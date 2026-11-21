"""Invite routes: issue and revoke (admin), check and redeem (public)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.passwords import _hasher
from app.config import get_env
from app.main import create_app
from tests.conftest import (
    T,
    add_identity,
    add_invite,
    add_user,
    login,
    owner_headers,
    query,
    run_sql,
)

KID_PASSWORD = "kid-password-123"
NEW_PASSWORD = "a-fresh-password-456"
LATER = "2099-01-01T00:00:00.000Z"
EARLIER = "2000-01-01T00:00:00.000Z"


@pytest.fixture
def client(client):
    add_user(client.db_path, 2, "Kid")
    return client


def _set(client, key: str, value) -> None:
    run_sql(
        client.db_path,
        "INSERT INTO settings (key, value, encrypted, updated_at) VALUES (?, ?, 0, ?)",
        (key, json.dumps(value), T),
    )


def _issue(client, user_id=2, headers=None):
    return client.post(
        f"/api/users/{user_id}/invites", headers=headers or owner_headers(client)
    )


def _history(client) -> list[tuple]:
    return query(
        client.db_path,
        "SELECT outcome, provider, user_id, identifier FROM auth_history "
        "WHERE outcome = 'success' AND user_id = 2",
    )


# POST /api/users/{id}/invites


def test_issue_returns_the_code_once(client):
    before = datetime.now(UTC)
    r = _issue(client)
    assert r.status_code == 201
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert set(body) == {"code", "url", "expires_at"}
    assert body["url"] == f"http://127.0.0.1:9685/invite#code={body['code']}"

    expires = datetime.strptime(body["expires_at"], "%Y-%m-%dT%H:%M:%S.%f%z")
    assert before + timedelta(days=3) - timedelta(seconds=5) < expires
    assert expires < datetime.now(UTC) + timedelta(days=3, seconds=5)

    (stored,) = query(client.db_path, "SELECT code_hash, created_by FROM invites")
    assert body["code"] not in stored[0]
    assert stored[1] == 1

    detail = client.get("/api/users/2", headers=owner_headers(client)).json()
    assert detail["open_invite_expires_at"] == body["expires_at"]


def test_expiry_follows_the_setting(client):
    _set(client, "invites.expiry_days", 7)
    expires = datetime.strptime(
        _issue(client).json()["expires_at"], "%Y-%m-%dT%H:%M:%S.%f%z"
    )
    assert (
        timedelta(days=6, hours=23) < expires - datetime.now(UTC) <= timedelta(days=7)
    )


def test_url_follows_the_setting(client):
    _set(client, "public_base_url", "https://boop.example/box")
    body = _issue(client).json()
    assert body["url"] == f"https://boop.example/box/invite#code={body['code']}"


def test_url_follows_the_environment(env, monkeypatch):
    monkeypatch.setenv("BOOPBOX_PUBLIC_BASE_URL", "https://env.example")
    get_env.cache_clear()
    with TestClient(create_app()) as c:
        c.db_path = env.db_path
        add_user(c.db_path, 2, "Kid")
        _set(c, "public_base_url", "https://ignored.example")
        body = _issue(c).json()
    assert body["url"] == f"https://env.example/invite#code={body['code']}"


def test_a_new_invite_revokes_the_earlier_one(client):
    headers = owner_headers(client)
    first = _issue(client, headers=headers).json()["code"]
    second = _issue(client, headers=headers).json()["code"]
    assert _check(client, first).status_code == 404
    assert _check(client, second).status_code == 200
    assert query(
        client.db_path, "SELECT count(*) FROM invites WHERE deleted_at IS NULL"
    ) == [(1,)]


def test_an_active_user_can_be_reinvited(client):
    add_identity(client.db_path, 2, "kid")
    assert _issue(client).status_code == 201


def test_the_owner_cannot_be_invited(client):
    r = _issue(client, user_id=1)
    assert r.status_code == 422
    assert r.json()["message"] == "the owner can't be invited"
    assert query(client.db_path, "SELECT count(*) FROM invites") == [(0,)]


def test_a_disabled_user_cannot_be_invited(client):
    run_sql(client.db_path, "UPDATE users SET disabled = 1 WHERE id = 2")
    r = _issue(client)
    assert r.status_code == 422
    assert r.json()["message"] == "enable the user before inviting them"


@pytest.mark.parametrize("deleted", [False, True])
def test_issue_for_an_unknown_or_deleted_user_is_404(client, deleted):
    if deleted:
        add_user(client.db_path, 3, "Gone", deleted=True)
    assert _issue(client, user_id=3).status_code == 404


def test_issue_needs_users_manage(client):
    add_identity(client.db_path, 2, "kid", secret_hash=_hasher.hash(KID_PASSWORD))
    token = login(client, "kid", KID_PASSWORD).json()["access_token"]
    add_user(client.db_path, 3, "Other")
    r = _issue(client, user_id=3, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# DELETE /api/users/{id}/invites


def test_revoke_invites(client):
    headers = owner_headers(client)
    code = _issue(client, headers=headers).json()["code"]
    r = client.delete("/api/users/2/invites", headers=headers)
    assert r.status_code == 204
    assert _check(client, code).status_code == 404
    detail = client.get("/api/users/2", headers=headers).json()
    assert detail["open_invite_expires_at"] is None


def test_revoke_without_invites_is_fine(client):
    assert (
        client.delete("/api/users/2/invites", headers=owner_headers(client)).status_code
        == 204
    )


def test_revoke_for_an_unknown_user_is_404(client):
    r = client.delete("/api/users/3/invites", headers=owner_headers(client))
    assert r.status_code == 404


# POST /api/invites/check


def _check(client, code: str):
    return client.post("/api/invites/check", json={"code": code})


def test_check_greets_by_name(client):
    add_invite(client.db_path, 2, "good-code", expires_at=LATER)
    r = _check(client, "good-code")
    assert r.status_code == 200
    assert r.json() == {"display_name": "Kid"}


INVALID_CASES = {
    "unknown": lambda db: None,
    "expired": lambda db: add_invite(db, 2, "code", expires_at=EARLIER),
    "used": lambda db: add_invite(db, 2, "code", expires_at=LATER, used=True),
    "revoked": lambda db: add_invite(db, 2, "code", expires_at=LATER, revoked=True),
    "disabled": lambda db: (
        add_invite(db, 2, "code", expires_at=LATER),
        run_sql(db, "UPDATE users SET disabled = 1 WHERE id = 2"),
    ),
    "deleted": lambda db: (
        add_invite(db, 2, "code", expires_at=LATER),
        run_sql(db, f"UPDATE users SET deleted_at = '{T}' WHERE id = 2"),
    ),
}

GENERIC_FAILURE = {
    "code": "not_found",
    "message": "invalid or expired invite",
    "field": "code",
}


@pytest.mark.parametrize("case", INVALID_CASES)
def test_check_failures_all_look_the_same(client, case):
    INVALID_CASES[case](client.db_path)
    r = _check(client, "code")
    assert r.status_code == 404
    assert r.json() == GENERIC_FAILURE


def test_an_oversized_code_looks_the_same(client):
    r = _check(client, "x" * 129)
    assert r.status_code == 404
    assert r.json() == GENERIC_FAILURE


def test_check_needs_json(client):
    r = client.post("/api/invites/check", data={"code": "x"})
    assert r.status_code == 422
    assert r.json()["message"] == "expected application/json"


def test_check_refuses_another_origin(client):
    r = client.post(
        "/api/invites/check",
        json={"code": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


# POST /api/invites/redeem


def _redeem(client, code: str, username="kid", password=NEW_PASSWORD):
    return client.post(
        "/api/invites/redeem",
        json={"code": code, "username": username, "password": password},
    )


def test_issue_check_redeem_then_use_the_session(client):
    code = _issue(client).json()["code"]
    assert _check(client, code).json() == {"display_name": "Kid"}

    r = _redeem(client, code, username=" Kid ")
    assert r.status_code == 200
    assert r.json() == {"must_change_password": False}
    # No Authorization header, so this rides on the cookie redeem just set.
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["id"] == 2
    assert me.json()["login"]["username"] == "kid"

    assert login(client, "kid", NEW_PASSWORD).status_code == 200
    detail = client.get("/api/users/2", headers=owner_headers(client)).json()
    assert detail["status"] == "active"
    assert detail["open_invite_expires_at"] is None


def test_redeem_counts_as_one_login(client):
    add_invite(client.db_path, 2, "code", expires_at=LATER)
    assert _redeem(client, "code", username="Kid").status_code == 200

    assert _history(client) == [("success", "local", 2, "Kid")]
    ((last_login, last_used),) = query(
        client.db_path,
        "SELECT u.last_login_at, i.last_used_at FROM users u "
        "JOIN auth_identities i ON i.user_id = u.id WHERE u.id = 2",
    )
    assert last_login is not None
    assert last_login == last_used


@pytest.mark.parametrize(
    ("username", "password", "field"),
    [
        ("ab", NEW_PASSWORD, "username"),
        ("a" * 33, NEW_PASSWORD, "username"),
        ("no spaces", NEW_PASSWORD, "username"),
        ("kid!", NEW_PASSWORD, "username"),
        ("kid", "too-short", "password"),
        ("kid", "x" * 129, "password"),
    ],
)
def test_redeem_validation_errors(client, username, password, field):
    add_invite(client.db_path, 2, "code", expires_at=LATER)
    r = _redeem(client, "code", username=username, password=password)
    assert r.status_code == 422
    assert r.json()["field"] == field
    assert _history(client) == []
    assert _check(client, "code").status_code == 200


@pytest.mark.parametrize("deleted", [False, True])
def test_a_taken_username_is_409(client, deleted):
    add_user(client.db_path, 3, "Other", deleted=deleted)
    add_identity(client.db_path, 3, "taken", deleted=deleted)
    add_invite(client.db_path, 2, "code", expires_at=LATER)

    r = _redeem(client, "code", username="Taken")
    assert r.status_code == 409
    assert r.json()["field"] == "username"
    assert "set-cookie" not in r.headers
    assert _history(client) == []
    assert _check(client, "code").status_code == 200


@pytest.mark.parametrize("case", INVALID_CASES)
def test_redeem_with_a_bad_code_looks_like_check(client, case):
    INVALID_CASES[case](client.db_path)
    r = _redeem(client, "code")
    assert r.status_code == 404
    assert r.json() == GENERIC_FAILURE
    assert "set-cookie" not in r.headers
    assert query(client.db_path, "SELECT count(*) FROM auth_history") == [(0,)]


def test_redeem_with_an_oversized_code_looks_like_check(client):
    r = _redeem(client, "x" * 129)
    assert r.status_code == 404
    assert r.json() == GENERIC_FAILURE


def test_redeeming_twice_fails_the_second_time(client):
    add_invite(client.db_path, 2, "code", expires_at=LATER)
    assert _redeem(client, "code").status_code == 200
    r = _redeem(client, "code", username="kid-two")
    assert r.status_code == 404
    assert len(_history(client)) == 1


def test_a_reinvite_ends_the_old_sessions(client):
    add_identity(client.db_path, 2, "kid", secret_hash=_hasher.hash(KID_PASSWORD))
    token = login(client, "kid", KID_PASSWORD).json()["access_token"]
    old = {"Authorization": f"Bearer {token}"}
    code = _issue(client).json()["code"]

    assert _redeem(client, code, username="kid").status_code == 200
    assert client.get("/api/me").status_code == 200

    assert client.get("/api/me", headers=old).status_code == 403
    assert login(client, "kid", KID_PASSWORD).status_code == 401
    assert login(client, "kid", NEW_PASSWORD).status_code == 200


def test_redeem_needs_json(client):
    r = client.post("/api/invites/redeem", data={"code": "x"})
    assert r.status_code == 422
    assert r.json()["message"] == "expected application/json"
