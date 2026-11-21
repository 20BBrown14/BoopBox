import base64
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import get_env
from app.errors import ErrorCode
from app.main import create_app
from app.security import hash_secret
from app.startup import start
from app.types.source import SourceError

T = "2026-11-13T09:30:00.000Z"
SECRET_KEY = base64.urlsafe_b64encode(b"k" * 32).rstrip(b"=").decode()
OWNER = "owner"
OWNER_PASSWORD = "owner-password-123"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A clean environment: no inherited BOOPBOX_* and no .env in the cwd."""
    for name in list(os.environ):
        if name.startswith("BOOPBOX_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    firmware_dir = tmp_path / "firmware-bins"
    firmware_dir.mkdir()
    for name, value in {
        "BOOPBOX_DB_PATH": str(tmp_path / "boopbox.db"),
        "BOOPBOX_FIRMWARE_DIR": str(firmware_dir),
        "BOOPBOX_SECRET_KEY": SECRET_KEY,
        "BOOPBOX_DEFAULT_USERNAME": OWNER,
        "BOOPBOX_DEFAULT_PASSWORD": OWNER_PASSWORD,
        # Nothing listens on port 1, so the MQTT client fails fast and retries.
        "BOOPBOX_MQTT_PORT": "1",
    }.items():
        monkeypatch.setenv(name, value)
    get_env.cache_clear()
    yield get_env()
    get_env.cache_clear()


@pytest.fixture
def client(env):
    with TestClient(create_app()) as c:
        c.db_path = env.db_path
        yield c


@pytest.fixture
async def services(env):
    svc = await start(env)
    try:
        yield svc
    finally:
        await svc.aclose()


def run_sql(db_path: str, sql: str, params=()) -> None:
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if params:
            conn.execute(sql, params)
        else:
            conn.executescript(sql)
    finally:
        conn.close()


def query(db_path: str, sql: str, params=()) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def add_device(
    db_path: str,
    device_id: str,
    *,
    ota_secret: str | None = None,
    api_token: str | None = None,
    revoked: bool = False,
    deleted: bool = False,
) -> None:
    run_sql(
        db_path,
        "INSERT INTO devices (id, revoked, ota_secret_hash, device_token_hash, "
        "created_at, updated_at, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            device_id,
            int(revoked),
            hash_secret(ota_secret) if ota_secret else None,
            hash_secret(api_token) if api_token else None,
            T,
            T,
            T if deleted else None,
        ),
    )


def add_source(
    db_path: str,
    source_id: int,
    *,
    type: str = "fake",
    enabled: bool = True,
    deleted: bool = False,
    settings: str = "{}",
    secret_encrypted: str | None = None,
) -> None:
    run_sql(
        db_path,
        "INSERT INTO media_sources (id, type, name, name_key, base_url, settings, "
        "secret_encrypted, enabled, created_at, updated_at, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source_id,
            type,
            f"Source {source_id}",
            f"source {source_id}",
            f"http://source-{source_id}",
            settings,
            secret_encrypted,
            int(enabled),
            T,
            T,
            T if deleted else None,
        ),
    )


def add_mapping(
    db_path: str,
    mapping_id: int,
    slug: str,
    *,
    all_devices: bool = True,
    play_order: str = "random",
    devices: tuple[str, ...] = (),
) -> None:
    run_sql(
        db_path,
        "INSERT INTO mappings (id, slug, name, all_devices, play_order, created_at, "
        "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (mapping_id, slug, slug, int(all_devices), play_order, T, T),
    )
    for device_id in devices:
        run_sql(
            db_path,
            "INSERT INTO mapping_devices (mapping_id, device_id, created_at) "
            "VALUES (?, ?, ?)",
            (mapping_id, device_id, T),
        )


def add_entry(
    db_path: str,
    entry_id: int,
    mapping_id: int,
    source_id: int,
    item: str,
    *,
    kind: str = "item",
    position: int = 0,
    status: str = "unknown",
) -> None:
    run_sql(
        db_path,
        "INSERT INTO mapping_entries (id, mapping_id, source_id, item, kind, position, "
        "status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entry_id, mapping_id, source_id, item, kind, position, status, T, T),
    )


def add_user(
    db_path: str,
    user_id: int,
    display_name: str,
    *,
    email: str | None = None,
    disabled: bool = False,
    deleted: bool = False,
    last_login_at: str | None = None,
) -> None:
    """A user with no identity, which makes them pending until one is added."""
    run_sql(
        db_path,
        "INSERT INTO users (id, display_name, email, disabled, last_login_at, "
        "created_at, updated_at, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            display_name,
            email,
            int(disabled),
            last_login_at,
            T,
            T,
            T if deleted else None,
        ),
    )


def add_identity(
    db_path: str,
    user_id: int,
    subject: str,
    *,
    provider: str = "local",
    issuer: str = "",
    label: str | None = None,
    secret_hash: str | None = None,
    locked_until: str | None = None,
    deleted: bool = False,
) -> None:
    run_sql(
        db_path,
        "INSERT INTO auth_identities (user_id, provider, issuer, subject, label, "
        "secret_hash, locked_until, created_at, updated_at, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            provider,
            issuer,
            subject,
            label,
            secret_hash,
            locked_until,
            T,
            T,
            T if deleted else None,
        ),
    )


def add_invite(
    db_path: str,
    user_id: int,
    code: str,
    *,
    expires_at: str,
    used: bool = False,
    revoked: bool = False,
    created_by: int | None = None,
) -> None:
    run_sql(
        db_path,
        "INSERT INTO invites (user_id, code_hash, expires_at, used_at, created_at, "
        "created_by, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            hash_secret(code),
            expires_at,
            T if used else None,
            T,
            created_by,
            T if revoked else None,
        ),
    )


def login(client, username: str, password: str):
    return client.post(
        "/api/auth/token", json={"username": username, "password": password}
    )


def owner_headers(client) -> dict[str, str]:
    """A usable owner token, skipping the first-login password change."""
    run_sql(client.db_path, "UPDATE auth_identities SET must_change_password = 0")
    r = login(client, OWNER, OWNER_PASSWORD)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class StubSources:
    """Stands in for SourceRegistry with fixed instances keyed by id."""

    def __init__(self, sources: dict) -> None:
        self.sources = sources

    async def get(self, source_id: int):
        try:
            return self.sources[source_id]
        except KeyError:
            raise SourceError(
                ErrorCode.source_unavailable, log_detail=f"no stub {source_id}"
            ) from None

    async def aclose(self) -> None:
        pass
