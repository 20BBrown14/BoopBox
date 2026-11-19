"""User login, lockout, history and token revocation; device credentials; and
strict separation between the credential types."""

import base64

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.auth import require_device_api, require_user
from app.auth.jwt import issue_user_jwt, now_seconds
from app.auth.login import client_address
from app.auth.passwords import _hasher
from app.db.users import AuthUser
from app.main import create_app
from app.security import hash_secret
from app.types.device import Device
from tests.conftest import OWNER, OWNER_PASSWORD, T, add_device, login, query, run_sql

OTA_SECRET = "device-ota-secret"
API_TOKEN = "device-api-token"
DEVICE_ID = "boop-test"
KID = "kid"
KID_PASSWORD = "kid-password-123"
GENERIC = {"code": "unauthorized", "message": "invalid username or password"}


@pytest.fixture
def client(env):
    app = create_app()

    # Stand-ins for routes guarded by each dependency.
    @app.get("/_test/device")
    async def _device(device: Device = Depends(require_device_api)):  # noqa: B008
        return {"device_id": device.id}

    @app.get("/_test/user")
    async def _user(user: AuthUser = Depends(require_user)):  # noqa: B008
        return {"user_id": user.id}

    with TestClient(app) as c:
        c.db_path = env.db_path
        add_device(env.db_path, DEVICE_ID, ota_secret=OTA_SECRET, api_token=API_TOKEN)
        run_sql(
            env.db_path,
            f"""
            INSERT INTO users (id, display_name, created_at, updated_at)
                VALUES (2, 'Kid', '{T}', '{T}');
            INSERT INTO auth_identities (user_id, provider, subject, secret_hash,
                                         created_at, updated_at)
                VALUES (2, 'local', '{KID}', '{_hasher.hash(KID_PASSWORD)}',
                        '{T}', '{T}');
            """,
        )
        yield c


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(client, username=KID, password=KID_PASSWORD) -> str:
    r = login(client, username, password)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _history(client) -> list[tuple]:
    return query(
        client.db_path,
        "SELECT outcome, user_id, identifier FROM auth_history ORDER BY id",
    )


def _identity(client, user_id=2) -> tuple:
    return query(
        client.db_path,
        "SELECT failed_attempts, last_failed_at IS NOT NULL, locked_until IS NOT NULL "
        "FROM auth_identities WHERE user_id = ?",
        (user_id,),
    )[0]


# --- login ---


def test_login_returns_a_working_token(client):
    r = login(client, KID, KID_PASSWORD)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 8 * 3600
    assert body["must_change_password"] is False
    assert client.get("/_test/user", headers=_bearer(body["access_token"])).json() == {
        "user_id": 2
    }
    assert query(
        client.db_path, "SELECT last_login_at IS NOT NULL FROM users WHERE id = 2"
    ) == [(1,)]


def test_username_is_trimmed_and_case_insensitive(client):
    assert login(client, "  KiD ", KID_PASSWORD).status_code == 200


@pytest.mark.parametrize(
    ("username", "password", "outcome", "user_id"),
    [
        (KID, "wrong-password-1", "bad_credentials", 2),
        ("nobody", KID_PASSWORD, "unknown_user", None),
    ],
)
def test_failures_share_one_error_and_are_recorded(
    client, username, password, outcome, user_id
):
    r = login(client, username, password)
    assert r.status_code == 401
    assert r.json() == GENERIC
    assert _history(client) == [(outcome, user_id, username)]


def test_history_records_client_details(client):
    login(client, KID, KID_PASSWORD)
    ip, agent = query(client.db_path, "SELECT client_ip, user_agent FROM auth_history")[
        0
    ]
    assert ip == "testclient"
    assert agent


def test_lockout_after_threshold(client):
    for _ in range(5):
        login(client, KID, "wrong-password-1")
    assert _identity(client) == (5, 1, 1)
    r = login(client, KID, KID_PASSWORD)
    assert r.json() == GENERIC
    login(client, KID, "wrong-password-1")
    # Attempts during the lock are neither checked nor counted.
    assert _identity(client) == (5, 1, 1)
    assert [row[0] for row in _history(client)][-2:] == ["locked", "locked"]

    run_sql(client.db_path, "UPDATE auth_identities SET locked_until = NULL")
    assert login(client, KID, KID_PASSWORD).status_code == 200
    assert _identity(client) == (0, 0, 0)


def test_old_failures_stop_counting(client):
    run_sql(
        client.db_path,
        "UPDATE auth_identities SET failed_attempts = 4, "
        "last_failed_at = '2020-01-01T00:00:00.000Z' WHERE user_id = 2",
    )
    login(client, KID, "wrong-password-1")
    assert _identity(client) == (1, 1, 0)


def test_disabled_user_cannot_log_in_or_use_a_token(client):
    token = _token(client)
    run_sql(client.db_path, "UPDATE users SET disabled = 1 WHERE id = 2")
    assert login(client, KID, KID_PASSWORD).json() == GENERIC
    assert _history(client)[-1][0] == "disabled"
    assert client.get("/_test/user", headers=_bearer(token)).status_code == 403


def test_deleted_user_cannot_log_in(client):
    run_sql(
        client.db_path,
        f"UPDATE users SET deleted_at = '{T}' WHERE id = 2; "
        f"UPDATE auth_identities SET deleted_at = '{T}' WHERE user_id = 2;",
    )
    assert login(client, KID, KID_PASSWORD).json() == GENERIC
    assert _history(client)[-1][:2] == ("deleted", 2)


def test_token_version_bump_revokes_tokens(client):
    token = _token(client)
    run_sql(client.db_path, "UPDATE users SET token_version = token_version + 1")
    assert client.get("/_test/user", headers=_bearer(token)).status_code == 403
    assert client.get("/_test/user", headers=_bearer(_token(client))).status_code == 200


def test_bad_tokens(client):
    assert client.get("/_test/user").status_code == 401
    token = _token(client)
    assert client.get("/_test/user", headers=_bearer(token + "x")).status_code == 403
    forged = issue_user_jwt(
        2,
        version=0,
        secret="a-different-secret-also-32-bytes-plus",
        ttl_seconds=600,
        now=now_seconds(),
    )
    assert client.get("/_test/user", headers=_bearer(forged)).status_code == 403


# --- bootstrap owner and the first-login password change ---


def test_owner_must_change_password_first(client):
    r = login(client, OWNER, OWNER_PASSWORD)
    assert r.json()["must_change_password"] is True
    first = r.json()["access_token"]
    assert client.get("/_test/user", headers=_bearer(first)).status_code == 403

    r = client.post(
        "/auth/password",
        headers=_bearer(first),
        json={
            "current_password": OWNER_PASSWORD,
            "new_password": "a new long password",
        },
    )
    assert r.status_code == 200
    second = r.json()["access_token"]
    assert r.json()["must_change_password"] is False
    assert client.get("/_test/user", headers=_bearer(second)).status_code == 200
    # The change logs out every other token.
    assert client.get("/_test/user", headers=_bearer(first)).status_code == 403
    assert login(client, OWNER, OWNER_PASSWORD).status_code == 401
    assert login(client, OWNER, "a new long password").status_code == 200


def test_password_change_checks_current_and_length(client):
    token = _token(client)
    wrong = client.post(
        "/auth/password",
        headers=_bearer(token),
        json={"current_password": "nope", "new_password": "a new long password"},
    )
    assert wrong.status_code == 403
    short = client.post(
        "/auth/password",
        headers=_bearer(token),
        json={"current_password": KID_PASSWORD, "new_password": "short"},
    )
    assert short.status_code == 422
    assert short.json()["code"] == "invalid_request"


def test_owner_is_created_once_with_a_hashed_password(client):
    rows = query(
        client.db_path,
        "SELECT u.is_owner, i.subject, i.secret_hash, i.must_change_password "
        "FROM users u JOIN auth_identities i ON i.user_id = u.id WHERE u.id = 1",
    )
    assert len(rows) == 1
    is_owner, subject, secret_hash, must_change = rows[0]
    assert (is_owner, subject, must_change) == (1, OWNER, 1)
    assert secret_hash.startswith("$argon2id$")


def test_client_address():
    assert client_address("10.0.0.1", "1.2.3.4, 5.6.7.8", False) == "10.0.0.1"
    assert client_address("10.0.0.1", "1.2.3.4, 5.6.7.8", True) == "5.6.7.8"
    assert client_address("10.0.0.1", None, True) == "10.0.0.1"


# --- device API (Bearer + X-Device-Id) ---


def _device_headers(token=API_TOKEN, device_id=DEVICE_ID) -> dict[str, str]:
    return {**_bearer(token), "X-Device-Id": device_id}


def test_device_api_accepts_valid_token(client):
    r = client.get("/_test/device", headers=_device_headers())
    assert r.status_code == 200
    assert r.json()["device_id"] == DEVICE_ID


def test_device_api_rejections(client):
    assert client.get("/_test/device", headers=_bearer(API_TOKEN)).status_code == 401
    assert (
        client.get("/_test/device", headers=_device_headers("nope")).status_code == 403
    )
    ghost = _device_headers(device_id="ghost")
    assert client.get("/_test/device", headers=ghost).status_code == 403


@pytest.mark.parametrize("change", ["revoked = 1", f"deleted_at = '{T}'"])
def test_device_api_inactive_device_403(client, change):
    run_sql(client.db_path, f"UPDATE devices SET {change}")
    assert client.get("/_test/device", headers=_device_headers()).status_code == 403


# --- strict separation ---


def test_user_jwt_rejected_on_device_route(client):
    headers = _device_headers(_token(client))
    assert client.get("/_test/device", headers=headers).status_code == 403


def test_device_token_rejected_on_user_route(client):
    assert client.get("/_test/user", headers=_bearer(API_TOKEN)).status_code == 403


def test_ota_basic_secret_rejected_on_user_route(client):
    raw = base64.b64encode(f"{DEVICE_ID}:{OTA_SECRET}".encode()).decode()
    r = client.get("/_test/user", headers={"Authorization": f"Basic {raw}"})
    assert r.status_code == 401


def test_stored_device_secrets_are_hashes(client):
    assert query(
        client.db_path, "SELECT ota_secret_hash, device_token_hash FROM devices"
    ) == [(hash_secret(OTA_SECRET), hash_secret(API_TOKEN))]
