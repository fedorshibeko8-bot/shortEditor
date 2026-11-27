from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from shorteditor.core.logging import JsonFormatter, configure_logging


def _record(message: str = "clip failed", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.WARNING, __file__, 1, message, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_keeps_structured_fields() -> None:
    payload = json.loads(
        JsonFormatter().format(
            _record(clip_id="abc", stage="download", duration_ms=1234, error="boom")
        )
    )

    assert payload["event"] == "clip failed"
    assert payload["level"] == "WARNING"
    assert payload["clip_id"] == "abc"
    assert payload["stage"] == "download"
    assert payload["duration_ms"] == 1234
    assert payload["error"] == "boom"
    assert "timestamp" in payload


def test_json_formatter_keeps_arbitrary_extra_fields_and_survives_unsafe_values() -> None:
    payload = json.loads(
        JsonFormatter().format(
            _record(job="disk_check", reason="lock_held", free_percent=4.5, unsafe=object())
        )
    )

    assert payload["job"] == "disk_check"
    assert payload["reason"] == "lock_held"
    assert payload["free_percent"] == 4.5
    assert isinstance(payload["unsafe"], str)


def test_json_formatter_uses_record_creation_time() -> None:
    record = _record()

    payload = json.loads(JsonFormatter().format(record))

    assert datetime.fromisoformat(payload["timestamp"]).timestamp() == pytest.approx(
        record.created, abs=0.001
    )


def test_json_formatter_omits_absent_optional_fields() -> None:
    payload = json.loads(JsonFormatter().format(_record()))

    assert set(payload) == {"event", "timestamp", "level"}


def test_json_formatter_keeps_cyrillic_readable() -> None:
    formatted = JsonFormatter().format(_record("клип готов"))

    assert "клип готов" in formatted


def test_json_formatter_puts_traceback_into_error() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "RuntimeError: boom" in payload["error"]


def test_configure_logging_writes_json_lines_to_rotating_file(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    configure_logging("DEBUG", log_dir=log_dir, rotation_mb=2, backups=3)
    try:
        logging.getLogger("test").warning("hello", extra={"event": "hello", "clip_id": "c1"})
        for handler in logging.getLogger().handlers:
            handler.flush()

        lines = (log_dir / "shorteditor.log").read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[-1])["clip_id"] == "c1"

        rotating = [
            handler
            for handler in logging.getLogger().handlers
            if isinstance(handler, RotatingFileHandler)
        ]
        assert len(rotating) == 1
        assert rotating[0].maxBytes == 2 * 1024 * 1024
        assert rotating[0].backupCount == 3
    finally:
        # Закрыть файловый handler, иначе Windows не отпустит файл до конца теста.
        configure_logging("INFO")


def test_configure_logging_without_dir_has_no_file_handler() -> None:
    configure_logging("INFO")
    try:
        assert not any(
            isinstance(handler, RotatingFileHandler)
            for handler in logging.getLogger().handlers
        )
    finally:
        configure_logging("INFO")


@pytest.mark.parametrize(("rotation_mb", "backups"), [(0, 5), (50, 0)])
def test_configure_logging_rejects_invalid_rotation(rotation_mb: int, backups: int) -> None:
    with pytest.raises(ValueError):
        configure_logging("INFO", log_dir="logs", rotation_mb=rotation_mb, backups=backups)
