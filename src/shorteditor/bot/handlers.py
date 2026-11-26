from __future__ import annotations

import time
from pathlib import Path

import aiosqlite
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from shorteditor import __version__
from shorteditor.core.statuses import ClipStatus


async def count_statuses(db: aiosqlite.Connection) -> dict[str, int]:
    cursor = await db.execute("SELECT status, COUNT(*) FROM clips GROUP BY status")
    rows = await cursor.fetchall()
    counts = {status.value: 0 for status in ClipStatus}
    counts.update({str(status): int(count) for status, count in rows})
    return counts


def create_handlers(database_path: str | Path, started_at: float) -> Router:
    router = Router(name="bot")

    @router.message(Command("start"))
    async def start_handler(message: Message) -> None:
        await message.answer("shortEditor готов к работе.")

    @router.message(Command("status"))
    async def status_handler(message: Message) -> None:
        async with aiosqlite.connect(database_path) as db:
            counts = await count_statuses(db)

        uptime_seconds = max(0, int(time.monotonic() - started_at))
        uptime_hours, remainder = divmod(uptime_seconds, 3600)
        uptime_minutes, uptime_seconds = divmod(remainder, 60)
        lines = [
            f"Версия: {__version__}",
            f"Uptime: {uptime_hours:02d}:{uptime_minutes:02d}:{uptime_seconds:02d}",
            "Клипы:",
        ]
        lines.extend(f"- {status}: {count}" for status, count in counts.items())
        await message.answer("\n".join(lines))

    return router
