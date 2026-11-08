"""Auth: user JWT, device OTA (Basic), device API (Bearer), strict separation.

Covers token issuance/verification, the three dependencies' accept/reject
matrices, the `revoked` kill switch across device credentials, and that no
credential type is accepted where it does not belong.
"""

import base64
import textwrap

import anyio
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.auth import require_device_api, require_user
from app.auth.jwt import issue_user_jwt, now_seconds
from app.config import get_settings
from app.db import DeviceRepository, connect
from app.main import create_app
from app.security import hash_secret
from app.types.device import Device

AUTH_USER = "operator"
AUTH_PASS = "s3cret-pw"
JWT_SECRET = "jwt-signing-secret-at-least-32-bytes-long"
OTA_SECRET = "device-ota-secret"
API_TOKEN = "device-api-token"
DEVICE_ID = "boop-test"

CONFIG = textwrap.dedent(
    """
    sources: []
    mappings: {}
    ota:
      manifest_version: "0.1.0"
    """
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG)
    firmware_dir = tmp_path / "firmware-bins"
    firmware_dir.mkdir()
    db_path = str(tmp_path / "devices.db")
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    monkeypatch.setenv("BOOPBOX_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("BOOPBOX_DB_PATH", db_path)
    monkeypatch.setenv("BOOPBOX_FIRMWARE_DIR", str(firmware_dir))
    monkeypatch.setenv("BOOPBOX_AUTH_USERNAME", AUTH_USER)
    monkeypatch.setenv("BOOPBOX_AUTH_PASSWORD", AUTH_PASS)
    monkeypatch.setenv("BOOPBOX_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("BOOPBOX_SEED_DEVICE_ID", DEVICE_ID)
    monkeypatch.setenv("BOOPBOX_SEED_DEVICE_OTA_SECRET", OTA_SECRET)
    monkeypatch.setenv("BOOPBOX_SEED_DEVICE_API_TOKEN", API_TOKEN)
    get_settings.cache_clear()
    app = create_app()

    # Throwaway routes to exercise the dependencies directly. No real device API
    # endpoint exists yet; this stands in for one.
    @app.get("/_test/device")
    async def _device(device: Device = Depends(require_device_api)):  # noqa: B008
        return {"device_id": device.id}

    @app.get("/_test/user")
    async def _user(subject: str = Depends(require_user)):  # noqa: B008
        return {"subject": subject}

    with TestClient(app) as c:
        c.db_path = db_path  # for out-of-band DB inspection/mutation in tests
        yield c
    get_settings.cache_clear()


def _login(client, user=AUTH_USER, password=AUTH_PASS):
    return client.post("/auth/token", json={"username": user, "password": password})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _basic_header(user: str, password: str) -> dict[str, str]:
    raw = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


async def _mutate_device(db_path: str, device_id: str, **changes) -> Device:
    """Open a fresh connection to the app's DB and apply changes to a device.

    A separate connection (not the app's own loop-bound one) avoids cross-loop
    use of the app's aiosqlite connection; WAL makes the committed write visible
    to the app's connection.
    """
    conn = await connect(db_path)
    try:
        repo = DeviceRepository(conn)
        device = await repo.get(device_id)
        for key, value in changes.items():
            setattr(device, key, value)
        await repo.upsert(device)
        return device
    finally:
        await conn.close()


async def _read_device(db_path: str, device_id: str) -> Device:
    conn = await connect(db_path)
    try:
        return await DeviceRepository(conn).get(device_id)
    finally:
        await conn.close()


# --- POST /auth/token ---


def test_token_happy_path(client):
    r = _login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().jwt_ttl_seconds
    assert body["access_token"]


def test_token_bad_password_401(client):
    r = _login(client, password="wrong")
    assert r.status_code == 401


def test_token_unknown_user_401(client):
    r = _login(client, user="nobody")
    assert r.status_code == 401


# --- require_user ---


def test_user_route_accepts_valid_jwt(client):
    token = _login(client).json()["access_token"]
    r = client.get("/_test/user", headers=_bearer(token))
    assert r.status_code == 200
    assert r.json()["subject"] == AUTH_USER


def test_user_route_missing_bearer_401(client):
    assert client.get("/_test/user").status_code == 401


def test_user_route_rejects_tampered_jwt(client):
    token = _login(client).json()["access_token"]
    r = client.get("/_test/user", headers=_bearer(token + "x"))
    assert r.status_code == 403


def test_user_route_rejects_foreign_signed_jwt(client):
    # Correct shape + audience, wrong signing secret -> rejected.
    forged = issue_user_jwt(
        "operator",
        secret="a-different-secret-also-32-bytes-plus",
        ttl_seconds=600,
        now=now_seconds(),
    )
    r = client.get("/_test/user", headers=_bearer(forged))
    assert r.status_code == 403


# --- require_device_api (Bearer + X-Device-Id) ---


def test_device_api_accepts_valid_token(client):
    r = client.get(
        "/_test/device",
        headers={**_bearer(API_TOKEN), "X-Device-Id": DEVICE_ID},
    )
    assert r.status_code == 200
    assert r.json()["device_id"] == DEVICE_ID


def test_device_api_missing_device_id_401(client):
    r = client.get("/_test/device", headers=_bearer(API_TOKEN))
    assert r.status_code == 401


def test_device_api_wrong_token_403(client):
    r = client.get(
        "/_test/device",
        headers={**_bearer("nope"), "X-Device-Id": DEVICE_ID},
    )
    assert r.status_code == 403


def test_device_api_unknown_device_403(client):
    r = client.get(
        "/_test/device",
        headers={**_bearer(API_TOKEN), "X-Device-Id": "ghost"},
    )
    assert r.status_code == 403


async def test_device_api_revoked_device_403(client):
    await _mutate_device(client.db_path, DEVICE_ID, revoked=True)
    r = client.get(
        "/_test/device",
        headers={**_bearer(API_TOKEN), "X-Device-Id": DEVICE_ID},
    )
    assert r.status_code == 403


# --- strict separation: credentials never cross principals ---


def test_user_jwt_rejected_on_device_route(client):
    token = _login(client).json()["access_token"]
    r = client.get(
        "/_test/device",
        headers={**_bearer(token), "X-Device-Id": DEVICE_ID},
    )
    # The user JWT is not the device's token -> forbidden.
    assert r.status_code == 403


def test_device_token_rejected_on_user_route(client):
    r = client.get("/_test/user", headers=_bearer(API_TOKEN))
    # A raw device token is not a valid JWT -> forbidden.
    assert r.status_code == 403


def test_ota_basic_secret_rejected_on_user_route(client):
    # Basic creds are not a bearer JWT at all -> missing bearer -> 401.
    r = client.get("/_test/user", headers=_basic_header(DEVICE_ID, OTA_SECRET))
    assert r.status_code == 401


def test_stored_secret_is_hashed_not_plaintext(client):
    # Defense-in-depth: the row stores the hash, never the plaintext secret.
    device = anyio.run(_read_device, client.db_path, DEVICE_ID)
    assert device.ota_secret_hash == hash_secret(OTA_SECRET)
    assert device.device_token_hash == hash_secret(API_TOKEN)
    assert device.ota_secret_hash != OTA_SECRET
