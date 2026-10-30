"""P11: OTA version-check + push policy and the POST /ota/update endpoint.

Policy unit tests drive OtaPolicy with a real FirmwareCache (over a tmp bin dir)
and a fake publisher that records send_cmd/send_flash. Endpoint tests use a
TestClient and stub app.state.ota_policy to capture the triggered query.
"""

import textwrap

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.firmware import FirmwareCache
from app.main import create_app
from app.models import CmdName, FlashCmd, VersionReply
from app.mqtt.publish import BROADCAST
from app.ota import OtaPolicy

VERSION = "0.2.0"


def _write_bin(firmware_dir, chip: str, version: str, data: bytes) -> None:
    chip_dir = firmware_dir / chip
    chip_dir.mkdir(parents=True, exist_ok=True)
    (chip_dir / f"boopbox-{version}.bin").write_bytes(data)


class _FakePublisher:
    """Records the policy's publish calls without a live MQTT client."""

    def __init__(self) -> None:
        self.cmds: list[tuple[str, CmdName]] = []
        self.flashes: list[tuple[str, FlashCmd]] = []

    async def send_cmd(self, target, cmd) -> None:
        self.cmds.append((target, cmd.cmd))

    async def send_flash(self, device_id, flash) -> None:
        self.flashes.append((device_id, flash))


@pytest.fixture
def firmware_dir(tmp_path):
    d = tmp_path / "firmware-bins"
    d.mkdir()
    return d


def _policy(firmware_dir, publisher, *, auto_push=False) -> OtaPolicy:
    _write_bin(firmware_dir, "esp32s3", VERSION, b"the-bin-bytes")
    cache = FirmwareCache(firmware_dir, VERSION)
    return OtaPolicy(
        cache, VERSION, publisher, auto_push_on_publish=auto_push
    )


# --- policy: compare-and-maybe-flash ---


async def test_stale_reply_flashes_with_index_entry(firmware_dir):
    pub = _FakePublisher()
    policy = _policy(firmware_dir, pub)
    entry = policy._firmware.index("esp32s3")

    await policy.on_version_reply(
        "boop-1", VersionReply(v=1, firmware="0.1.0", chip="esp32s3")
    )

    assert pub.cmds == []
    assert len(pub.flashes) == 1
    device_id, flash = pub.flashes[0]
    assert device_id == "boop-1"
    assert flash.cmd is CmdName.flash
    assert flash.url == entry.path
    assert flash.md5 == entry.md5


async def test_current_reply_no_flash(firmware_dir):
    pub = _FakePublisher()
    policy = _policy(firmware_dir, pub)

    await policy.on_version_reply(
        "boop-1", VersionReply(v=1, firmware=VERSION, chip="esp32s3")
    )

    assert pub.flashes == []
    assert pub.cmds == []


async def test_unknown_chip_no_flash(firmware_dir):
    pub = _FakePublisher()
    policy = _policy(firmware_dir, pub)

    # Stale firmware but a chip with no bin in the index -> no flash, never a
    # wrong-chip guess.
    await policy.on_version_reply(
        "boop-1", VersionReply(v=1, firmware="0.1.0", chip="esp32c3")
    )

    assert pub.flashes == []


# --- policy triggers: query + auto-push ---


async def test_query_version_per_device_and_broadcast(firmware_dir):
    pub = _FakePublisher()
    policy = _policy(firmware_dir, pub)

    await policy.query_version("boop-1")
    await policy.query_version()

    assert pub.cmds == [
        ("boop-1", CmdName.get_version),
        (BROADCAST, CmdName.get_version),
    ]
    assert pub.flashes == []


async def test_auto_push_knob_off_is_inert(firmware_dir):
    pub = _FakePublisher()
    policy = _policy(firmware_dir, pub, auto_push=False)

    await policy.maybe_push_on_publish()

    assert pub.cmds == []
    assert pub.flashes == []


async def test_auto_push_knob_on_broadcasts_query(firmware_dir):
    pub = _FakePublisher()
    policy = _policy(firmware_dir, pub, auto_push=True)

    await policy.maybe_push_on_publish()

    assert pub.cmds == [(BROADCAST, CmdName.get_version)]
    assert pub.flashes == []


# --- endpoint: POST /ota/update triggers query only ---

CONFIG = textwrap.dedent(
    f"""
    sources: []
    mappings: {{}}
    ota:
      manifest_version: "{VERSION}"
    """
)


class _RecordingPolicy:
    def __init__(self) -> None:
        self.queries: list[str | None] = []

    async def query_version(self, device_id=None) -> None:
        self.queries.append(device_id)


AUTH_USER = "admin"
AUTH_PASS = "pw"


@pytest.fixture
def client(tmp_path, firmware_dir, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG)
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    monkeypatch.setenv("BOOPBOX_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("BOOPBOX_DB_PATH", str(tmp_path / "devices.db"))
    monkeypatch.setenv("BOOPBOX_FIRMWARE_DIR", str(firmware_dir))
    monkeypatch.setenv("BOOPBOX_AUTH_USERNAME", AUTH_USER)
    monkeypatch.setenv("BOOPBOX_AUTH_PASSWORD", AUTH_PASS)
    monkeypatch.setenv("BOOPBOX_JWT_SECRET", "jwt-signing-secret-at-least-32-bytes")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _user_headers(client) -> dict[str, str]:
    r = client.post(
        "/auth/token", json={"username": AUTH_USER, "password": AUTH_PASS}
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_update_no_body_broadcasts_query(client):
    recorder = _RecordingPolicy()
    client.app.state.ota_policy = recorder
    r = client.post("/ota/update", headers=_user_headers(client))
    assert r.status_code == 200
    assert r.json()["device_id"] == "all"
    assert recorder.queries == [None]


def test_update_with_device_id_queries_that_device(client):
    recorder = _RecordingPolicy()
    client.app.state.ota_policy = recorder
    # The seed device id is created at startup.
    seed_id = get_settings().seed_device_id
    r = client.post(
        "/ota/update", json={"device_id": seed_id}, headers=_user_headers(client)
    )
    assert r.status_code == 200
    assert r.json()["device_id"] == seed_id
    assert recorder.queries == [seed_id]


def test_update_unknown_device_is_404(client):
    recorder = _RecordingPolicy()
    client.app.state.ota_policy = recorder
    r = client.post(
        "/ota/update",
        json={"device_id": "no-such-device"},
        headers=_user_headers(client),
    )
    assert r.status_code == 404
    assert recorder.queries == []


def test_update_without_auth_is_401(client):
    recorder = _RecordingPolicy()
    client.app.state.ota_policy = recorder
    r = client.post("/ota/update")
    assert r.status_code == 401
    assert recorder.queries == []
