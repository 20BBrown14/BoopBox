import pytest

from app.crypto import source_aad
from app.errors import ErrorCode
from app.sources import FakeSource, register_source_type
from app.types.source import Range, SourceError
from tests.conftest import add_source, run_sql

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
    data = bytes(range(256)) * 4
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


async def test_members_expands_collection():
    src = FakeSource(collections={"col-1": ["a", "b", "c"]})
    assert await src.members("col-1") == ["a", "b", "c"]


async def test_members_unknown_collection_is_item_unavailable():
    src = FakeSource()
    with pytest.raises(SourceError) as exc:
        await src.members("nope")
    assert exc.value.code is ErrorCode.item_unavailable


async def test_members_empty_collection_is_item_unavailable():
    src = FakeSource(collections={"col-empty": []})
    with pytest.raises(SourceError) as exc:
        await src.members("col-empty")
    assert exc.value.code is ErrorCode.item_unavailable


async def test_members_source_unavailable_mode():
    src = FakeSource(fail_with=ErrorCode.source_unavailable)
    with pytest.raises(SourceError) as exc:
        await src.members("col-1")
    assert exc.value.code is ErrorCode.source_unavailable


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
    # Also on the pre-stream duration path.
    with pytest.raises(SourceError) as exc2:
        await src.duration(ITEM)
    assert exc2.value.code is ErrorCode.source_unavailable


async def test_unavailable_detail_is_log_only():
    # The error carries a log-only detail; it is not the client message surface.
    # The client message is built from the code alone.
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


async def _registry_error(services, source_id) -> ErrorCode:
    with pytest.raises(SourceError) as exc:
        await services.sources.get(source_id)
    return exc.value.code


async def test_registry_builds_live_enabled_source(services):
    add_source(services.env.db_path, 1)
    assert isinstance(await services.sources.get(1), FakeSource)


@pytest.mark.parametrize(
    "row", [{}, {"enabled": False}, {"deleted": True}, {"type": "nope"}]
)
async def test_registry_refuses_unusable_source(services, row):
    if row:
        add_source(services.env.db_path, 1, **row)
    assert await _registry_error(services, 1) is ErrorCode.source_unavailable


async def test_registry_caches_and_rebuilds_on_change(services):
    db_path = services.env.db_path
    add_source(db_path, 1)
    first = await services.sources.get(1)
    assert await services.sources.get(1) is first
    run_sql(db_path, "UPDATE media_sources SET base_url = 'http://moved' WHERE id = 1")
    assert await services.sources.get(1) is not first


async def test_registry_decrypts_credential_bound_to_source(services):
    seen = {}

    def build(row, secret, options):
        seen[row.id] = (secret, options)
        return FakeSource()

    register_source_type("capture", build)
    db_path = services.env.db_path
    sealed = services.keyring.encrypt("api-key-1", source_aad(1))
    add_source(
        db_path, 1, type="capture", settings='{"user_id": "u"}', secret_encrypted=sealed
    )
    # The same ciphertext copied to another source must not decrypt there.
    add_source(db_path, 2, type="capture", secret_encrypted=sealed)

    await services.sources.get(1)
    assert seen[1] == ("api-key-1", {"user_id": "u"})
    assert await _registry_error(services, 2) is ErrorCode.source_unavailable
