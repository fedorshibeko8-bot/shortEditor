from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOG_FILE_NAME = "shorteditor.log"
STRUCTURED_FIELDS = ("clip_id", "stage", "duration_ms", "error")


class JsonFormatter(logging.Formatter):
    """Одна строка — один JSON-объект с обязательными структурными полями."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "event": getattr(record, "event", record.getMessage()),
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
        }
        for field in STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: str = "INFO",
    *,
    log_dir: str | Path | None = None,
    rotation_mb: int = 50,
    backups: int = 5,
) -> None:
    """Настраивает структурные логи: stdout всегда, файл с ротацией — при заданном log_dir."""

    if rotation_mb < 1:
        raise ValueError("rotation_mb must be at least 1")
    if backups < 1:
        raise ValueError("backups must be at least 1")

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = JsonFormatter()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    if log_dir is not None:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            directory / LOG_FILE_NAME,
            maxBytes=rotation_mb * 1024 * 1024,
            backupCount=backups,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.setLevel(level.upper())
