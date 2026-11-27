from __future__ import annotations

import asyncio
import logging
import signal
import sqlite3
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.exceptions import AiogramError, TelegramNetworkError
from aiogram.types import BotCommand
from pydantic import ValidationError

from shorteditor.bot.handlers import create_handlers
from shorteditor.bot.middleware import AdminOnlyMiddleware
from shorteditor.bot.notifications import TelegramNotifier
from shorteditor.core.config import AppConfig, load_config, load_settings
from shorteditor.core.disk import DiskGuard
from shorteditor.core.logging import configure_logging
from shorteditor.core.scheduler import (
    DailySchedule,
    IntervalSchedule,
    ScheduledJob,
    Scheduler,
)
from shorteditor.core.statuses import ClipStatus
from shorteditor.core.worker import StepHandler, Worker
from shorteditor.storage.database import initialize_database
from shorteditor.storage.repository import ClipRepository

DATABASE_PATH = Path("data/shorteditor.db")
SchedulerCallback = Callable[[], Awaitable[None]]


def _build_scheduler_jobs(
    callbacks: Mapping[str, SchedulerCallback],
    *,
    poll_interval_minutes: int,
    digest_at: str,
    candidate_ttl_scan_minutes: int,
    disk_check_minutes: int,
    tz: str,
) -> tuple[ScheduledJob, ...]:
    supported_jobs = {
        "parser_poll": IntervalSchedule(poll_interval_minutes * 60),
        "daily_digest": DailySchedule.from_string(digest_at, ZoneInfo(tz)),
        "candidate_ttl_scan": IntervalSchedule(candidate_ttl_scan_minutes * 60),
        "disk_check": IntervalSchedule(disk_check_minutes * 60),
    }
    unknown_jobs = set(callbacks) - supported_jobs.keys()
    if unknown_jobs:
        raise ValueError(f"Unknown scheduler jobs: {sorted(unknown_jobs)}")
    return tuple(
        ScheduledJob(name=name, schedule=supported_jobs[name], callback=callback)
        for name, callback in callbacks.items()
    )


class BotApplication:
    def __init__(
        self,
        database_path: str | Path = DATABASE_PATH,
        worker_handlers: Mapping[ClipStatus, StepHandler] | None = None,
        scheduler_jobs: Mapping[str, SchedulerCallback] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.worker_handlers = worker_handlers
        self.scheduler_jobs = scheduler_jobs or {}
        self.config: AppConfig | None = None
        self.started_at = 0.0
        self.bot: Bot | None = None
        self.dispatcher: Dispatcher | None = None
        self.worker: Worker | None = None
        self.worker_task: asyncio.Task[None] | None = None
        self.scheduler: Scheduler | None = None
        self.scheduler_task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @staticmethod
    def _load_config() -> AppConfig:
        """config.yaml может отсутствовать (например, в контейнере) — тогда действуют дефолты."""

        try:
            return load_config()
        except FileNotFoundError:
            return AppConfig()

    async def start(self) -> None:
        self.started_at = time.monotonic()
        settings = load_settings()
        config = self._load_config()
        self.config = config
        configure_logging(
            settings.log_level or config.logging.level,
            log_dir=config.logging.dir,
            rotation_mb=config.logging.rotation_mb,
            backups=config.logging.backups,
        )
        await initialize_database(self.database_path)

        self.bot = Bot(settings.telegram_bot_token)
        self.dispatcher = Dispatcher()
        self.dispatcher.message.middleware(AdminOnlyMiddleware(settings.telegram_admin_id))
        self.dispatcher.callback_query.middleware(AdminOnlyMiddleware(settings.telegram_admin_id))
        self.dispatcher.include_router(create_handlers(self.database_path, self.started_at))
        await self.bot.set_my_commands(
            [
                BotCommand(command="start", description="Запустить бота"),
                BotCommand(command="status", description="Показать состояние"),
            ]
        )

        logging.getLogger(__name__).info(
            "bot_started",
            extra={"event": "bot_started", "stage": "startup"},
        )

        notifier = TelegramNotifier(self.bot, settings.telegram_admin_id)

        if self.worker_handlers:
            self.worker = Worker(
                repository=ClipRepository(self.database_path),
                statuses=tuple(self.worker_handlers),
                handlers=self.worker_handlers,
                poll_interval_seconds=config.queue.poll_interval_seconds,
                claim_ttl_minutes=config.queue.claim_ttl_minutes,
                max_attempts=config.queue.max_attempts,
                notifier=notifier,
            )
            self.worker_task = asyncio.create_task(self.worker.run(), name="clip-worker")

        jobs = dict(self.scheduler_jobs)
        if "disk_check" not in jobs:
            disk_guard = DiskGuard(
                self.database_path.parent,
                threshold_percent=config.notifications.disk_free_alert_percent,
                alert_interval=timedelta(hours=config.notifications.disk_alert_repeat_hours),
                notifier=notifier,
            )
            jobs["disk_check"] = disk_guard.check

        scheduled_jobs = _build_scheduler_jobs(
            jobs,
            poll_interval_minutes=config.parser.poll_interval_minutes,
            digest_at=config.notifications.daily_digest_at,
            candidate_ttl_scan_minutes=config.parser.candidate_ttl_scan_minutes,
            disk_check_minutes=config.notifications.disk_check_minutes,
            tz=settings.tz,
        )
        self.scheduler = Scheduler(
            self.database_path,
            scheduled_jobs,
            notifier=notifier,
        )
        self.scheduler_task = asyncio.create_task(
            self.scheduler.run(),
            name="background-scheduler",
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.request_shutdown)
            except NotImplementedError:
                pass

        try:
            await self.dispatcher.start_polling(
                self.bot,
                handle_signals=False,
                allowed_updates=["message", "callback_query"],
            )
        except TelegramNetworkError as exc:
            logging.getLogger(__name__).error(
                "bot_polling_network_error",
                extra={"event": "bot_polling_network_error", "stage": "polling", "error": str(exc)},
            )
            raise

    def request_shutdown(self) -> None:
        if self._stopping.is_set():
            return
        self._stopping.set()
        logging.getLogger(__name__).info(
            "bot_shutdown_requested",
            extra={"event": "bot_shutdown_requested", "stage": "shutdown"},
        )
        if self.dispatcher is not None:
            self.dispatcher.stop_polling()

    async def close(self) -> None:
        if self.scheduler is not None:
            self.scheduler.stop()
        if self.worker is not None:
            self.worker.stop()
        scheduler_task = self.scheduler_task
        self.scheduler_task = None
        task = self.worker_task
        self.worker_task = None
        try:
            if scheduler_task is not None:
                await scheduler_task
            if task is not None:
                await task
        finally:
            self.scheduler = None
            self.worker = None
            if self.bot is not None:
                await self.bot.session.close()
                self.bot = None
            logging.getLogger(__name__).info(
                "bot_shutdown_complete",
                extra={"event": "bot_shutdown_complete", "stage": "shutdown"},
            )


async def run() -> int:
    app = BotApplication()
    try:
        await app.start()
        await app.close()
        return 0
    except ValidationError as exc:
        configure_logging("ERROR")
        missing_fields = []
        env_names = {
            "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
            "telegram_admin_id": "TELEGRAM_ADMIN_ID",
            "twitch_client_id": "TWITCH_CLIENT_ID",
            "twitch_client_secret": "TWITCH_CLIENT_SECRET",
            "r2_account_id": "R2_ACCOUNT_ID",
            "r2_access_key_id": "R2_ACCESS_KEY_ID",
            "r2_secret_access_key": "R2_SECRET_ACCESS_KEY",
            "r2_bucket": "R2_BUCKET",
        }
        for error in exc.errors():
            field = error["loc"][0] if error["loc"] else "unknown"
            missing_fields.append(env_names.get(str(field), str(field).upper()))
        names = ", ".join(sorted(set(missing_fields)))
        print(f"Startup error: required environment variables are missing or invalid: {names}")
        return 1
    except (AiogramError, OSError, RuntimeError, sqlite3.Error, ValueError) as exc:
        configure_logging("ERROR")
        print(f"Startup error: {exc}")
        return 1
    finally:
        await app.close()
