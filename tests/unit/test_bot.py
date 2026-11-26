from __future__ import annotations

from types import SimpleNamespace

import aiosqlite
import pytest

from shorteditor.bot.app import _build_scheduler_jobs
from shorteditor.bot.handlers import count_statuses
from shorteditor.bot.middleware import AdminOnlyMiddleware
from shorteditor.storage.database import initialize_database


def test_scheduler_registers_only_supplied_callbacks_with_configured_schedules() -> None:
    async def callback() -> None:
        pass

    jobs = _build_scheduler_jobs(
        {"parser_poll": callback, "daily_digest": callback},
        poll_interval_minutes=15,
        digest_at="21:00",
        candidate_ttl_scan_minutes=10,
        disk_check_minutes=5,
        tz="Europe/Moscow",
    )

    assert [job.name for job in jobs] == ["parser_poll", "daily_digest"]
    assert jobs[0].schedule.interval_seconds == 900


@pytest.mark.asyncio
async def test_admin_middleware_rejects_foreign_id() -> None:
    middleware = AdminOnlyMiddleware(admin_id=123)
    called = False

    async def handler(event: object, data: dict[str, object]) -> str:
        nonlocal called
        called = True
        return "handler-called"

    event = SimpleNamespace(from_user=SimpleNamespace(id=999))
    result = await middleware(handler, event, {})  # type: ignore[arg-type]

    assert result is None
    assert called is False


@pytest.mark.asyncio
async def test_admin_middleware_accepts_admin_id() -> None:
    middleware = AdminOnlyMiddleware(admin_id=123)

    async def handler(event: object, data: dict[str, object]) -> str:
        return "handler-called"

    event = SimpleNamespace(from_user=SimpleNamespace(id=123))
    result = await middleware(handler, event, {})  # type: ignore[arg-type]

    assert result == "handler-called"


@pytest.mark.asyncio
async def test_empty_database_status_counts_are_honest(tmp_path) -> None:
    database_path = tmp_path / "shorteditor.db"
    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as db:
        counts = await count_statuses(db)

    assert counts
    assert all(count == 0 for count in counts.values())
