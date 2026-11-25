from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA_VERSION = 1


async def initialize_database(database_path: str | Path) -> None:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS clips (
                clip_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                title TEXT,
                channel_login TEXT,
                channel_name TEXT,
                category_id TEXT,
                category_name TEXT,
                clip_url TEXT,
                duration_sec REAL,
                views INTEGER,
                created_at TEXT,
                sent_to_admin_at TEXT,
                rejection_reason TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                worker_claim TEXT,
                claimed_at TEXT,
                transcript_json TEXT,
                created_record_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        existing = await db.execute("PRAGMA table_info(clips)")
        columns = {row[1] for row in await existing.fetchall()}
        for name, definition in (
            ("sent_to_admin_at", "TEXT"),
            ("rejection_reason", "TEXT"),
            ("worker_claim", "TEXT"),
            ("claimed_at", "TEXT"),
        ):
            if name not in columns:
                await db.execute(f"ALTER TABLE clips ADD COLUMN {name} {definition}")

        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_clips_status_sent_at ON clips(status, sent_to_admin_at)"
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS renders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clip_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                comment TEXT,
                file_path TEXT,
                width INTEGER,
                height INTEGER,
                fps TEXT,
                duration_sec REAL,
                video_codec TEXT,
                audio_codec TEXT,
                size_bytes INTEGER,
                crf INTEGER,
                subtitles_mode TEXT,
                hook_text TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(clip_id, version),
                FOREIGN KEY (clip_id) REFERENCES clips(clip_id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clip_id TEXT,
                status TEXT,
                stage TEXT,
                event_type TEXT NOT NULL,
                payload_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                FOREIGN KEY (clip_id) REFERENCES clips(clip_id) ON DELETE SET NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_clip_id ON events(clip_id, id)"
        )

        await db.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        await db.commit()
