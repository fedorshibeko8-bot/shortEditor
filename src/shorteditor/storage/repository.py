from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from shorteditor.core.statuses import ClipStatus, assert_transition


class ClipRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)

    async def create_clip(self, clip_id: str, **fields: Any) -> None:
        allowed = {
            "title",
            "channel_login",
            "channel_name",
            "category_id",
            "category_name",
            "clip_url",
            "duration_sec",
            "views",
            "created_at",
        }
        extra = set(fields) - allowed
        if extra:
            raise ValueError(f"Unknown clip fields: {sorted(extra)}")

        columns = ["clip_id", "status", *fields]
        placeholders = ", ".join("?" for _ in columns)
        values = [clip_id, ClipStatus.NEW.value, *(fields[key] for key in fields)]
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                f"INSERT OR IGNORE INTO clips ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            await db.commit()

    async def get_status(self, clip_id: str) -> ClipStatus | None:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "SELECT status FROM clips WHERE clip_id = ?",
                (clip_id,),
            )
            row = await cursor.fetchone()
        return ClipStatus(row[0]) if row else None

    async def transition(
        self,
        clip_id: str,
        target: ClipStatus | str,
        *,
        rejection_reason: str | None = None,
    ) -> bool:
        target_status = ClipStatus(target)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT status FROM clips WHERE clip_id = ?",
                (clip_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                await db.rollback()
                return False

            current_status = ClipStatus(row[0])
            if current_status == target_status:
                await db.rollback()
                return True

            assert_transition(current_status, target_status)
            await db.execute(
                """
                UPDATE clips
                SET status = ?,
                    rejection_reason = CASE WHEN ? IS NULL THEN rejection_reason ELSE ? END,
                    sent_to_admin_at = CASE
                        WHEN ? = 'sent_to_admin' AND sent_to_admin_at IS NULL
                        THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        ELSE sent_to_admin_at
                    END,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE clip_id = ?
                """,
                (
                    target_status.value,
                    rejection_reason,
                    rejection_reason,
                    target_status.value,
                    clip_id,
                ),
            )
            await db.execute(
                """
                INSERT INTO events(clip_id, status, stage, event_type, payload_json)
                VALUES (?, ?, ?, 'status_transition', ?)
                """,
                (
                    clip_id,
                    target_status.value,
                    target_status.value,
                    json.dumps({"from": current_status.value, "to": target_status.value}),
                ),
            )
            await db.commit()
            return True

    async def claim_next(self, worker_claim: str, statuses: tuple[ClipStatus, ...]) -> str | None:
        if not statuses:
            return None
        placeholders = ", ".join("?" for _ in statuses)
        values: tuple[Any, ...] = tuple(status.value for status in statuses)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                f"""
                SELECT clip_id
                FROM clips
                WHERE status IN ({placeholders}) AND worker_claim IS NULL
                ORDER BY created_record_at
                LIMIT 1
                """,
                values,
            )
            row = await cursor.fetchone()
            if row is None:
                await db.rollback()
                return None
            clip_id = row[0]
            cursor = await db.execute(
                """
                UPDATE clips
                SET worker_claim = ?, claimed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE clip_id = ? AND worker_claim IS NULL
                """,
                (worker_claim, clip_id),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return None
            await db.commit()
            return clip_id

    async def release_claim(self, clip_id: str, worker_claim: str) -> bool:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                """
                UPDATE clips
                SET worker_claim = NULL, claimed_at = NULL
                WHERE clip_id = ? AND worker_claim = ?
                """,
                (clip_id, worker_claim),
            )
            changed = cursor.rowcount == 1
            await db.commit()
            return changed
