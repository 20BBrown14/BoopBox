"""Jellyfin source tests, backed by httpx.MockTransport (no real server).

Mirrors test_sources' style: deterministic, async, asserting the Source
contract and the scrub-at-the-boundary discipline.
"""

import textwrap

import httpx2 as httpx
import pytest

from app.config import Settings
from app.errors import ErrorCode, default_message, http_error
from app.sources import JellyfinSource, SourceRegistry
from app.sources.jellyfin import _TICKS_PER_SECOND
from app.types.source import Range, SourceError

BASE = "http://jellyfin.test"
KEY = "secret-key"
ITEM = "item-123"


def _source(handler, *, api_key: str = KEY, user_id: str | None = None):
    client = httpx.AsyncClient(
        base_url=BASE,
        headers={"Authorization": f'MediaBrowser Token="{api_key}"'},
        transport=httpx.MockTransport(handler),
    )
    return JellyfinSource(BASE, api_key, user_id=user_id, client=client)


async def _read_all(stream) -> bytes:
    out = b""
    async for chunk in stream.aiter_bytes():
        out += chunk
    return out


# --- open: full stream ---


async def test_open_full_relays_bytes_and_facts():
    data = b"audio-bytes" * 512
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["static"] = request.url.params.get("static")
        seen["auth"] = request.headers.get("authorization")
        seen["range"] = request.headers.get("range")
        return httpx.Response(200, content=data, headers={"Content-Type": "audio/mpeg"})

    src = _source(handler)
    async with await src.open(ITEM, None) as stream:
        body = await _read_all(stream)

    assert body == data
    assert stream.content_type == "audio/mpeg"
    assert stream.total_size == len(data)
    assert stream.content_length == len(data)
    assert stream.content_range is None
    assert seen["path"] == f"/Audio/{ITEM}/stream"
    assert seen["static"] == "true"
    assert seen["auth"] == f'MediaBrowser Token="{KEY}"'
    assert seen["range"] is None


# --- open: ranged stream ---


async def test_open_ranged_forwards_range_and_relays_206():
    full = bytes(range(256)) * 8  # 2048 bytes
    sl = full[10:21]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("range") == "bytes=10-20"
        return httpx.Response(
            206,
            content=sl,
            headers={
                "Content-Type": "audio/mpeg",
                "Content-Range": f"bytes 10-20/{len(full)}",
            },
        )

    src = _source(handler)
    async with await src.open(ITEM, Range(start=10, end=20)) as stream:
        body = await _read_all(stream)

    assert body == sl
    assert stream.content_range == (10, 20, len(full))
    assert stream.content_length == 11
    assert stream.total_size == len(full)


# --- duration ---


async def test_duration_converts_ticks_to_seconds():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/Items/{ITEM}"
        return httpx.Response(200, json={"RunTimeTicks": 184 * _TICKS_PER_SECOND})

    src = _source(handler)
    assert await src.duration(ITEM) == 184


async def test_duration_missing_ticks_is_none():
    src = _source(lambda r: httpx.Response(200, json={"Name": "x"}))
    assert await src.duration(ITEM) is None


async def test_duration_zero_ticks_is_none():
    src = _source(lambda r: httpx.Response(200, json={"RunTimeTicks": 0}))
    assert await src.duration(ITEM) is None


async def test_duration_passes_user_id_when_set():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["userId"] = request.url.params.get("userId")
        return httpx.Response(200, json={"RunTimeTicks": _TICKS_PER_SECOND})

    src = _source(handler, user_id="user-7")
    assert await src.duration(ITEM) == 1
    assert seen["userId"] == "user-7"


# --- members ---


async def test_members_returns_item_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/Items"
        assert request.url.params.get("parentId") == "col-1"
        assert request.url.params.get("recursive") == "true"
        return httpx.Response(
            200,
            json={"Items": [{"Id": "a"}, {"Id": "b"}, {"Id": "c"}]},
        )

    src = _source(handler)
    assert await src.members("col-1") == ["a", "b", "c"]


async def test_members_empty_collection_is_item_unavailable():
    src = _source(lambda r: httpx.Response(200, json={"Items": []}))
    with pytest.raises(SourceError) as exc:
        await src.members("col-empty")
    assert exc.value.code is ErrorCode.item_unavailable


# --- error mapping ---


@pytest.mark.parametrize(
    "status,expected",
    [
        (404, ErrorCode.item_unavailable),
        (401, ErrorCode.source_unavailable),
        (403, ErrorCode.source_unavailable),
        (500, ErrorCode.source_unavailable),
        (503, ErrorCode.source_unavailable),
    ],
)
async def test_duration_status_mapping(status, expected):
    src = _source(lambda r: httpx.Response(status, text="upstream detail body"))
    with pytest.raises(SourceError) as exc:
        await src.duration(ITEM)
    assert exc.value.code is expected


@pytest.mark.parametrize(
    "status,expected",
    [
        (404, ErrorCode.item_unavailable),
        (401, ErrorCode.source_unavailable),
        (500, ErrorCode.source_unavailable),
    ],
)
async def test_open_status_mapping(status, expected):
    src = _source(lambda r: httpx.Response(status, text="secret upstream body"))
    with pytest.raises(SourceError) as exc:
        await src.open(ITEM, None)
    assert exc.value.code is expected


async def test_connection_error_is_source_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    src = _source(handler)
    with pytest.raises(SourceError) as exc:
        await src.duration(ITEM)
    assert exc.value.code is ErrorCode.source_unavailable


async def test_open_connection_error_is_source_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    src = _source(handler)
    with pytest.raises(SourceError) as exc:
        await src.open(ITEM, None)
    assert exc.value.code is ErrorCode.source_unavailable


async def test_missing_api_key_is_source_unavailable():
    # No upstream call should happen; the guard fires first.
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not call upstream without a key")

    src = _source(handler, api_key="")
    with pytest.raises(SourceError) as exc:
        await src.duration(ITEM)
    assert exc.value.code is ErrorCode.source_unavailable


# --- scrubbing: upstream detail never reaches the client message ---


async def test_upstream_detail_is_log_only_not_client_message():
    leaky = "jellyfin item 42 at http://jellyfin.test/Audio/42 key=secret-key"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=leaky)

    src = _source(handler)
    with pytest.raises(SourceError) as exc:
        await src.duration(ITEM)
    err = exc.value

    # The log-only detail may describe the failure, but the CLIENT-facing
    # surface (what P6/P3 render from the code) must carry none of it.
    client_msg = default_message(err.code)
    body, status = http_error(err.code)
    assert status == 502
    for leak in ("jellyfin.test", "secret-key", "/Audio/", ITEM):
        assert leak not in client_msg
        assert leak not in body["message"]


# --- stream cleanup ---


async def test_stream_cleanup_closes_upstream():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"xyz", headers={"Content-Type": "audio/mpeg"}
        )

    src = _source(handler)
    stream = await src.open(ITEM, None)
    assert stream.closed is False
    async with stream:
        await _read_all(stream)
    assert stream.closed is True


# --- registry wiring ---

_CONFIG = textwrap.dedent(
    """
    sources:
      - id: jellyfin-main
        type: jellyfin
        base_url: http://jellyfin.test
    """
)


def test_registry_builds_jellyfin_with_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    # Key env is derived from the source id by source_api_key_env.
    monkeypatch.setenv("BOOPBOX_SOURCE_JELLYFIN_MAIN_API_KEY", "built-key")
    path = tmp_path / "config.yaml"
    path.write_text(_CONFIG)
    settings = Settings(_env_file=None, config_path=str(path))

    registry = SourceRegistry.from_settings(settings)
    source = registry.get("jellyfin-main")
    assert isinstance(source, JellyfinSource)
    assert source._api_key == "built-key"
    assert source._base_url == "http://jellyfin.test"
