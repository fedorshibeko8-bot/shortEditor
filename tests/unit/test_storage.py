from pathlib import Path

import aiosqlite
import pytest

from shorteditor.core.statuses import ClipStatus
from shorteditor.storage.database import initialize_database
from shorteditor.storage.repository import ClipRepository


@pytest.mark.asyncio
async def test_idempotent_migration_creates_tables_and_ttl_index(tmp_path: Path) -> None:
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    await initialize_database(db_path)

    async with aiosqlite.connect(db_path) as db:
        tables_cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        tables = {row[0] for row in await tables_cursor.fetchall()}
        columns_cursor = await db.execute("PRAGMA table_info(clips)")
        clip_columns = {row[1] for row in await columns_cursor.fetchall()}
        indexes_cursor = await db.execute("PRAGMA index_list(clips)")
        indexes = {row[1] for row in await indexes_cursor.fetchall()}

    assert {"clips", "renders", "events", "schema_migrations"} <= tables
    assert "sent_to_admin_at" in clip_columns
    assert "idx_clips_status_sent_at" in indexes


@pytest.mark.asyncio
async def test_migration_upgrades_existing_clips_table(tmp_path: Path) -> None:
    db_path = tmp_path / "shorteditor.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "CREATE TABLE clips (clip_id TEXT PRIMARY KEY, status TEXT NOT NULL)"
        )
        await db.commit()

    await initialize_database(db_path)

    async with aiosqlite.connect(db_path) as db:
        columns_cursor = await db.execute("PRAGMA table_info(clips)")
        columns = {row[1] for row in await columns_cursor.fetchall()}
    assert "sent_to_admin_at" in columns


@pytest.mark.asyncio
async def test_repository_updates_status_and_sent_admin_timestamp(tmp_path: Path) -> None:
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    repository = ClipRepository(db_path)
    await repository.create_clip("clip-1", title="Test")

    assert await repository.get_status("clip-1") == ClipStatus.NEW
    assert await repository.transition("clip-1", ClipStatus.SENT_TO_ADMIN)
    assert await repository.transition("clip-1", ClipStatus.APPROVED)
    assert await repository.get_status("clip-1") == ClipStatus.APPROVED

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT sent_to_admin_at FROM clips WHERE clip_id = 'clip-1'"
        )
        row = await cursor.fetchone()
    assert row[0]


@pytest.mark.asyncio
async def test_repository_does_not_double_process_claim(tmp_path: Path) -> None:
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    repository = ClipRepository(db_path)
    await repository.create_clip("clip-1")
    await repository.transition("clip-1", ClipStatus.SENT_TO_ADMIN)
    await repository.transition("clip-1", ClipStatus.APPROVED)

    first = await repository.claim_next("worker-a", (ClipStatus.APPROVED,))
    second = await repository.claim_next("worker-b", (ClipStatus.APPROVED,))

    assert first == "clip-1"
    assert second is None


@pytest.mark.asyncio
async def test_repository_release_claim_allows_claim_again(tmp_path: Path) -> None:
    db_path = tmp_path / "shorteditor.db"
    await initialize_database(db_path)
    repository = ClipRepository(db_path)
    await repository.create_clip("clip-1")
    await repository.transition("clip-1", ClipStatus.SENT_TO_ADMIN)
    await repository.transition("clip-1", ClipStatus.APPROVED)

    assert await repository.claim_next("worker-a", (ClipStatus.APPROVED,))
    assert await repository.release_claim("clip-1", "worker-a")
    assert await repository.claim_next("worker-b", (ClipStatus.APPROVED,))
