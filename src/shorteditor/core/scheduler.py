from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from datetime import time as wall_time
from pathlib import Path
from typing import Protocol

import aiosqlite


class Schedule(Protocol):
    def next_after(self, now: datetime) -> datetime: ...


class SchedulerNotifier(Protocol):
    async def send(self, text: str) -> None: ...


@dataclass(frozen=True)
class IntervalSchedule:
    interval_seconds: float

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than 0")

    def next_after(self, now: datetime) -> datetime:
        _require_aware(now)
        return now + timedelta(seconds=self.interval_seconds)

    def next_after_due(self, due: datetime, now: datetime) -> datetime:
        _require_aware(due)
        _require_aware(now)
        next_due = due + timedelta(seconds=self.interval_seconds)
        if next_due <= now:
            missed_intervals = math.floor(
                (now - next_due).total_seconds() / self.interval_seconds
            ) + 1
            next_due += timedelta(seconds=missed_intervals * self.interval_seconds)
        return next_due


@dataclass(frozen=True)
class DailySchedule:
    at: wall_time
    timezone: tzinfo = UTC

    @classmethod
    def from_string(cls, value: str, timezone: tzinfo) -> DailySchedule:
        try:
            parsed = wall_time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("daily schedule time must use HH:MM format") from exc
        if parsed.tzinfo is not None:
            raise ValueError("daily schedule time must not include a timezone")
        return cls(parsed, timezone)

    def next_after(self, now: datetime) -> datetime:
        _require_aware(now)
        local_now = now.astimezone(self.timezone)
        next_run = datetime.combine(local_now.date(), self.at, tzinfo=self.timezone)
        if next_run <= local_now:
            next_run = datetime.combine(
                local_now.date() + timedelta(days=1),
                self.at,
                tzinfo=self.timezone,
            )
        return next_run.astimezone(UTC)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler datetimes must be timezone-aware")


JobCallback = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    schedule: Schedule
    callback: JobCallback
    run_immediately: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("job name must not be empty")


async def _acquire_job_lock(
    database_path: str | Path,
    job_name: str,
    owner: str,
    lease_seconds: float,
) -> bool:
    lease_modifier = f"+{lease_seconds} seconds"
    async with aiosqlite.connect(database_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "DELETE FROM background_job_locks WHERE expires_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        )
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO background_job_locks(job_name, owner, expires_at)
            VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?))
            """,
            (job_name, owner, lease_modifier),
        )
        acquired = cursor.rowcount == 1
        await db.commit()
    return acquired


async def _renew_job_lock(
    database_path: str | Path,
    job_name: str,
    owner: str,
    lease_seconds: float,
) -> bool:
    async with aiosqlite.connect(database_path) as db:
        cursor = await db.execute(
            """
            UPDATE background_job_locks
            SET expires_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?)
            WHERE job_name = ? AND owner = ?
            """,
            (f"+{lease_seconds} seconds", job_name, owner),
        )
        await db.commit()
    return cursor.rowcount == 1


async def _release_job_lock(database_path: str | Path, job_name: str, owner: str) -> None:
    async with aiosqlite.connect(database_path) as db:
        await db.execute(
            "DELETE FROM background_job_locks WHERE job_name = ? AND owner = ?",
            (job_name, owner),
        )
        await db.commit()


class Scheduler:
    def __init__(
        self,
        database_path: str | Path,
        jobs: Sequence[ScheduledJob],
        *,
        notifier: SchedulerNotifier | None = None,
        lock_lease_seconds: float = 60,
    ) -> None:
        if lock_lease_seconds <= 0:
            raise ValueError("lock_lease_seconds must be greater than 0")
        names = [job.name for job in jobs]
        if len(set(names)) != len(names):
            raise ValueError("job names must be unique")

        self.database_path = str(database_path)
        self.jobs = tuple(jobs)
        self.notifier = notifier
        self.lock_lease_seconds = lock_lease_seconds
        self._stop_event = asyncio.Event()
        self._logger = logging.getLogger(__name__)

    async def run(self) -> None:
        tasks = [
            asyncio.create_task(self._run_job(job), name=f"scheduler-{job.name}")
            for job in self.jobs
        ]
        if tasks:
            await asyncio.gather(*tasks)

    def stop(self) -> None:
        self._stop_event.set()

    async def _run_job(self, job: ScheduledJob) -> None:
        now = datetime.now(UTC)
        due = now if job.run_immediately else job.schedule.next_after(now)
        while not self._stop_event.is_set():
            if await self._wait_until(due):
                return
            await self._run_once(job)
            now = datetime.now(UTC)
            if isinstance(job.schedule, IntervalSchedule):
                due = job.schedule.next_after_due(due, now)
            else:
                due = job.schedule.next_after(now)

    async def _wait_until(self, due: datetime) -> bool:
        delay = max(0.0, (due - datetime.now(UTC)).total_seconds())
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            return True
        except TimeoutError:
            return self._stop_event.is_set()

    async def _run_once(self, job: ScheduledJob) -> None:
        owner = str(uuid.uuid4())
        started = time.monotonic()
        acquired = False
        heartbeat: asyncio.Task[None] | None = None
        error: Exception | None = None
        try:
            acquired = await _acquire_job_lock(
                self.database_path,
                job.name,
                owner,
                self.lock_lease_seconds,
            )
            if not acquired:
                self._logger.info(
                    "scheduler_job_skipped",
                    extra={
                        "event": "scheduler_job_skipped",
                        "stage": "scheduler",
                        "job": job.name,
                        "reason": "lock_held",
                    },
                )
                return
            heartbeat = asyncio.create_task(
                self._renew_lock(job.name, owner),
                name=f"scheduler-lock-{job.name}",
            )
            await job.callback()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - individual job failures must not stop scheduling
            error = exc
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
            if acquired:
                try:
                    await _release_job_lock(self.database_path, job.name, owner)
                except Exception as exc:
                    if error is None:
                        error = exc
                    else:
                        self._logger.exception(
                            "scheduler_lock_release_failed",
                            extra={
                                "event": "scheduler_lock_release_failed",
                                "stage": "scheduler",
                                "job": job.name,
                                "error": str(exc) or exc.__class__.__name__,
                            },
                        )

        duration_ms = round((time.monotonic() - started) * 1000)
        if error is not None:
            message = str(error) or error.__class__.__name__
            self._logger.exception(
                "scheduler_job_failed",
                exc_info=(type(error), error, error.__traceback__),
                extra={
                    "event": "scheduler_job_failed",
                    "stage": "scheduler",
                    "job": job.name,
                    "duration_ms": duration_ms,
                    "error": message,
                },
            )
            await self._notify_failure(job.name, message)
            return
        self._logger.info(
            "scheduler_job_succeeded",
            extra={
                "event": "scheduler_job_succeeded",
                "stage": "scheduler",
                "job": job.name,
                "duration_ms": duration_ms,
            },
        )

    async def _renew_lock(self, job_name: str, owner: str) -> None:
        interval = self.lock_lease_seconds / 3
        while True:
            await asyncio.sleep(interval)
            try:
                renewed = await _renew_job_lock(
                    self.database_path,
                    job_name,
                    owner,
                    self.lock_lease_seconds,
                )
            except Exception as exc:
                self._logger.exception(
                    "scheduler_lock_renewal_failed",
                    extra={
                        "event": "scheduler_lock_renewal_failed",
                        "stage": "scheduler",
                        "job": job_name,
                        "error": str(exc) or exc.__class__.__name__,
                    },
                )
                continue
            if not renewed:
                self._logger.error(
                    "scheduler_lock_lost",
                    extra={
                        "event": "scheduler_lock_lost",
                        "stage": "scheduler",
                        "job": job_name,
                    },
                )
                return

    async def _notify_failure(self, job_name: str, error: str) -> None:
        if self.notifier is None:
            return
        try:
            await self.notifier.send(f"Фоновая задача {job_name} завершилась с ошибкой: {error}")
        except Exception as exc:
            self._logger.exception(
                "scheduler_notification_failed",
                extra={
                    "event": "scheduler_notification_failed",
                    "stage": "scheduler",
                    "job": job_name,
                    "error": str(exc) or exc.__class__.__name__,
                },
            )
