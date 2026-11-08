import hashlib
import os
import textwrap
import time

import pytest
from fastapi.testclient import TestClient

from app import firmware as firmware_mod
from app.config import get_settings
from app.firmware import FirmwareCache
from app.main import create_app

VERSION = "0.1.0"
CONFIG = textwrap.dedent(
    f"""
    sources: []
    mappings: {{}}
    ota:
      manifest_version: "{VERSION}"
    """
)


def _write_bin(firmware_dir, chip: str, version: str, data: bytes) -> None:
    chip_dir = firmware_dir / chip
    chip_dir.mkdir(parents=True, exist_ok=True)
    (chip_dir / f"boopbox-{version}.bin").write_bytes(data)


@pytest.fixture
def firmware_dir(tmp_path):
    d = tmp_path / "firmware-bins"
    d.mkdir()
    return d


OTA_SECRET = "seed-ota-secret"


@pytest.fixture
def client(tmp_path, firmware_dir, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG)
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    monkeypatch.setenv("BOOPBOX_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("BOOPBOX_DB_PATH", str(tmp_path / "devices.db"))
    monkeypatch.setenv("BOOPBOX_FIRMWARE_DIR", str(firmware_dir))
    monkeypatch.setenv("BOOPBOX_SEED_DEVICE_OTA_SECRET", OTA_SECRET)
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _ota_auth():
    """HTTP Basic auth for the seed device's OTA bin fetch."""
    return (get_settings().seed_device_id, OTA_SECRET)


# --- Generator / index unit tests (no HTTP) ---


def test_md5_matches_disk(firmware_dir):
    data = bytes(range(256)) * 4
    _write_bin(firmware_dir, "esp32s3", VERSION, data)
    cache = FirmwareCache(firmware_dir, VERSION)
    entry = cache.index("esp32s3")
    assert entry is not None
    assert entry.md5 == hashlib.md5(data).hexdigest()


def test_version_from_config_not_filename(firmware_dir):
    # Bin named for 2.0.0 on disk, but config version is 0.1.0 -> no match.
    _write_bin(firmware_dir, "esp32s3", "2.0.0", b"wrong-version")
    _write_bin(firmware_dir, "esp32s3", VERSION, b"right-version")
    cache = FirmwareCache(firmware_dir, VERSION)
    manifest = cache.manifest()
    assert manifest["version"] == VERSION
    entry = cache.index("esp32s3")
    assert entry is not None
    assert entry.version == VERSION
    assert entry.path == f"/firmware/esp32s3/boopbox-{VERSION}.bin"


def test_per_chip_entries_and_skip(firmware_dir):
    _write_bin(firmware_dir, "esp32s3", VERSION, b"aaa")
    # A second known chip would need to be in CHIP_FAMILIES; emulate by adding
    # one to the mapping for the duration of the test.
    firmware_mod.CHIP_FAMILIES["esp32c3"] = "ESP32-C3"
    try:
        _write_bin(firmware_dir, "esp32c3", VERSION, b"bbb")
        # A chip dir without the versioned bin is skipped.
        (firmware_dir / "esp32c6").mkdir()
        cache = FirmwareCache(firmware_dir, VERSION)
        builds = cache.manifest()["builds"]
        families = {b["chipFamily"] for b in builds}
        assert families == {"ESP32-S3", "ESP32-C3"}
        assert cache.index("esp32s3") is not None
        assert cache.index("esp32c3") is not None
        assert cache.index("esp32c6") is None
        for b in builds:
            assert b["ota"]["path"].startswith("/firmware/")
    finally:
        del firmware_mod.CHIP_FAMILIES["esp32c3"]


def test_empty_builds_when_no_bins(firmware_dir):
    cache = FirmwareCache(firmware_dir, VERSION)
    manifest = cache.manifest()
    assert manifest["builds"] == []
    assert manifest["version"] == VERSION
    assert cache.index("esp32s3") is None


def test_index_lookup_present_and_absent(firmware_dir):
    _write_bin(firmware_dir, "esp32s3", VERSION, b"data")
    cache = FirmwareCache(firmware_dir, VERSION)
    entry = cache.index("esp32s3")
    assert entry is not None
    assert entry.version == VERSION
    assert entry.path.startswith("/")
    assert entry.md5
    assert cache.index("esp32c3") is None


def test_absolute_paths(firmware_dir):
    _write_bin(firmware_dir, "esp32s3", VERSION, b"data")
    cache = FirmwareCache(firmware_dir, VERSION)
    assert cache.manifest()["builds"][0]["ota"]["path"].startswith("/")
    assert cache.index("esp32s3").path.startswith("/")


def test_cache_invalidation_on_mtime(firmware_dir, monkeypatch):
    data = b"first"
    _write_bin(firmware_dir, "esp32s3", VERSION, data)
    cache = FirmwareCache(firmware_dir, VERSION)
    first_md5 = cache.index("esp32s3").md5

    calls = {"n": 0}
    real_md5 = firmware_mod._md5_of

    def counting_md5(path):
        calls["n"] += 1
        return real_md5(path)

    monkeypatch.setattr(firmware_mod, "_md5_of", counting_md5)
    cache.manifest()
    cache.index("esp32s3")
    assert calls["n"] == 0

    # Change the bin + bump mtime -> recompute.
    bin_path = firmware_dir / "esp32s3" / f"boopbox-{VERSION}.bin"
    bin_path.write_bytes(b"second-different")
    future = time.time() + 10
    os.utime(bin_path, (future, future))
    new_md5 = cache.index("esp32s3").md5
    assert calls["n"] >= 1
    assert new_md5 != first_md5
    assert new_md5 == hashlib.md5(b"second-different").hexdigest()


# --- HTTP integration tests ---


def test_manifest_endpoint_shape(client, firmware_dir):
    data = bytes(range(256))
    _write_bin(firmware_dir, "esp32s3", VERSION, data)
    client.app.state.firmware.rebuild()
    r = client.get("/firmware/manifest.json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["name"] == "BoopBox"
    assert body["version"] == VERSION
    assert len(body["builds"]) == 1
    build = body["builds"][0]
    assert build["chipFamily"] == "ESP32-S3"
    assert build["ota"]["md5"] == hashlib.md5(data).hexdigest()
    assert build["ota"]["path"] == f"/firmware/esp32s3/boopbox-{VERSION}.bin"


def test_firmware_served_with_range(client, firmware_dir):
    data = bytes(range(256)) * 8
    _write_bin(firmware_dir, "esp32s3", VERSION, data)
    r = client.get(
        f"/firmware/esp32s3/boopbox-{VERSION}.bin",
        headers={"Range": "bytes=10-19"},
        auth=_ota_auth(),
    )
    assert r.status_code == 206
    assert r.content == data[10:20]
    assert r.headers["content-range"] == f"bytes 10-19/{len(data)}"


def test_firmware_full_fetch(client, firmware_dir):
    data = b"full-bin-bytes"
    _write_bin(firmware_dir, "esp32s3", VERSION, data)
    r = client.get(f"/firmware/esp32s3/boopbox-{VERSION}.bin", auth=_ota_auth())
    assert r.status_code == 200
    assert r.content == data


def test_firmware_requires_auth(client, firmware_dir):
    _write_bin(firmware_dir, "esp32s3", VERSION, b"data")
    r = client.get(f"/firmware/esp32s3/boopbox-{VERSION}.bin")
    assert r.status_code == 401


def test_firmware_wrong_secret_forbidden(client, firmware_dir):
    _write_bin(firmware_dir, "esp32s3", VERSION, b"data")
    r = client.get(
        f"/firmware/esp32s3/boopbox-{VERSION}.bin",
        auth=(get_settings().seed_device_id, "wrong-secret"),
    )
    assert r.status_code == 403


def test_manifest_is_public(client, firmware_dir):
    # The manifest stays reachable without any credential.
    _write_bin(firmware_dir, "esp32s3", VERSION, b"data")
    client.app.state.firmware.rebuild()
    r = client.get("/firmware/manifest.json")
    assert r.status_code == 200


def test_manifest_wins_over_static_file(client, firmware_dir):
    # A stray on-disk manifest.json must not shadow the generated route.
    (firmware_dir / "manifest.json").write_text('{"stray": true}')
    _write_bin(firmware_dir, "esp32s3", VERSION, b"data")
    client.app.state.firmware.rebuild()
    r = client.get("/firmware/manifest.json")
    assert r.status_code == 200
    body = r.json()
    assert "stray" not in body
    assert body["name"] == "BoopBox"
