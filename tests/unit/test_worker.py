from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest

from shorteditor.core.statuses import ClipStatus
from shorteditor.core.worker import Worker
from shorteditor.storage.database import initialize_database
from shorteditor.storage.repository import ClipRepository


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


async def add_approved_clip(repository: ClipRepository, clip_id: str) -> None:
    await repository.create_clip(clip_id)
    await repository.transition(clip_id, ClipStatus.SENT_TO_ADMIN)
    await repository.transition(clip_id, ClipStatus.APPROVED)


async def wait_for_status(
    repository: ClipRepository,
    clip_id: str,
    expected: ClipStatus,
) -> None:
    for _ in range(100):
        if await repository.get_status(clip_id) == expected:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"{clip_id} did not reach status {expected.value}")


@pytest.mark.asyncio
async def test_worker_processes_only_configured_status_and_logs_success(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    repository = ClipRepository(db_path)
    await add_approved_clip(repository, "approved-clip")
    await repository.create_clip("new-clip")
    completed = asyncio.Event()

    async def process_clip(clip_id: str) -> None:
        await repository.transition(clip_id, ClipStatus.DOWNLOADING)
        completed.set()

    notifier = FakeNotifier()
    worker = Worker(
        repository,
        (ClipStatus.APPROVED,),
        {ClipStatus.APPROVED: process_clip},
        poll_interval_seconds=0.01,
        claim_ttl_minutes=15,
        max_attempts=3,
        notifier=notifier,
        worker_id="worker-a",
    )
    task = asyncio.create_task(worker.run())

    await asyncio.wait_for(completed.wait(), timeout=1)
    worker.stop()
    await asyncio.wait_for(task, timeout=1)

    assert await repository.get_status("approved-clip") == ClipStatus.DOWNLOADING
    assert await repository.get_status("new-clip") == ClipStatus.NEW
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT attempt_count, worker_claim FROM clips WHERE clip_id = 'approved-clip'"
        )
        attempt_count, claim = await cursor.fetchone()
    assert attempt_count == 0
    assert claim is None
    assert any(
        record.event == "worker_step_succeeded"
        and record.clip_id == "approved-clip"
        and record.stage == ClipStatus.APPROVED.value
        and isinstance(record.duration_ms, int)
        for record in caplog.records
    )
    assert notifier.messages == []


@pytest.mark.asyncio
async def test_worker_retries_and_notifies_once_after_max_attempts(tmp_path: Path) -> None:
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    repository = ClipRepository(db_path)
    await add_approved_clip(repository, "clip-1")
    notifier = FakeNotifier()
    calls = 0
    third_attempt = asyncio.Event()

    async def fail_clip(clip_id: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            third_attempt.set()
        raise RuntimeError("processing failed")

    worker = Worker(
        repository,
        (ClipStatus.APPROVED,),
        {ClipStatus.APPROVED: fail_clip},
        poll_interval_seconds=0.01,
        claim_ttl_minutes=15,
        max_attempts=3,
        notifier=notifier,
        worker_id="worker-a",
    )
    task = asyncio.create_task(worker.run())

    await asyncio.wait_for(third_attempt.wait(), timeout=1)
    await wait_for_status(repository, "clip-1", ClipStatus.FAILED)
    worker.stop()
    await asyncio.wait_for(task, timeout=1)

    assert calls == 3
    assert len(notifier.messages) == 1
    assert "processing failed" in notifier.messages[0]
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            SELECT attempt_count, worker_claim FROM clips WHERE clip_id = 'clip-1'
            """
        )
        attempt_count, claim = await cursor.fetchone()
        events = await db.execute_fetchall(
            """
            SELECT event_type, error FROM events
            WHERE clip_id = 'clip-1' AND event_type LIKE 'worker_%'
            """
        )
    assert attempt_count == 3
    assert claim is None
    assert len(events) == 3
    assert events[-1] == ("worker_failed", "processing failed")


@pytest.mark.asyncio
async def test_worker_stop_waits_for_current_clip_and_releases_claim(tmp_path: Path) -> None:
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    repository = ClipRepository(db_path)
    await add_approved_clip(repository, "clip-1")
    started = asyncio.Event()
    finish = asyncio.Event()

    async def process_clip(clip_id: str) -> None:
        started.set()
        await finish.wait()

    worker = Worker(
        repository,
        (ClipStatus.APPROVED,),
        {ClipStatus.APPROVED: process_clip},
        poll_interval_seconds=0.01,
        claim_ttl_minutes=15,
        max_attempts=3,
        notifier=FakeNotifier(),
        worker_id="worker-a",
    )
    task = asyncio.create_task(worker.run())

    await asyncio.wait_for(started.wait(), timeout=1)
    worker.stop()
    finish.set()
    await asyncio.wait_for(task, timeout=1)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT worker_claim, claimed_at FROM clips WHERE clip_id = 'clip-1'"
        )
        assert await cursor.fetchone() == (None, None)


@pytest.mark.asyncio
async def test_worker_reclaims_expired_claim_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    repository = ClipRepository(db_path)
    await add_approved_clip(repository, "clip-1")
    assert await repository.claim_next("dead-worker", (ClipStatus.APPROVED,))

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE clips SET claimed_at = '2000-01-01T00:00:00.000Z' WHERE clip_id = 'clip-1'"
        )
        await db.commit()
    completed = asyncio.Event()

    async def process_clip(clip_id: str) -> None:
        await repository.transition(clip_id, ClipStatus.DOWNLOADING)
        completed.set()

    worker = Worker(
        repository,
        (ClipStatus.APPROVED,),
        {ClipStatus.APPROVED: process_clip},
        poll_interval_seconds=0.01,
        claim_ttl_minutes=15,
        max_attempts=3,
        notifier=FakeNotifier(),
        worker_id="new-worker",
    )
    task = asyncio.create_task(worker.run())

    await asyncio.wait_for(completed.wait(), timeout=1)
    worker.stop()
    await asyncio.wait_for(task, timeout=1)

    assert await repository.get_status("clip-1") == ClipStatus.DOWNLOADING


def test_worker_rejects_status_that_cannot_become_failed(tmp_path: Path) -> None:
    repository = ClipRepository(tmp_path / "shorteditor.db")

    async def process_clip(clip_id: str) -> None:
        return None

    with pytest.raises(ValueError, match="cannot transition to failed"):
        Worker(
            repository,
            (ClipStatus.NEW,),
            {ClipStatus.NEW: process_clip},
            poll_interval_seconds=0.01,
            claim_ttl_minutes=15,
            max_attempts=3,
            notifier=FakeNotifier(),
        )
