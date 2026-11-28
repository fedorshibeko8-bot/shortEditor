from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any, Self

import aiohttp
import pytest

from shorteditor.core.config import ParserConfig
from shorteditor.parser.twitch import (
    CLIPS_URL,
    TOKEN_URL,
    TwitchAPIError,
    TwitchHelixClient,
    TwitchPaginationError,
    TwitchRequestError,
)


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.body = body if body is not None else {}
        self.headers = headers or {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def json(self, *, content_type: str | None = None) -> Any:
        return self.body

    async def text(self) -> str:
        return str(self.body)


class FakeSession:
    def __init__(self, responses: list[FakeResponse | BaseException]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        return response


def token_response(token: str = "token", expires_in: int = 3600) -> FakeResponse:
    return FakeResponse(200, {"access_token": token, "expires_in": expires_in})


def clip(
    clip_id: str = "clip-1",
    *,
    created_at: str = "2026-11-28T07:00:00Z",
) -> dict[str, Any]:
    return {
        "id": clip_id,
        "url": "https://clips.twitch.tv/clip",
        "embed_url": "https://clips.twitch.tv/embed?clip=clip",
        "title": "A clip",
        "broadcaster_id": "broadcaster-id",
        "broadcaster_name": "Broadcaster",
        "creator_name": "Creator",
        "game_id": "game-id",
        "view_count": 1234,
        "created_at": created_at,
        "duration": 42.5,
        "thumbnail_url": "https://example.test/thumbnail.jpg",
        "language": "en",
    }


def clips_response(*clips: dict[str, Any], cursor: str | None = None) -> FakeResponse:
    pagination = {"cursor": cursor} if cursor is not None else {}
    return FakeResponse(200, {"data": list(clips), "pagination": pagination})


def make_client(
    session: FakeSession,
    *,
    config: ParserConfig | None = None,
    sleep: Any = None,
    clock: Any = None,
    wall_clock: Any = None,
) -> TwitchHelixClient:
    kwargs: dict[str, Any] = {"session": session, "config": config}
    if sleep is not None:
        kwargs["sleep"] = sleep
    if clock is not None:
        kwargs["clock"] = clock
    if wall_clock is not None:
        kwargs["wall_clock"] = wall_clock
    return TwitchHelixClient("test-client-id", "test-client-secret", **kwargs)


@pytest.mark.asyncio
async def test_token_is_reused_and_refreshed_before_expiration() -> None:
    now = [100.0]
    session = FakeSession(
        [
            token_response("first", expires_in=120),
            clips_response(clip()),
            clips_response(clip("clip-2")),
            token_response("second"),
            clips_response(clip("clip-3")),
        ]
    )
    client = make_client(session, clock=lambda: now[0])

    await client.get_clips_page()
    await client.get_clips_page()
    assert sum(url == TOKEN_URL for _, url, _ in session.calls) == 1

    now[0] = 160.0
    await client.get_clips_page()
    assert sum(url == TOKEN_URL for _, url, _ in session.calls) == 2
    assert session.calls[-1][2]["headers"]["Authorization"] == "Bearer second"


@pytest.mark.asyncio
async def test_parallel_requests_share_one_token_refresh() -> None:
    session = FakeSession([token_response(), *(clips_response(clip(str(i))) for i in range(8))])
    client = make_client(session)

    await asyncio.gather(*(client.get_clips_page() for _ in range(8)))

    assert sum(url == TOKEN_URL for _, url, _ in session.calls) == 1


@pytest.mark.asyncio
async def test_unauthorized_response_refreshes_token_and_retries_once() -> None:
    session = FakeSession(
        [
            token_response("old"),
            FakeResponse(401, {"message": "expired"}),
            token_response("new"),
            clips_response(clip()),
        ]
    )

    page = await make_client(session).get_clips_page()

    assert page.clips[0].id == "clip-1"
    assert [(call[2].get("headers") or {}).get("Authorization") for call in session.calls] == [
        None,
        "Bearer old",
        None,
        "Bearer new",
    ]


@pytest.mark.asyncio
async def test_pagination_sends_first_and_after_until_cursor_is_absent() -> None:
    session = FakeSession(
        [
            token_response(),
            clips_response(clip("one"), cursor="cursor-1"),
            clips_response(clip("two"), cursor="cursor-2"),
            clips_response(clip("three")),
        ]
    )
    client = make_client(session)

    found = [item async for item in client.iter_clips(first=2, max_pages=5)]
    requests = [kwargs["params"] for method, url, kwargs in session.calls if url == CLIPS_URL]

    assert [item.id for item in found] == ["one", "two", "three"]
    assert [params["first"] for params in requests] == [2, 2, 2]
    assert [params.get("after") for params in requests] == [None, "cursor-1", "cursor-2"]


@pytest.mark.asyncio
async def test_pagination_respects_clip_limit_and_rejects_repeated_cursor() -> None:
    limited_session = FakeSession([token_response(), clips_response(clip("one"), clip("two"))])
    found = [
        item
        async for item in make_client(limited_session).iter_clips(max_clips=1, max_pages=4)
    ]
    assert [item.id for item in found] == ["one"]
    assert sum(url == CLIPS_URL for _, url, _ in limited_session.calls) == 1

    repeated_session = FakeSession(
        [
            token_response(),
            clips_response(clip("one"), cursor="same"),
            clips_response(clip("two"), cursor="same"),
        ]
    )
    with pytest.raises(TwitchPaginationError, match="repeated pagination cursor"):
        _ = [item async for item in make_client(repeated_session).iter_clips(max_pages=4)]


@pytest.mark.asyncio
async def test_rate_limit_retries_using_retry_after() -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    session = FakeSession(
        [
            token_response(),
            FakeResponse(429, {"message": "slow down"}, {"Retry-After": "2.5"}),
            clips_response(clip()),
        ]
    )
    page = await make_client(session, sleep=fake_sleep).get_clips_page()

    assert page.clips[0].id == "clip-1"
    assert delays == [2.5]


@pytest.mark.asyncio
async def test_server_error_uses_exponential_backoff() -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    session = FakeSession(
        [
            token_response(),
            FakeResponse(503, {"message": "unavailable"}),
            clips_response(clip()),
        ]
    )

    await make_client(session, sleep=fake_sleep).get_clips_page()

    assert delays == [1.0]


@pytest.mark.asyncio
async def test_rate_limit_exhaustion_raises_api_error_with_body() -> None:
    session = FakeSession(
        [
            token_response(),
            FakeResponse(429, {"message": "first"}),
            FakeResponse(429, {"message": "last"}),
        ]
    )
    client = make_client(
        session,
        config=ParserConfig(http_max_attempts=2),
        sleep=lambda _: asyncio.sleep(0),
    )

    with pytest.raises(TwitchAPIError) as exc:
        await client.get_clips_page()

    assert exc.value.status == 429
    assert exc.value.body == {"message": "last"}


@pytest.mark.asyncio
async def test_clip_fields_are_mapped_and_created_at_is_timezone_aware() -> None:
    session = FakeSession([token_response(), clips_response(clip())])

    result = (await make_client(session).get_clips_page()).clips[0]

    assert result.id == "clip-1"
    assert result.url == "https://clips.twitch.tv/clip"
    assert result.embed_url == "https://clips.twitch.tv/embed?clip=clip"
    assert result.title == "A clip"
    assert result.broadcaster_id == "broadcaster-id"
    assert result.broadcaster_name == "Broadcaster"
    assert result.creator_name == "Creator"
    assert result.game_id == "game-id"
    assert result.view_count == 1234
    assert result.created_at == datetime(2026, 11, 28, 7, tzinfo=UTC)
    assert result.created_at.tzinfo is not None
    assert result.duration == 42.5
    assert result.thumbnail_url == "https://example.test/thumbnail.jpg"
    assert result.language == "en"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [TimeoutError(), aiohttp.ClientConnectionError("offline")],
)
async def test_timeout_and_network_errors_raise_client_exception(
    failure: BaseException,
) -> None:
    session = FakeSession([token_response(), failure])

    with pytest.raises(TwitchRequestError, match="Twitch GET request failed"):
        await make_client(session).get_clips_page()
