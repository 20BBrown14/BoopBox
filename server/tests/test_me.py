"""GET /api/me."""

import pytest

from app.auth.passwords import _hasher
from app.permissions import CATALOG
from tests.conftest import (
    OWNER,
    OWNER_PASSWORD,
    T,
    add_device,
    login,
    owner_headers,
    run_sql,
)

KID_PASSWORD = "kid-password-123"


@pytest.fixture
def client(client):
    run_sql(
        client.db_path,
        f"""
        INSERT INTO users (id, display_name, created_at, updated_at)
            VALUES (2, 'Kid', '{T}', '{T}');
        INSERT INTO auth_identities (user_id, provider, subject, secret_hash,
                                     created_at, updated_at)
            VALUES (2, 'local', 'kid', '{_hasher.hash(KID_PASSWORD)}', '{T}', '{T}');
        """,
    )
    return client


def _kid_headers(client) -> dict[str, str]:
    token = login(client, "kid", KID_PASSWORD).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _grant(client, permission: str, device_id: str | None = None) -> None:
    if device_id is None:
        run_sql(
            client.db_path,
            "INSERT INTO user_permissions (user_id, permission_id, granted_at) "
            "VALUES (2, ?, ?)",
            (permission, T),
        )
    else:
        run_sql(
            client.db_path,
            "INSERT INTO user_device_permissions "
            "(user_id, device_id, permission_id, granted_at) VALUES (2, ?, ?, ?)",
            (device_id, permission, T),
        )


def test_requires_login(client):
    assert client.get("/api/me").status_code == 401


def test_works_while_password_change_is_required(client):
    token = login(client, OWNER, OWNER_PASSWORD).json()["access_token"]
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["must_change_password"] is True


def test_owner_gets_the_whole_catalog(client):
    body = client.get("/api/me", headers=owner_headers(client)).json()
    assert body == {
        "id": 1,
        "display_name": OWNER,
        "is_owner": True,
        "must_change_password": False,
        "login": {"provider": "local", "username": OWNER, "label": None},
        "permissions": {"global": sorted(CATALOG), "devices": {}},
    }


def test_user_without_grants(client):
    body = client.get("/api/me", headers=_kid_headers(client)).json()
    assert body["is_owner"] is False
    assert body["login"] == {"provider": "local", "username": "kid", "label": None}
    assert body["permissions"] == {"global": [], "devices": {}}


def test_global_and_device_grants(client):
    add_device(client.db_path, "boop-kitchen")
    add_device(client.db_path, "boop-den", revoked=True)
    _grant(client, "users.manage")
    _grant(client, "device.view")
    _grant(client, "device.view", "boop-kitchen")
    _grant(client, "device.control", "boop-kitchen")
    _grant(client, "device.view", "boop-den")
    body = client.get("/api/me", headers=_kid_headers(client)).json()
    assert body["permissions"] == {
        "global": ["device.view", "users.manage"],
        "devices": {
            "boop-den": ["device.view"],
            "boop-kitchen": ["device.control", "device.view"],
        },
    }


def test_grant_on_deleted_device_is_left_out(client):
    add_device(client.db_path, "boop-gone", deleted=True)
    _grant(client, "device.view", "boop-gone")
    body = client.get("/api/me", headers=_kid_headers(client)).json()
    assert body["permissions"]["devices"] == {}


def test_works_with_the_session_cookie(client):
    client.post("/api/auth/login", json={"username": "kid", "password": KID_PASSWORD})
    assert client.get("/api/me").json()["id"] == 2


def test_no_internals_in_the_response(client):
    r = client.get("/api/me", headers=_kid_headers(client))
    assert set(r.json()) == {
        "id",
        "display_name",
        "is_owner",
        "must_change_password",
        "login",
        "permissions",
    }
    assert "argon2" not in r.text
    assert "token_version" not in r.text
