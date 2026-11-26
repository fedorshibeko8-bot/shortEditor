from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Collection, Mapping
from typing import Protocol

from shorteditor.core.statuses import ClipStatus
from shorteditor.storage.repository import ClipRepository

StepHandler = Callable[[str], Awaitable[None]]


class Notifier(Protocol):
    async def send(self, text: str) -> None: ...


class Worker:
    def __init__(
        self,
        repository: ClipRepository,
        statuses: Collection[ClipStatus],
        handlers: Mapping[ClipStatus, StepHandler],
        poll_interval_seconds: float,
        claim_ttl_minutes: int,
        max_attempts: int,
        notifier: Notifier,
        *,
        worker_id: str | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than 0")
        if claim_ttl_minutes < 1:
            raise ValueError("claim_ttl_minutes must be at least 1")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if not statuses:
            raise ValueError("Worker requires at least one processable status")
        if not set(statuses) <= handlers.keys():
            raise ValueError("Every processable status must have a handler")

        self.repository = repository
        self.statuses = tuple(statuses)
        self.handlers = handlers
        self.poll_interval_seconds = poll_interval_seconds
        self.claim_ttl_minutes = claim_ttl_minutes
        self.max_attempts = max_attempts
        self.notifier = notifier
        self.worker_id = worker_id or str(uuid.uuid4())
        self._stop_event = asyncio.Event()
        self._logger = logging.getLogger(__name__)

    async def run(self) -> None:
        await self.repository.release_expired_claims(self.claim_ttl_minutes)
        while not self._stop_event.is_set():
            clip_id = await self.repository.claim_next(
                self.worker_id,
                self.statuses,
                self.claim_ttl_minutes,
            )
            if clip_id is None:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.poll_interval_seconds,
                    )
                except TimeoutError:
                    pass
                continue
            await self._process(clip_id)

    def stop(self) -> None:
        self._stop_event.set()

    async def _process(self, clip_id: str) -> None:
        status = await self.repository.get_status(clip_id)
        if status is None:
            await self.repository.release_claim(clip_id, self.worker_id)
            return

        started = time.monotonic()
        self._logger.info(
            "worker_step_started",
            extra={"event": "worker_step_started", "clip_id": clip_id, "stage": status.value},
        )
        finished = False
        try:
            try:
                await self.handlers[status](clip_id)
            except Exception as exc:  # noqa: BLE001
                error = str(exc) or exc.__class__.__name__
                result = await self.repository.finish_attempt(
                    clip_id,
                    self.worker_id,
                    max_attempts=self.max_attempts,
                    error=error,
                )
                finished = True
                self._log_step_finished(
                    clip_id,
                    status,
                    started,
                    "worker_step_failed",
                    error=error,
                )
                if result is not None and result.failed:
                    try:
                        await self.notifier.send(f"Клип {clip_id} переведён в failed: {error}")
                    except Exception as notify_error:
                        self._logger.exception(
                            "worker_notification_failed",
                            extra={
                                "event": "worker_notification_failed",
                                "clip_id": clip_id,
                                "stage": status.value,
                                "error": str(notify_error) or notify_error.__class__.__name__,
                            },
                        )
            else:
                result = await self.repository.finish_attempt(
                    clip_id,
                    self.worker_id,
                    max_attempts=self.max_attempts,
                )
                finished = True
                self._log_step_finished(clip_id, status, started, "worker_step_succeeded")
            if result is None:
                self._logger.warning(
                    "worker_claim_lost",
                    extra={
                        "event": "worker_claim_lost",
                        "clip_id": clip_id,
                        "stage": status.value,
                    },
                )
        finally:
            if not finished:
                await self.repository.release_claim(clip_id, self.worker_id)

    def _log_step_finished(
        self,
        clip_id: str,
        status: ClipStatus,
        started: float,
        event: str,
        *,
        error: str | None = None,
    ) -> None:
        extra: dict[str, object] = {
            "event": event,
            "clip_id": clip_id,
            "stage": status.value,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
        if error is not None:
            extra["error"] = error
        log = self._logger.error if error is not None else self._logger.info
        log(event, extra=extra)
