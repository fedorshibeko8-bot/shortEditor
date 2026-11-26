from __future__ import annotations

import asyncio
import logging
import signal
import sqlite3
import time
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.exceptions import AiogramError, TelegramNetworkError
from aiogram.types import BotCommand
from pydantic import ValidationError

from shorteditor.bot.handlers import create_handlers
from shorteditor.bot.logging import configure_logging
from shorteditor.bot.middleware import AdminOnlyMiddleware
from shorteditor.core.config import AppConfig, load_settings
from shorteditor.storage.database import initialize_database

DATABASE_PATH = Path("data/shorteditor.db")


class BotApplication:
    def __init__(self, database_path: str | Path = DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.started_at = 0.0
        self.bot: Bot | None = None
        self.dispatcher: Dispatcher | None = None
        self.database: aiosqlite.Connection | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        self.started_at = time.monotonic()
        settings = load_settings()
        AppConfig.model_validate({})
        configure_logging(settings.log_level)
        await initialize_database(self.database_path)
        self.database = await aiosqlite.connect(self.database_path)

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
        if self.bot is not None:
            await self.bot.session.close()
            self.bot = None
        if self.database is not None:
            await self.database.close()
            self.database = None
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
