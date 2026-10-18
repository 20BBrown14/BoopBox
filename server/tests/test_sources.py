import textwrap

import pytest

from app.config import Settings
from app.errors import ErrorCode
from app.sources import FakeSource, SourceRegistry
from app.types.source import Range, SourceError

ITEM = "fake-item"


async def _read_all(stream) -> bytes:
    out = b""
    async for chunk in stream.aiter_bytes():
        out += chunk
    return out


async def test_full_read_returns_fixture_bytes():
    data = b"boopboop" * 4096
    src = FakeSource(data=data)
    async with await src.open(ITEM, None) as stream:
        body = await _read_all(stream)
    assert body == data
    assert stream.content_length == len(data)
    assert stream.total_size == len(data)
    assert stream.content_range is None


async def test_ranged_read_returns_slice_and_facts():
    data = bytes(range(256)) * 4  # 1024 bytes, deterministic
    src = FakeSource(data=data)
    async with await src.open(ITEM, Range(start=10, end=19)) as stream:
        body = await _read_all(stream)
    assert body == data[10:20]
    assert stream.content_length == 10
    assert stream.content_range == (10, 19, len(data))
    assert stream.total_size == len(data)


async def test_range_clamped_to_object_end():
    data = b"x" * 100
    src = FakeSource(data=data)
    async with await src.open(ITEM, Range(start=90, end=999)) as stream:
        body = await _read_all(stream)
    assert body == data[90:]
    assert stream.content_range == (90, 99, 100)
    assert stream.content_length == 10


async def test_reports_duration():
    src = FakeSource(duration=180)
    assert await src.duration(ITEM) == 180


async def test_none_duration_mode():
    src = FakeSource(duration=None)
    assert await src.duration(ITEM) is None


async def test_item_unavailable_on_unknown_item():
    src = FakeSource()
    with pytest.raises(SourceError) as exc:
        await src.open("missing", None)
    assert exc.value.code is ErrorCode.item_unavailable


async def test_source_unavailable_mode():
    src = FakeSource(fail_with=ErrorCode.source_unavailable)
    with pytest.raises(SourceError) as exc:
        await src.open(ITEM, None)
    assert exc.value.code is ErrorCode.source_unavailable
    # Also on the pre-stream duration path P7 uses.
    with pytest.raises(SourceError) as exc2:
        await src.duration(ITEM)
    assert exc2.value.code is ErrorCode.source_unavailable


async def test_unavailable_detail_is_log_only():
    # The error carries a log-only detail; it is not the client message surface.
    # P6/P3 build the client message from the code alone.
    src = FakeSource(fail_with=ErrorCode.source_unavailable)
    with pytest.raises(SourceError) as exc:
        await src.duration(ITEM)
    err = exc.value
    assert err.log_detail is not None
    assert isinstance(err.code, ErrorCode)


async def test_cleanup_runs_on_context_exit():
    src = FakeSource()
    async with await src.open(ITEM, None) as stream:
        assert stream.closed is False
    assert stream.closed is True
    assert src.last_stream is stream


# --- Registry ---

_CONFIG = textwrap.dedent(
    """
    sources:
      - id: fake-main
        type: fake
        base_url: http://unused
    """
)


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    path = tmp_path / "config.yaml"
    path.write_text(_CONFIG)
    return Settings(_env_file=None, config_path=str(path))


def test_registry_resolves_configured_source(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    registry = SourceRegistry.from_settings(settings)
    assert isinstance(registry.get("fake-main"), FakeSource)


def test_registry_unknown_id_raises(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    registry = SourceRegistry.from_settings(settings)
    with pytest.raises(KeyError):
        registry.get("nope")
