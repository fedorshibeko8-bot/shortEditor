from __future__ import annotations

from datetime import timedelta

import pytest

from shorteditor.core.disk import DiskGuard, DiskUsage, format_bytes


class FakeNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.messages: list[str] = []
        self.fail = fail

    async def send(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("telegram is down")
        self.messages.append(text)


def _usage(free_bytes: int, total_bytes: int = 1000) -> DiskUsage:
    return DiskUsage(total_bytes=total_bytes, free_bytes=free_bytes)


@pytest.mark.asyncio
async def test_alerts_once_per_interval() -> None:
    now = 0.0
    notifier = FakeNotifier()
    guard = DiskGuard(
        "/data",
        threshold_percent=10,
        alert_interval=timedelta(hours=6),
        notifier=notifier,
        usage_provider=lambda _: _usage(50),
        clock=lambda: now,
    )

    assert await guard.check() is True

    now = 3600.0
    assert await guard.check() is False

    now = 6 * 3600.0
    assert await guard.check() is True

    assert len(notifier.messages) == 2
    assert "5.0 %" in notifier.messages[0]


@pytest.mark.asyncio
async def test_threshold_is_strict_less_than() -> None:
    notifier = FakeNotifier()
    guard = DiskGuard(
        "/data",
        threshold_percent=10,
        notifier=notifier,
        usage_provider=lambda _: _usage(100),
        clock=lambda: 0.0,
    )

    assert await guard.check() is False
    assert notifier.messages == []


@pytest.mark.asyncio
async def test_above_threshold_never_notifies() -> None:
    notifier = FakeNotifier()
    guard = DiskGuard(
        "/data",
        notifier=notifier,
        usage_provider=lambda _: _usage(500),
        clock=lambda: 0.0,
    )

    assert await guard.check() is False
    assert notifier.messages == []


@pytest.mark.asyncio
async def test_recovery_resets_throttle() -> None:
    now = 0.0
    notifier = FakeNotifier()
    free = 50
    guard = DiskGuard(
        "/data",
        alert_interval=timedelta(hours=6),
        notifier=notifier,
        usage_provider=lambda _: _usage(free),
        clock=lambda: now,
    )

    assert await guard.check() is True

    free = 900
    assert await guard.check() is False

    free = 50
    assert await guard.check() is True

    assert len(notifier.messages) == 2


@pytest.mark.asyncio
async def test_failed_notification_is_retried_next_check() -> None:
    notifier = FakeNotifier(fail=True)
    guard = DiskGuard(
        "/data",
        alert_interval=timedelta(hours=6),
        notifier=notifier,
        usage_provider=lambda _: _usage(50),
        clock=lambda: 0.0,
    )

    assert await guard.check() is False

    notifier.fail = False
    assert await guard.check() is True
    assert len(notifier.messages) == 1


@pytest.mark.asyncio
async def test_works_without_notifier() -> None:
    guard = DiskGuard("/data", usage_provider=lambda _: _usage(50), clock=lambda: 0.0)

    assert await guard.check() is True


@pytest.mark.asyncio
async def test_zero_total_bytes_means_zero_percent() -> None:
    notifier = FakeNotifier()
    guard = DiskGuard(
        "/data",
        notifier=notifier,
        usage_provider=lambda _: _usage(0, total_bytes=0),
        clock=lambda: 0.0,
    )

    assert await guard.check() is True
    assert notifier.messages


@pytest.mark.parametrize("threshold", [0, -1, 101])
def test_invalid_threshold_is_rejected(threshold: float) -> None:
    with pytest.raises(ValueError):
        DiskGuard("/data", threshold_percent=threshold)


@pytest.mark.parametrize("interval", [timedelta(0), timedelta(seconds=-1)])
def test_invalid_alert_interval_is_rejected(interval: timedelta) -> None:
    with pytest.raises(ValueError):
        DiskGuard("/data", alert_interval=interval)


def test_format_bytes_uses_readable_units() -> None:
    assert format_bytes(0) == "0.0 Б"
    assert format_bytes(1536) == "1.5 КБ"
    assert format_bytes(5 * 1024**3) == "5.0 ГБ"
