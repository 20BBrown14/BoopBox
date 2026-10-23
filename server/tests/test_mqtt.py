import json
import random
import textwrap
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import Settings
from app.db import DeviceRepository, connect, init_schema, seed_device
from app.errors import ErrorCode
from app.models import Boop, Cmd, CmdName, Error, Play
from app.mqtt.handler import build_response
from app.mqtt.publish import publish_cmd
from app.mqtt.service import MqttService, device_id_from_topic
from app.protocol import PROTOCOL_VERSION
from app.sources import FakeSource, SourceRegistry
from app.stream_token import verify

SECRET = "s3cret"
DEVICE = "boop-test"
ITEM = "fake-item"

# A config with: an item slug, a collection slug, an empty-collection slug, and a
# multi-entry slug. All reference the single fake source.
CONFIG = textwrap.dedent(
    """
    sources:
      - id: fake-main
        type: fake
        base_url: http://unused
    mappings:
      "boop/item":
        - source: fake-main
          item: fake-item
          kind: item
      "boop/collection":
        - source: fake-main
          item: col-1
          kind: collection
      "boop/empty":
        - source: fake-main
          item: col-empty
          kind: collection
      "boop/multi":
        - source: fake-main
          item: item-a
          kind: item
        - source: fake-main
          item: item-b
          kind: item
    """
)


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", SECRET)
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return Settings(
        _env_file=None,
        config_path=str(path),
        stream_secret=SECRET,
        public_base_url="https://boop.example/base",
    )


def _fake_registry(**kwargs) -> SourceRegistry:
    # One fake source that knows every item used in the config, with members for
    # the collection slug. known_item is widened so item/member reads pass.
    fake = FakeSource(
        known_item=ITEM,
        collections={"col-1": ["member-x"], "col-empty": []},
        **kwargs,
    )
    return SourceRegistry({"fake-main": fake})


def _boop_bytes(slug: str, *, v: int = PROTOCOL_VERSION, bid: str = "b1") -> bytes:
    return Boop(
        v=v, id=bid, slug=slug, uid="04aabbcc", ts=1700000000
    ).model_dump_json().encode()


# --- handler: build_response (the flow + single-response guarantee) ---


async def test_happy_path_item_slug(settings):
    registry = _fake_registry()
    rng = random.Random(0)
    resp = await build_response(
        DEVICE, _boop_bytes("boop/item"), settings, registry, rng=rng
    )
    assert isinstance(resp, Play)
    assert resp.boop is not None
    assert resp.boop.id == "b1"
    assert resp.boop.slug == "boop/item"
    assert resp.duration == 180

    parsed = urlparse(resp.url)
    assert resp.url.startswith("https://boop.example/base/stream?sig=")
    token = parse_qs(parsed.query)["sig"][0]
    claims = verify(token, now=int(time.time()), secret=SECRET)
    assert not isinstance(claims, ErrorCode)
    assert claims.device == DEVICE
    assert claims.source == "fake-main"
    assert claims.item == ITEM


async def test_collection_slug_expands_to_member(settings):
    # The collection col-1 has one member (member-x); widen the fake to know it.
    fake = FakeSource(
        known_item="member-x", collections={"col-1": ["member-x"]}
    )
    registry = SourceRegistry({"fake-main": fake})
    resp = await build_response(
        DEVICE,
        _boop_bytes("boop/collection"),
        settings,
        registry,
        rng=random.Random(0),
    )
    assert isinstance(resp, Play)
    token = parse_qs(urlparse(resp.url).query)["sig"][0]
    claims = verify(token, now=int(time.time()), secret=SECRET)
    assert not isinstance(claims, ErrorCode)
    assert claims.item == "member-x"


async def test_empty_collection_is_item_unavailable(settings):
    registry = _fake_registry()
    resp = await build_response(
        DEVICE, _boop_bytes("boop/empty"), settings, registry, rng=random.Random(0)
    )
    assert isinstance(resp, Error)
    assert resp.code is ErrorCode.item_unavailable
    assert resp.boop is not None
    assert resp.boop.slug == "boop/empty"


async def test_multi_entry_pick_is_deterministic_with_seed(settings):
    # Two item entries (item-a, item-b); the fake accepts both.
    class _Multi(FakeSource):
        def _guard(self, item):
            if item not in {"item-a", "item-b"}:
                from app.types.source import SourceError

                raise SourceError(ErrorCode.item_unavailable)

    registry = SourceRegistry({"fake-main": _Multi()})

    picks = set()
    for seed in range(8):
        resp = await build_response(
            DEVICE,
            _boop_bytes("boop/multi"),
            settings,
            registry,
            rng=random.Random(seed),
        )
        assert isinstance(resp, Play)
        token = parse_qs(urlparse(resp.url).query)["sig"][0]
        claims = verify(token, now=int(time.time()), secret=SECRET)
        picks.add(claims.item)

    # Both entries are reachable across seeds (uniform pick), and a fixed seed is
    # reproducible.
    assert picks == {"item-a", "item-b"}
    first = await build_response(
        DEVICE, _boop_bytes("boop/multi"), settings, registry, rng=random.Random(3)
    )
    again = await build_response(
        DEVICE, _boop_bytes("boop/multi"), settings, registry, rng=random.Random(3)
    )
    t1 = parse_qs(urlparse(first.url).query)["sig"][0]
    t2 = parse_qs(urlparse(again.url).query)["sig"][0]
    c1 = verify(t1, now=int(time.time()), secret=SECRET)
    c2 = verify(t2, now=int(time.time()), secret=SECRET)
    assert c1.item == c2.item


async def test_unknown_slug_is_unknown_tag(settings):
    registry = _fake_registry()
    resp = await build_response(
        DEVICE, _boop_bytes("boop/nope"), settings, registry, rng=random.Random(0)
    )
    assert isinstance(resp, Error)
    assert resp.code is ErrorCode.unknown_tag
    assert resp.boop is not None
    assert resp.boop.id == "b1"
    assert resp.boop.slug == "boop/nope"


async def test_unsupported_version_best_effort_ref(settings):
    registry = _fake_registry()
    raw = json.dumps(
        {"v": PROTOCOL_VERSION + 1, "id": "b9", "slug": "boop/item"}
    ).encode()
    resp = await build_response(DEVICE, raw, settings, registry, rng=random.Random(0))
    assert isinstance(resp, Error)
    assert resp.code is ErrorCode.unsupported_version
    # Best-effort ref: id/slug parseable before the unknown v.
    assert resp.boop is not None
    assert resp.boop.id == "b9"
    assert resp.boop.slug == "boop/item"


async def test_undecodable_payload_is_unsupported_version(settings):
    registry = _fake_registry()
    resp = await build_response(
        DEVICE, b"\xff not json", settings, registry, rng=random.Random(0)
    )
    assert isinstance(resp, Error)
    assert resp.code is ErrorCode.unsupported_version


# --- service: dispatch publishes exactly one message + last_seen ---


class _CapturingClient:
    """Stands in for the aiomqtt client; records every publish."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, topic, payload=None, *args, **kwargs) -> None:
        self.published.append((topic, payload))


class _Message:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = type("T", (), {"value": topic})()
        self.payload = payload


@pytest.fixture
async def devices(tmp_path):
    conn = await connect(str(tmp_path / "devices.db"))
    await init_schema(conn)
    repo = DeviceRepository(conn)
    await seed_device(repo, DEVICE)
    try:
        yield repo
    finally:
        await conn.close()


def _service(settings, registry, devices) -> MqttService:
    return MqttService(settings, registry, devices, rng=random.Random(0))


async def test_dispatch_publishes_single_play(settings, devices):
    svc = _service(settings, _fake_registry(), devices)
    client = _CapturingClient()
    await svc._dispatch(
        client, _Message("boopbox/boop-test/boop", _boop_bytes("boop/item"))
    )

    assert len(client.published) == 1
    topic, payload = client.published[0]
    assert topic == "boopbox/boop-test/play"
    play = Play.model_validate_json(payload)
    assert play.boop.slug == "boop/item"


async def test_dispatch_publishes_single_error(settings, devices):
    svc = _service(settings, _fake_registry(), devices)
    client = _CapturingClient()
    await svc._dispatch(
        client, _Message("boopbox/boop-test/boop", _boop_bytes("boop/nope"))
    )

    assert len(client.published) == 1
    topic, payload = client.published[0]
    assert topic == "boopbox/boop-test/error"
    err = Error.model_validate_json(payload)
    assert err.code is ErrorCode.unknown_tag


async def test_dispatch_updates_last_seen_off_loop(settings, devices):
    before = (await devices.get(DEVICE)).last_seen_at
    assert before is None

    svc = _service(settings, _fake_registry(), devices)
    client = _CapturingClient()
    await svc._dispatch(
        client, _Message("boopbox/boop-test/boop", _boop_bytes("boop/item"))
    )

    after = (await devices.get(DEVICE)).last_seen_at
    assert after is not None


async def test_dispatch_ignores_unexpected_topic(settings, devices):
    svc = _service(settings, _fake_registry(), devices)
    client = _CapturingClient()
    await svc._dispatch(client, _Message("boopbox/boop-test/play", b"{}"))
    assert client.published == []


def test_device_id_from_topic():
    assert device_id_from_topic("boopbox/abc/boop") == "abc"
    assert device_id_from_topic("boopbox/abc/play") is None
    assert device_id_from_topic("boopbox/a/b/boop") is None


# --- publish_cmd: per-device + broadcast ---


async def test_publish_cmd_per_device_and_broadcast():
    client = _CapturingClient()
    cmd = Cmd(cmd=CmdName.check_update)

    await publish_cmd(client, "boop-test", cmd)
    await publish_cmd(client, "all", cmd)

    assert client.published[0][0] == "boopbox/boop-test/cmd"
    assert client.published[1][0] == "boopbox/all/cmd"
    for _, payload in client.published:
        parsed = Cmd.model_validate_json(payload)
        assert parsed.cmd is CmdName.check_update
        assert parsed.v == PROTOCOL_VERSION


async def test_send_cmd_requires_connection(settings, devices):
    svc = _service(settings, _fake_registry(), devices)
    with pytest.raises(RuntimeError):
        await svc.send_cmd("boop-test", Cmd(cmd=CmdName.check_update))

    # When connected, it publishes through the live client.
    svc.client = _CapturingClient()
    await svc.send_cmd("boop-test", Cmd(cmd=CmdName.check_update))
    assert svc.client.published[0][0] == "boopbox/boop-test/cmd"
