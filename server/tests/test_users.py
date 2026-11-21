"""GET /api/users and GET /api/users/{id}."""

import pytest

from app.auth.passwords import _hasher
from tests.conftest import (
    OWNER,
    T,
    add_identity,
    add_invite,
    add_user,
    login,
    owner_headers,
    run_sql,
)

KID_PASSWORD = "kid-password-123"
LATER = "2099-01-01T00:00:00.000Z"

USER_FIELDS = {
    "id",
    "display_name",
    "email",
    "is_owner",
    "status",
    "login",
    "last_login_at",
    "locked",
    "created_at",
}


@pytest.fixture
def client(client):
    add_user(client.db_path, 2, "Kid")
    add_identity(client.db_path, 2, "kid", secret_hash=_hasher.hash(KID_PASSWORD))
    return client


def _kid_headers(client) -> dict[str, str]:
    token = login(client, "kid", KID_PASSWORD).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _grant_kid(client, permission: str) -> None:
    run_sql(
        client.db_path,
        "INSERT INTO user_permissions (user_id, permission_id, granted_at) "
        "VALUES (2, ?, ?)",
        (permission, T),
    )


@pytest.mark.parametrize("path", ["/api/users", "/api/users/1"])
def test_requires_login(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/users", "/api/users/1", "/api/users/999"])
def test_forbidden_without_users_manage(client, path):
    _grant_kid(client, "device.view")
    r = client.get(path, headers=_kid_headers(client))
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"


@pytest.mark.parametrize("path", ["/api/users", "/api/users/1"])
def test_allowed_with_a_grant(client, path):
    _grant_kid(client, "users.manage")
    assert client.get(path, headers=_kid_headers(client)).status_code == 200


def test_owner_lists_everyone(client):
    body = client.get("/api/users", headers=owner_headers(client)).json()
    assert body["total"] == 2
    assert (body["limit"], body["offset"]) == (50, 0)
    assert [user["display_name"] for user in body["items"]] == ["Kid", OWNER]


def test_list_item_shape(client):
    add_user(client.db_path, 3, "Pending", email="p@example.com")
    body = client.get("/api/users", headers=owner_headers(client)).json()
    by_id = {user["id"]: user for user in body["items"]}

    for user in body["items"]:
        assert set(user) == USER_FIELDS
    assert by_id[2]["login"] == {"provider": "local", "username": "kid", "label": None}
    assert by_id[2]["status"] == "active"
    assert by_id[3] == {
        "id": 3,
        "display_name": "Pending",
        "email": "p@example.com",
        "is_owner": False,
        "status": "pending",
        "login": None,
        "last_login_at": None,
        "locked": False,
        "created_at": T,
    }


def test_pages(client):
    for user_id in range(3, 8):
        add_user(client.db_path, user_id, f"User {user_id}")
    headers = owner_headers(client)

    body = client.get("/api/users?limit=2&offset=2", headers=headers).json()
    assert body["total"] == 7
    assert (body["limit"], body["offset"]) == (2, 2)
    assert [user["display_name"] for user in body["items"]] == ["User 3", "User 4"]

    past_the_end = client.get("/api/users?offset=50", headers=headers).json()
    assert past_the_end["items"] == []
    assert past_the_end["total"] == 7


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("limit=0", "limit"),
        ("limit=201", "limit"),
        ("limit=lots", "limit"),
        ("offset=-1", "offset"),
    ],
)
def test_bad_page_params(client, query, field):
    r = client.get(f"/api/users?{query}", headers=owner_headers(client))
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"
    assert r.json()["field"] == field


def test_detail(client):
    add_invite(client.db_path, 2, "open-code", expires_at=LATER)
    body = client.get("/api/users/2", headers=owner_headers(client)).json()
    assert set(body) == USER_FIELDS | {"open_invite_expires_at"}
    assert body["display_name"] == "Kid"
    assert body["open_invite_expires_at"] == LATER


def test_owner_detail(client):
    body = client.get("/api/users/1", headers=owner_headers(client)).json()
    assert body["is_owner"] is True
    assert body["login"] == {"provider": "local", "username": OWNER, "label": None}
    assert body["open_invite_expires_at"] is None


@pytest.mark.parametrize("deleted", [False, True])
def test_unknown_or_deleted_user_is_404(client, deleted):
    if deleted:
        add_user(client.db_path, 3, "Gone", deleted=True)
    r = client.get("/api/users/3", headers=owner_headers(client))
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_no_internals_anywhere(client):
    headers = owner_headers(client)
    texts = [
        client.get("/api/users", headers=headers).text,
        client.get("/api/users/1", headers=headers).text,
        client.get("/api/users/2", headers=headers).text,
    ]
    for text in texts:
        for leaked in (
            "secret_hash",
            "token_version",
            "identity_id",
            "subject",
            "issuer",
            "failed_attempts",
            "locked_until",
            "$argon2",
        ):
            assert leaked not in text
