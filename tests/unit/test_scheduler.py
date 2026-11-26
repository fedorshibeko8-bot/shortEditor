from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite
import pytest

from shorteditor.core.scheduler import (
    DailySchedule,
    IntervalSchedule,
    ScheduledJob,
    Scheduler,
    _acquire_job_lock,
)
from shorteditor.storage.database import initialize_database


def test_interval_schedule_skips_missed_ticks_without_drift() -> None:
    schedule = IntervalSchedule(10)
    start = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

    assert schedule.next_after(start).timestamp() == (start.timestamp() + 10)
    assert schedule.next_after_due(
        start + timedelta(seconds=10),
        start + timedelta(seconds=35),
    ) == start + timedelta(seconds=40)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-11-26T17:59:00+00:00", "2026-11-26T18:00:00+00:00"),
        ("2026-11-26T18:00:00+00:00", "2026-11-27T18:00:00+00:00"),
        ("2026-11-26T23:30:00+00:00", "2026-11-27T18:00:00+00:00"),
    ],
)
def test_daily_schedule_uses_local_time_and_crosses_midnight(
    now: str, expected: str
) -> None:
    schedule = DailySchedule(time(21, 0), ZoneInfo("Europe/Moscow"))

    assert schedule.next_after(datetime.fromisoformat(now)).isoformat() == expected


@pytest.mark.asyncio
async def test_scheduler_waits_for_schedule_by_default(tmp_path: Path) -> None:
    await initialize_database(tmp_path / "shorteditor.db")
    called = False

    async def callback() -> None:
        nonlocal called
        called = True

    scheduler = Scheduler(
        tmp_path / "shorteditor.db",
        [ScheduledJob("later", IntervalSchedule(3600), callback)],
    )
    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0)

    assert not called
    scheduler.stop()
    await task


@pytest.mark.asyncio
async def test_stop_waits_for_running_job_to_finish(tmp_path: Path) -> None:
    await initialize_database(tmp_path / "shorteditor.db")
    started = asyncio.Event()
    finish = asyncio.Event()

    async def callback() -> None:
        started.set()
        await finish.wait()

    scheduler = Scheduler(
        tmp_path / "shorteditor.db",
        [ScheduledJob("long", IntervalSchedule(3600), callback, run_immediately=True)],
    )
    task = asyncio.create_task(scheduler.run())
    await started.wait()
    scheduler.stop()

    assert not task.done()
    finish.set()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_failed_job_is_logged_notified_and_does_not_stop_scheduler(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    await initialize_database(tmp_path / "shorteditor.db")

    class Notifier:
        def __init__(self) -> None:
            self.messages: list[str] = []
            self.notified = asyncio.Event()

        async def send(self, text: str) -> None:
            self.messages.append(text)
            self.notified.set()

    notifier = Notifier()

    async def callback() -> None:
        raise RuntimeError("expected failure")

    scheduler = Scheduler(
        tmp_path / "shorteditor.db",
        [ScheduledJob("broken", IntervalSchedule(3600), callback, run_immediately=True)],
        notifier=notifier,
    )
    task = asyncio.create_task(scheduler.run())
    await notifier.notified.wait()

    assert len(notifier.messages) == 1
    assert not task.done()
    failure = next(record for record in caplog.records if record.event == "scheduler_job_failed")
    assert failure.stage == "scheduler"
    assert failure.duration_ms >= 0
    assert failure.error == "expected failure"

    scheduler.stop()
    await task


@pytest.mark.asyncio
async def test_busy_job_lock_is_skipped_and_expired_lock_is_reclaimed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    called = False

    async def callback() -> None:
        nonlocal called
        called = True

    scheduler = Scheduler(db_path, [])
    job = ScheduledJob("shared", IntervalSchedule(3600), callback)
    assert await _acquire_job_lock(db_path, "shared", "other-instance", 60)

    await scheduler._run_once(job)
    assert not called
    assert any(record.event == "scheduler_job_skipped" for record in caplog.records)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE background_job_locks SET expires_at = '2000-01-01T00:00:00.000Z' "
            "WHERE job_name = 'shared'"
        )
        await db.commit()

    await scheduler._run_once(job)
    assert called
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT job_name FROM background_job_locks WHERE job_name = 'shared'"
        )
        assert await cursor.fetchone() is None
