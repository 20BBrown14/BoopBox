import json
import random
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.errors import ErrorCode
from app.models import Boop, Cmd, CmdName, Error, FlashCmd, Play, VersionReply
from app.mqtt.handler import box_time, handle_boop, normalize_uid, parse_version_reply
from app.mqtt.publish import publish_cmd, publish_flash
from app.mqtt.service import MqttService, _build_client, device_id_from_topic
from app.protocol import PROTOCOL_VERSION
from app.sources import FakeSource
from app.startup import start
from app.stream_token import verify
from app.types.source import SourceError
from tests.conftest import (
    StubSources,
    add_device,
    add_entry,
    add_mapping,
    add_source,
    query,
    run_sql,
)

SECRET = "stream-secret-at-least-thirty-two-bytes"
BASE_URL = "https://boop.example/base"
DEVICE = "boop-test"
ITEM = "fake-item"


class _Items(FakeSource):
    """A fake that knows a set of items rather than one."""

    def __init__(self, items=(ITEM,), **kwargs) -> None:
        super().__init__(**kwargs)
        self.items = set(items)

    def _guard(self, item):
        if self._fail_with is not None:
            raise SourceError(self._fail_with, log_detail="forced")
        if item not in self.items:
            raise SourceError(ErrorCode.item_unavailable, log_detail=f"no {item}")


def _fake(**kwargs) -> _Items:
    return _Items(
        items=(ITEM, "item-a", "item-b", "member-x"),
        collections={"col-1": ["member-x"], "col-empty": []},
        **kwargs,
    )


@pytest.fixture
async def svc(env, monkeypatch):
    monkeypatch.setenv("BOOPBOX_SECRETS_STREAM", SECRET)
    monkeypatch.setenv("BOOPBOX_PUBLIC_BASE_URL", BASE_URL)
    services = await start(env)
    db_path = env.db_path
    add_device(db_path, DEVICE)
    add_source(db_path, 1)
    add_mapping(db_path, 1, "boop/item")
    add_entry(db_path, 1, 1, 1, ITEM)
    add_mapping(db_path, 2, "boop/collection")
    add_entry(db_path, 2, 2, 1, "col-1", kind="collection")
    add_mapping(db_path, 3, "boop/empty")
    add_entry(db_path, 3, 3, 1, "col-empty", kind="collection")
    add_mapping(db_path, 4, "boop/multi")
    add_entry(db_path, 4, 4, 1, "item-a", position=0)
    add_entry(db_path, 5, 4, 1, "item-b", position=1)
    try:
        yield services
    finally:
        await services.aclose()


def _boop_bytes(
    slug: str, *, v: int = PROTOCOL_VERSION, bid: str = "b1", uid: str = "04aabbcc"
) -> bytes:
    return (
        Boop(v=v, id=bid, slug=slug, uid=uid, ts=1700000000).model_dump_json().encode()
    )


async def _handle(svc, slug, *, sources=None, seed=0, device=DEVICE, raw=None):
    return await handle_boop(
        device,
        raw if raw is not None else _boop_bytes(slug),
        db=svc.db,
        sources=sources or StubSources({1: _fake()}),
        settings=await svc.settings.snapshot(),
        rng=random.Random(seed),
    )


def _claims(play: Play):
    token = parse_qs(urlparse(play.url).query)["sig"][0]
    return verify(token, now=int(time.time()), secret=SECRET)


# --- resolution and the single response ---


async def test_item_slug_plays(svc):
    result = await _handle(svc, "boop/item")
    assert isinstance(result.response, Play)
    assert result.response.url.startswith(f"{BASE_URL}/stream?sig=")
    assert result.response.duration == 180
    assert result.response.boop.id == "b1"
    claims = _claims(result.response)
    assert (claims.device, claims.source, claims.item) == (DEVICE, "1", ITEM)
    rec = result.record
    assert (rec.outcome, rec.mapping_id, rec.entry_id, rec.source_id, rec.item) == (
        "played",
        1,
        1,
        1,
        ITEM,
    )
    assert rec.uid == "04:AA:BB:CC"
    assert rec.correlation_id == "b1"
    assert result.entry_status == {1: "ok"}


async def test_slug_lookup_is_trimmed_and_case_folded(svc):
    result = await _handle(svc, "  Boop/Item ")
    assert isinstance(result.response, Play)
    assert result.record.slug == "Boop/Item"


async def test_collection_expands_to_member(svc):
    result = await _handle(svc, "boop/collection")
    assert _claims(result.response).item == "member-x"
    assert result.record.entry_id == 2
    assert result.entry_status == {2: "ok"}


async def test_empty_collection_is_item_unavailable_and_marked(svc):
    result = await _handle(svc, "boop/empty")
    assert result.response.code is ErrorCode.item_unavailable
    assert result.record.outcome == "item_unavailable"
    assert result.entry_status == {3: "missing"}


async def test_random_pick_reaches_every_entry_and_is_seeded(svc):
    picks = {
        _claims((await _handle(svc, "boop/multi", seed=s)).response).item
        for s in range(8)
    }
    assert picks == {"item-a", "item-b"}
    first = await _handle(svc, "boop/multi", seed=3)
    again = await _handle(svc, "boop/multi", seed=3)
    assert _claims(first.response).item == _claims(again.response).item


async def test_sequential_always_plays_first(svc):
    run_sql(svc.env.db_path, "UPDATE mappings SET play_order = 'sequential'")
    for seed in range(5):
        result = await _handle(svc, "boop/multi", seed=seed)
        assert _claims(result.response).item == "item-a"


async def test_unknown_slug(svc):
    result = await _handle(svc, "boop/nope")
    assert result.response.code is ErrorCode.unknown_tag
    assert result.response.boop.slug == "boop/nope"
    assert result.record.outcome == "unknown_tag"
    assert result.record.mapping_id is None
    assert result.record.uid == "04:AA:BB:CC"


async def test_out_of_scope_is_logged_but_answered_as_unknown_tag(svc):
    db_path = svc.env.db_path
    add_device(db_path, "boop-other")
    add_mapping(db_path, 5, "boop/kitchen", all_devices=False, devices=("boop-other",))
    add_entry(db_path, 6, 5, 1, ITEM)

    result = await _handle(svc, "boop/kitchen")
    assert result.response.code is ErrorCode.unknown_tag
    assert result.record.outcome == "out_of_scope"
    assert result.record.mapping_id == 5

    listed = await _handle(svc, "boop/kitchen", device="boop-other")
    assert isinstance(listed.response, Play)


async def test_parked_mapping_resolves_nowhere(svc):
    add_mapping(svc.env.db_path, 5, "boop/parked", all_devices=False)
    add_entry(svc.env.db_path, 6, 5, 1, ITEM)
    result = await _handle(svc, "boop/parked")
    assert result.record.outcome == "out_of_scope"


async def test_empty_mapping_is_item_unavailable(svc):
    add_mapping(svc.env.db_path, 5, "boop/new")
    result = await _handle(svc, "boop/new")
    assert result.response.code is ErrorCode.item_unavailable


@pytest.mark.parametrize(
    "change", ["enabled = 0", "deleted_at = '2026-11-13T09:30:00.000Z'"]
)
async def test_unusable_source_is_source_unavailable(svc, change):
    run_sql(svc.env.db_path, f"UPDATE media_sources SET {change}")
    result = await _handle(svc, "boop/item")
    assert result.response.code is ErrorCode.source_unavailable
    assert result.entry_status == {}


async def test_unreachable_source_is_source_unavailable_and_not_marked(svc):
    sources = StubSources({1: _fake(fail_with=ErrorCode.source_unavailable)})
    result = await _handle(svc, "boop/multi", sources=sources)
    assert result.response.code is ErrorCode.source_unavailable
    assert result.entry_status == {}


async def test_missing_item_is_marked_and_next_entry_plays(svc):
    run_sql(svc.env.db_path, "UPDATE mappings SET play_order = 'sequential'")
    fake = _fake()
    fake.items.discard("item-a")
    result = await _handle(svc, "boop/multi", sources=StubSources({1: fake}))
    assert _claims(result.response).item == "item-b"
    assert result.entry_status == {4: "missing", 5: "ok"}


async def test_missing_entries_are_skipped_then_retried(svc):
    db_path = svc.env.db_path
    run_sql(db_path, "UPDATE mappings SET play_order = 'sequential'")
    run_sql(db_path, "UPDATE mapping_entries SET status = 'missing' WHERE id = 4")
    skipped = await _handle(svc, "boop/multi")
    assert _claims(skipped.response).item == "item-b"

    run_sql(db_path, "UPDATE mapping_entries SET status = 'missing' WHERE id = 5")
    recovered = await _handle(svc, "boop/multi")
    assert _claims(recovered.response).item == "item-a"
    assert recovered.entry_status == {4: "ok"}


async def test_unsupported_version_is_answered_and_logged_without_tag(svc):
    raw = json.dumps({"v": PROTOCOL_VERSION + 1, "id": "b9", "slug": "x"}).encode()
    result = await _handle(svc, "", raw=raw)
    assert result.response.code is ErrorCode.unsupported_version
    assert (result.response.boop.id, result.response.boop.slug) == ("b9", "x")
    assert result.record.outcome == "unsupported_version"
    assert result.record.uid is None and result.record.slug is None


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff not json",
        json.dumps({"v": PROTOCOL_VERSION, "id": "b1"}).encode(),
        _boop_bytes("boop/item", uid="not-hex"),
        json.dumps(
            {"v": 1, "id": "x" * 65, "slug": "s", "uid": "04", "ts": 1}
        ).encode(),
    ],
    ids=["undecodable", "missing fields", "bad uid", "long id"],
)
async def test_unreadable_payload_is_answered_but_not_logged(svc, raw):
    result = await _handle(svc, "", raw=raw)
    assert result.response.code is ErrorCode.unsupported_version
    assert result.record is None


def test_normalize_uid():
    assert normalize_uid("04aabbcc") == "04:AA:BB:CC"
    assert normalize_uid(" 04:a2:2b ") == "04:A2:2B"
    assert normalize_uid("04-a2") == "04:A2"
    assert normalize_uid("zz") is None
    assert normalize_uid("") is None
    assert normalize_uid("0" * 34) is None


def test_box_time_rejects_unset_or_future_clocks():
    now = 1_800_000_000
    assert box_time(0, now) is None
    assert box_time(now + 2 * 86400, now) is None
    assert box_time(1700000000, now) == "2023-11-14T22:13:20.000Z"


# --- service: gating, publishing and recording ---


class _CapturingClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, topic, payload=None, *args, **kwargs) -> None:
        self.published.append((topic, payload))


class _Message:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = type("T", (), {"value": topic})()
        self.payload = payload


def _service(svc, sources=None) -> MqttService:
    return MqttService(
        svc.db, svc.settings, sources or StubSources({1: _fake()}), rng=random.Random(0)
    )


async def _dispatch(service, topic, payload) -> _CapturingClient:
    client = _CapturingClient()
    await service._dispatch(client, _Message(topic, payload))
    return client


async def test_dispatch_publishes_one_play_and_records(svc):
    client = await _dispatch(
        _service(svc), "boopbox/boop-test/boop", _boop_bytes("boop/item")
    )
    assert len(client.published) == 1
    topic, payload = client.published[0]
    assert topic == "boopbox/boop-test/play"
    assert Play.model_validate_json(payload).boop.slug == "boop/item"

    db_path = svc.env.db_path
    assert query(db_path, "SELECT outcome, mapping_id, entry_id, item FROM boops") == [
        ("played", 1, 1, ITEM)
    ]
    assert query(db_path, "SELECT uid, first_slug, last_slug FROM tags") == [
        ("04:AA:BB:CC", "boop/item", "boop/item")
    ]
    assert query(db_path, "SELECT status FROM mapping_entries WHERE id = 1") == [
        ("ok",)
    ]
    last_seen, updated = query(
        db_path, "SELECT last_seen_at, updated_at FROM devices WHERE id = ?", (DEVICE,)
    )[0]
    assert last_seen is not None
    assert updated == "2026-11-13T09:30:00.000Z"


async def test_dispatch_publishes_one_error_and_records_unmapped_tag(svc):
    client = await _dispatch(
        _service(svc), "boopbox/boop-test/boop", _boop_bytes("boop/nope")
    )
    assert [t for t, _ in client.published] == ["boopbox/boop-test/error"]
    err = Error.model_validate_json(client.published[0][1])
    assert err.code is ErrorCode.unknown_tag
    assert query(svc.env.db_path, "SELECT last_slug FROM tags") == [("boop/nope",)]


async def test_tag_keeps_first_sighting_and_tracks_last(svc):
    service = _service(svc)
    add_device(svc.env.db_path, "boop-two")
    await _dispatch(service, "boopbox/boop-test/boop", _boop_bytes("boop/item"))
    await _dispatch(service, "boopbox/boop-two/boop", _boop_bytes("Boop/Rewritten"))
    rows = query(
        svc.env.db_path,
        "SELECT first_slug, first_seen_device_id, last_slug, last_seen_device_id "
        "FROM tags",
    )
    assert rows == [("boop/item", DEVICE, "Boop/Rewritten", "boop-two")]
    assert query(svc.env.db_path, "SELECT count(*) FROM boops") == [(2,)]


@pytest.mark.parametrize(
    "device",
    [
        {"device_id": "boop-revoked", "revoked": True},
        {"device_id": "boop-gone", "deleted": True},
        None,
    ],
    ids=["revoked", "deleted", "unknown"],
)
async def test_inactive_devices_are_dropped_silently(svc, device):
    device_id = device["device_id"] if device else "boop-stranger"
    if device:
        add_device(svc.env.db_path, **device)
    client = await _dispatch(
        _service(svc), f"boopbox/{device_id}/boop", _boop_bytes("boop/item")
    )
    assert client.published == []
    db_path = svc.env.db_path
    assert query(db_path, "SELECT count(*) FROM boops") == [(0,)]
    assert query(db_path, "SELECT count(*) FROM tags") == [(0,)]
    assert query(
        db_path, "SELECT last_seen_at FROM devices WHERE id = ?", (device_id,)
    ) in ([], [(None,)])


async def test_oversized_payload_is_dropped(svc):
    raw = _boop_bytes("boop/item")[:-1] + b" " * 4096 + b"}"
    client = await _dispatch(_service(svc), "boopbox/boop-test/boop", raw)
    assert client.published == []
    assert query(svc.env.db_path, "SELECT count(*) FROM boops") == [(0,)]


async def test_dispatch_ignores_unexpected_topic(svc):
    client = await _dispatch(_service(svc), "boopbox/boop-test/play", b"{}")
    assert client.published == []


def test_device_id_from_topic():
    assert device_id_from_topic("boopbox/abc/boop") == "abc"
    assert device_id_from_topic("boopbox/abc/play") is None
    assert device_id_from_topic("boopbox/abc/version") is None
    assert device_id_from_topic("boopbox/a/b/boop") is None


async def test_client_is_built_from_settings(svc):
    values = await svc.settings.snapshot()
    values.update({"mqtt.host": "broker.example", "mqtt.port": 8883})
    client = _build_client(values)
    assert (client._hostname, client._port) == ("broker.example", 8883)


# --- commands and version replies ---


async def test_publish_cmd_per_device_and_broadcast():
    client = _CapturingClient()
    cmd = Cmd(cmd=CmdName.get_version)
    await publish_cmd(client, "boop-test", cmd)
    await publish_cmd(client, "all", cmd)
    assert client.published[0][0] == "boopbox/boop-test/cmd"
    assert client.published[1][0] == "boopbox/all/cmd"
    for _, payload in client.published:
        assert json.loads(payload) == {"v": PROTOCOL_VERSION, "cmd": "get_version"}


async def test_flash_command_shape_per_device():
    client = _CapturingClient()
    flash = FlashCmd(url="/firmware/esp32s3/boopbox-0.2.0.bin", md5="abc123")
    await publish_flash(client, "boop-test", flash)
    topic, payload = client.published[0]
    assert topic == "boopbox/boop-test/cmd"
    body = json.loads(payload)
    assert body["cmd"] == "flash"
    assert body["url"] == "/firmware/esp32s3/boopbox-0.2.0.bin"
    assert body["md5"] == "abc123"


async def test_send_requires_connection(svc):
    service = _service(svc)
    flash = FlashCmd(url="/firmware/esp32s3/boopbox-0.2.0.bin", md5="abc123")
    with pytest.raises(RuntimeError):
        await service.send_cmd("boop-test", Cmd(cmd=CmdName.get_version))
    with pytest.raises(RuntimeError):
        await service.send_flash("boop-test", flash)
    service.client = _CapturingClient()
    await service.send_cmd("boop-test", Cmd(cmd=CmdName.get_version))
    await service.send_flash("boop-test", flash)
    assert [t for t, _ in service.client.published] == ["boopbox/boop-test/cmd"] * 2


def _version_bytes(firmware: str, chip: str, *, v: int = PROTOCOL_VERSION) -> bytes:
    return json.dumps({"v": v, "firmware": firmware, "chip": chip}).encode()


def test_parse_version_reply():
    reply = parse_version_reply("boop-test", _version_bytes("0.1.0", "esp32s3"))
    assert isinstance(reply, VersionReply)
    assert (reply.firmware, reply.chip) == ("0.1.0", "esp32s3")
    unsupported = _version_bytes("0.1.0", "esp32s3", v=PROTOCOL_VERSION + 1)
    assert parse_version_reply("boop-test", unsupported) is None
    assert parse_version_reply("boop-test", b"\xff not json") is None
    assert parse_version_reply("boop-test", json.dumps({"v": 1}).encode()) is None
    too_long = _version_bytes("1." * 17, "esp32s3")
    assert parse_version_reply("boop-test", too_long) is None


async def test_version_reply_stamps_firmware_and_reaches_policy(svc):
    service = _service(svc)
    seen = []

    async def on_reply(device_id, reply):
        seen.append((device_id, reply.firmware))

    service.on_version_reply = on_reply
    client = await _dispatch(
        service, "boopbox/boop-test/version", _version_bytes("0.4.2", "esp32s3")
    )
    assert client.published == []
    assert seen == [("boop-test", "0.4.2")]
    assert query(
        svc.env.db_path,
        "SELECT firmware_version, last_seen_at IS NOT NULL, updated_at FROM devices",
    ) == [("0.4.2", 1, "2026-11-13T09:30:00.000Z")]


async def test_bad_version_reply_no_stamp_no_handler(svc):
    service = _service(svc)
    called = []
    service.on_version_reply = lambda d, r: called.append((d, r))
    await _dispatch(service, "boopbox/boop-test/version", b"\xff not json")
    await _dispatch(
        service, "boopbox/boop-test/version", _version_bytes("x" * 33, "esp32s3")
    )
    assert called == []
    assert query(svc.env.db_path, "SELECT firmware_version FROM devices") == [(None,)]


async def test_no_cross_talk_boop_vs_version(svc):
    service = _service(svc)
    seen = []

    async def on_reply(device_id, reply):
        seen.append(device_id)

    service.on_version_reply = on_reply
    boop = await _dispatch(service, "boopbox/boop-test/boop", _boop_bytes("boop/item"))
    assert [t for t, _ in boop.published] == ["boopbox/boop-test/play"]
    assert seen == []
    version = await _dispatch(
        service, "boopbox/boop-test/version", _version_bytes("0.1.0", "esp32s3")
    )
    assert version.published == []
    assert seen == ["boop-test"]
