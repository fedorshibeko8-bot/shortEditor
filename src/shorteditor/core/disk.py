from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol


class DiskNotifier(Protocol):
    async def send(self, text: str) -> None: ...


@dataclass(frozen=True)
class DiskUsage:
    total_bytes: int
    free_bytes: int

    @property
    def free_percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return self.free_bytes / self.total_bytes * 100


def read_disk_usage(path: str | Path) -> DiskUsage:
    usage = shutil.disk_usage(Path(path))
    return DiskUsage(total_bytes=usage.total, free_bytes=usage.free)


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


class DiskGuard:
    """Проверяет свободное место и шлёт один алерт не чаще alert_interval."""

    def __init__(
        self,
        path: str | Path,
        *,
        threshold_percent: float = 10,
        alert_interval: timedelta = timedelta(hours=6),
        notifier: DiskNotifier | None = None,
        usage_provider: Callable[[str | Path], DiskUsage] = read_disk_usage,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 < threshold_percent <= 100:
            raise ValueError("threshold_percent must be between 0 and 100")
        if alert_interval <= timedelta(0):
            raise ValueError("alert_interval must be greater than zero")

        self.path = Path(path)
        self.threshold_percent = threshold_percent
        self.alert_interval = alert_interval
        self.notifier = notifier
        self.usage_provider = usage_provider
        self.clock = clock
        self._last_alert_at: float | None = None
        self._logger = logging.getLogger(__name__)

    async def check(self) -> bool:
        """Возвращает True, если алерт действительно отправлен."""

        usage = self.usage_provider(self.path)
        free_percent = usage.free_percent

        if free_percent >= self.threshold_percent:
            if self._last_alert_at is not None:
                self._last_alert_at = None
                self._logger.info(
                    "disk_space_recovered",
                    extra={
                        "event": "disk_space_recovered",
                        "stage": "disk",
                        "free_percent": round(free_percent, 1),
                        "threshold_percent": self.threshold_percent,
                    },
                )
            return False

        now = self.clock()
        if (
            self._last_alert_at is not None
            and now - self._last_alert_at < self.alert_interval.total_seconds()
        ):
            self._logger.debug(
                "disk_space_low_suppressed",
                extra={
                    "event": "disk_space_low_suppressed",
                    "stage": "disk",
                    "free_percent": round(free_percent, 1),
                },
            )
            return False

        self._logger.warning(
            "disk_space_low",
            extra={
                "event": "disk_space_low",
                "stage": "disk",
                "free_percent": round(free_percent, 1),
                "threshold_percent": self.threshold_percent,
                "free_bytes": usage.free_bytes,
                "total_bytes": usage.total_bytes,
            },
        )

        if self.notifier is not None:
            text = (
                f"⚠️ Мало свободного места: {free_percent:.1f} % "
                f"({format_bytes(usage.free_bytes)} из {format_bytes(usage.total_bytes)}). "
                f"Порог {self.threshold_percent:.0f} %."
            )
            try:
                await self.notifier.send(text)
            except Exception as exc:  # алерт не должен ронять планировщик
                self._logger.exception(
                    "disk_alert_failed",
                    extra={
                        "event": "disk_alert_failed",
                        "stage": "disk",
                        "error": str(exc) or exc.__class__.__name__,
                    },
                )
                return False

        self._last_alert_at = now
        return True
