from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol, Self

import aiohttp

from shorteditor.core.config import ParserConfig

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
CLIPS_URL = "https://api.twitch.tv/helix/clips"
TOKEN_REFRESH_MARGIN_SECONDS = 60


class TwitchClientError(Exception):
    """Base exception for Twitch client and response failures."""


class TwitchAPIError(TwitchClientError):
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self.body = body
        super().__init__(f"Twitch API returned HTTP {status}: {body}")


class TwitchRequestError(TwitchClientError):
    """A request failed before a valid HTTP response was received."""


class TwitchResponseError(TwitchClientError):
    """Twitch returned a response that does not match the Helix schema."""


class TwitchPaginationError(TwitchClientError):
    """Pagination returned a repeated cursor."""


@dataclass(frozen=True, slots=True)
class TwitchClip:
    id: str
    url: str
    embed_url: str
    title: str
    broadcaster_id: str
    broadcaster_name: str
    creator_name: str
    game_id: str
    view_count: int
    created_at: datetime
    duration: float
    thumbnail_url: str
    language: str


@dataclass(frozen=True, slots=True)
class TwitchClipPage:
    clips: tuple[TwitchClip, ...]
    after: str | None


class TwitchClipClient(Protocol):
    async def get_clips_page(
        self,
        *,
        first: int = 100,
        after: str | None = None,
        game_id: str | None = None,
        broadcaster_id: str | None = None,
        started_at: datetime | str | None = None,
        ended_at: datetime | str | None = None,
    ) -> TwitchClipPage: ...

    def iter_clips(
        self,
        *,
        first: int = 100,
        game_id: str | None = None,
        broadcaster_id: str | None = None,
        started_at: datetime | str | None = None,
        ended_at: datetime | str | None = None,
        max_pages: int = 100,
        max_clips: int = 1000,
    ) -> AsyncIterator[TwitchClip]: ...


@dataclass(frozen=True, slots=True)
class _HTTPResult:
    status: int
    headers: Mapping[str, str]
    body: Any


class TwitchHelixClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        config: ParserConfig | None = None,
        *,
        session: Any | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.config = config or ParserConfig()
        self._session = session
        self._owns_session = session is None
        self._sleep = sleep
        self._clock = clock
        self._wall_clock = wall_clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        self._get_session()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def get_clips_page(
        self,
        *,
        first: int = 100,
        after: str | None = None,
        game_id: str | None = None,
        broadcaster_id: str | None = None,
        started_at: datetime | str | None = None,
        ended_at: datetime | str | None = None,
    ) -> TwitchClipPage:
        if not 1 <= first <= 100:
            raise ValueError("first must be between 1 and 100")
        params: dict[str, str | int] = {"first": first}
        optional_params = {
            "after": after,
            "game_id": game_id,
            "broadcaster_id": broadcaster_id,
            "started_at": _format_datetime(started_at),
            "ended_at": _format_datetime(ended_at),
        }
        params.update({key: value for key, value in optional_params.items() if value is not None})

        payload = await self._authorized_get(params)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise TwitchResponseError("Twitch clips response must contain a data list")
        pagination = payload.get("pagination", {})
        if not isinstance(pagination, dict):
            raise TwitchResponseError("Twitch clips pagination must be an object")

        try:
            clips = tuple(_parse_clip(item) for item in payload["data"])
            cursor = pagination.get("cursor")
            if cursor is not None and not isinstance(cursor, str):
                raise ValueError("pagination cursor must be a string")
        except (KeyError, TypeError, ValueError) as exc:
            raise TwitchResponseError(f"Invalid Twitch clip response: {exc}") from exc
        return TwitchClipPage(clips=clips, after=cursor)

    async def iter_clips(
        self,
        *,
        first: int = 100,
        game_id: str | None = None,
        broadcaster_id: str | None = None,
        started_at: datetime | str | None = None,
        ended_at: datetime | str | None = None,
        max_pages: int = 100,
        max_clips: int = 1000,
    ) -> AsyncIterator[TwitchClip]:
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if max_clips < 1:
            raise ValueError("max_clips must be at least 1")

        cursor: str | None = None
        seen_cursors: set[str] = set()
        yielded = 0
        for _ in range(max_pages):
            page = await self.get_clips_page(
                first=first,
                after=cursor,
                game_id=game_id,
                broadcaster_id=broadcaster_id,
                started_at=started_at,
                ended_at=ended_at,
            )
            for clip in page.clips:
                yield clip
                yielded += 1
                if yielded >= max_clips:
                    return
            if page.after is None:
                return
            if page.after in seen_cursors:
                raise TwitchPaginationError(f"Twitch repeated pagination cursor: {page.after}")
            seen_cursors.add(page.after)
            cursor = page.after

    async def _authorized_get(self, params: Mapping[str, str | int]) -> Any:
        for auth_attempt in range(2):
            token = await self._get_access_token()
            result = await self._request_with_retries(
                "GET",
                CLIPS_URL,
                params=params,
                headers={"Client-Id": self.client_id, "Authorization": f"Bearer {token}"},
            )
            if result.status == 401 and auth_attempt == 0:
                await self._invalidate_token(token)
                continue
            if result.status >= 400:
                raise TwitchAPIError(result.status, result.body)
            return result.body
        raise TwitchClientError("Twitch authorization retry failed")

    async def _get_access_token(self) -> str:
        async with self._token_lock:
            if (
                self._token is not None
                and self._clock() < self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS
            ):
                return self._token

            result = await self._request_with_retries(
                "POST",
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
            )
            if result.status >= 400:
                raise TwitchAPIError(result.status, result.body)
            if not isinstance(result.body, dict):
                raise TwitchResponseError("Twitch token response must be an object")
            try:
                token = result.body["access_token"]
                expires_in = float(result.body["expires_in"])
                if not isinstance(token, str) or not token or expires_in <= 0:
                    raise ValueError("access_token and positive expires_in are required")
            except (KeyError, TypeError, ValueError) as exc:
                raise TwitchResponseError(f"Invalid Twitch token response: {exc}") from exc
            self._token = token
            self._token_expires_at = self._clock() + expires_in
            return token

    async def _invalidate_token(self, rejected_token: str) -> None:
        async with self._token_lock:
            if self._token == rejected_token:
                self._token = None
                self._token_expires_at = 0.0

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> _HTTPResult:
        max_attempts = self.config.http_max_attempts
        for attempt in range(max_attempts):
            try:
                async with self._get_session().request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.http_timeout_seconds),
                ) as response:
                    body = await _response_body(response)
                    result = _HTTPResult(response.status, response.headers, body)
            except (TimeoutError, aiohttp.ClientError) as exc:
                raise TwitchRequestError(
                    f"Twitch {method} request failed: {type(exc).__name__}: {exc}"
                ) from exc

            if (
                (result.status == 429 or 500 <= result.status <= 599)
                and attempt + 1 < max_attempts
            ):
                delay = _retry_delay(
                    result.headers,
                    attempt=attempt,
                    rate_limited=result.status == 429,
                    wall_clock=self._wall_clock,
                )
                await self._sleep(delay)
                continue
            return result
        raise TwitchClientError("Twitch request retry loop exhausted")

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.http_timeout_seconds)
            )
        return self._session


def _format_datetime(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Twitch date-time parameters must be timezone-aware")
    return value.isoformat().replace("+00:00", "Z")


def _parse_clip(raw: Any) -> TwitchClip:
    if not isinstance(raw, dict):
        raise TypeError("clip must be an object")
    try:
        created_at_value = raw["created_at"]
        if not isinstance(created_at_value, str):
            raise TypeError("created_at must be a string")
        created_at = datetime.fromisoformat(created_at_value)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return TwitchClip(
            id=str(raw["id"]),
            url=str(raw["url"]),
            embed_url=str(raw["embed_url"]),
            title=str(raw["title"]),
            broadcaster_id=str(raw["broadcaster_id"]),
            broadcaster_name=str(raw["broadcaster_name"]),
            creator_name=str(raw["creator_name"]),
            game_id=str(raw["game_id"]),
            view_count=int(raw["view_count"]),
            created_at=created_at,
            duration=float(raw["duration"]),
            thumbnail_url=str(raw["thumbnail_url"]),
            language=str(raw["language"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid clip fields: {exc}") from exc


async def _response_body(response: Any) -> Any:
    try:
        return await response.json(content_type=None)
    except (aiohttp.ContentTypeError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return await response.text()


def _retry_delay(
    headers: Mapping[str, str],
    *,
    attempt: int,
    rate_limited: bool,
    wall_clock: Callable[[], float],
) -> float:
    if rate_limited:
        retry_after = _header(headers, "Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    return max(0.0, retry_at.timestamp() - wall_clock())
                except (TypeError, ValueError, OverflowError):
                    pass
        rate_limit_reset = _header(headers, "Ratelimit-Reset")
        if rate_limit_reset is not None:
            try:
                return max(0.0, float(rate_limit_reset) - wall_clock())
            except ValueError:
                pass
    return float(2**attempt)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    value = next((value for key, value in headers.items() if key.lower() == name.lower()), None)
    return str(value) if value is not None else None
