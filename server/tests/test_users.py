"""/api/users: list, detail, create, update and delete."""

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
    query,
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


# POST /api/users


def _create(client, headers, **body):
    return client.post("/api/users", json=body, headers=headers)


def _user_row(client, user_id: int) -> dict:
    columns = (
        "display_name, email, disabled, token_version, created_by, updated_at, "
        "updated_by, deleted_at, deleted_by"
    )
    (row,) = query(
        client.db_path, f"SELECT {columns} FROM users WHERE id = ?", (user_id,)
    )
    return dict(zip([c.strip() for c in columns.split(",")], row, strict=True))


def test_create_makes_a_pending_user(client):
    r = _create(
        client, owner_headers(client), display_name="  Nan  ", email=" nan@example.com "
    )
    assert r.status_code == 201
    body = r.json()
    assert set(body) == USER_FIELDS | {"open_invite_expires_at"}
    assert body["display_name"] == "Nan"
    assert body["email"] == "nan@example.com"
    assert body["status"] == "pending"
    assert body["login"] is None
    assert body["open_invite_expires_at"] is None

    row = _user_row(client, body["id"])
    assert (row["created_by"], row["updated_by"]) == (1, 1)


def test_create_stamps_the_acting_user(client):
    _grant_kid(client, "users.manage")
    r = _create(client, _kid_headers(client), display_name="Nan")
    assert r.status_code == 201
    row = _user_row(client, r.json()["id"])
    assert (row["created_by"], row["updated_by"]) == (2, 2)


@pytest.mark.parametrize("email", [None, "", "   "])
def test_create_without_an_email_stores_null(client, email):
    body = (
        {"display_name": "Nan"}
        if email is None
        else {"display_name": "Nan", "email": email}
    )
    r = client.post("/api/users", json=body, headers=owner_headers(client))
    assert r.status_code == 201
    assert r.json()["email"] is None
    assert _user_row(client, r.json()["id"])["email"] is None


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "display_name"),
        ({"display_name": ""}, "display_name"),
        ({"display_name": "   "}, "display_name"),
        ({"display_name": "a" * 65}, "display_name"),
        ({"display_name": "two\nlines"}, "display_name"),
        ({"display_name": "tab\there"}, "display_name"),
        ({"display_name": "Nan", "email": "nope"}, "email"),
        ({"display_name": "Nan", "email": "a@b@c"}, "email"),
        ({"display_name": "Nan", "email": "a" * 250 + "@b.cd"}, "email"),
        ({"display_name": "Nan", "email": "a@b\n.cd"}, "email"),
    ],
)
def test_create_field_errors(client, body, field):
    r = client.post("/api/users", json=body, headers=owner_headers(client))
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"
    assert r.json()["field"] == field


def test_create_counts_the_cleaned_name(client):
    name = "e\u0301" * 64
    r = _create(client, owner_headers(client), display_name=f" {name} ")
    assert r.status_code == 201
    assert len(r.json()["display_name"]) == 64


def test_create_needs_users_manage(client):
    _grant_kid(client, "device.view")
    r = _create(client, _kid_headers(client), display_name="Nan")
    assert r.status_code == 403
    assert query(client.db_path, "SELECT count(*) FROM users") == [(2,)]


# PATCH /api/users/{id}


def _patch(client, headers, user_id, **body):
    return client.patch(f"/api/users/{user_id}", json=body, headers=headers)


def test_patch_applies_only_what_was_sent(client):
    headers = owner_headers(client)
    run_sql(client.db_path, "UPDATE users SET email = 'kid@example.com' WHERE id = 2")

    r = _patch(client, headers, 2, display_name=" Kiddo ")
    assert r.status_code == 200
    assert (r.json()["display_name"], r.json()["email"]) == ("Kiddo", "kid@example.com")

    r = _patch(client, headers, 2, email="new@example.com")
    assert (r.json()["display_name"], r.json()["email"]) == ("Kiddo", "new@example.com")

    row = _user_row(client, 2)
    assert (row["disabled"], row["updated_by"]) == (0, 1)


@pytest.mark.parametrize("email", [None, "", "  "])
def test_patch_can_clear_the_email(client, email):
    run_sql(client.db_path, "UPDATE users SET email = 'kid@example.com' WHERE id = 2")
    r = _patch(client, owner_headers(client), 2, email=email)
    assert r.status_code == 200
    assert r.json()["email"] is None
    assert _user_row(client, 2)["email"] is None


def test_patch_without_changes_leaves_updated_alone(client):
    headers = owner_headers(client)
    for body in ({}, {"display_name": "Kid"}, {"disabled": False}, {"email": None}):
        assert _patch(client, headers, 2, **body).status_code == 200
    row = _user_row(client, 2)
    assert (row["updated_at"], row["updated_by"]) == (T, None)


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"display_name": None}, "display_name"),
        ({"display_name": ""}, "display_name"),
        ({"display_name": "a\nb"}, "display_name"),
        ({"email": "nope"}, "email"),
        ({"disabled": None}, "disabled"),
    ],
)
def test_patch_field_errors(client, body, field):
    r = _patch(client, owner_headers(client), 2, **body)
    assert r.status_code == 422
    assert r.json()["field"] == field


def test_disabling_revokes_tokens_and_enabling_does_not_restore_them(client):
    kid = _kid_headers(client)
    assert client.get("/api/me", headers=kid).status_code == 200
    headers = owner_headers(client)

    r = _patch(client, headers, 2, disabled=True)
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    assert client.get("/api/me", headers=kid).status_code == 403
    assert _user_row(client, 2)["token_version"] == 1

    r = _patch(client, headers, 2, disabled=False)
    assert r.json()["status"] == "active"
    assert _user_row(client, 2)["token_version"] == 1
    assert client.get("/api/me", headers=kid).status_code == 403
    assert client.get("/api/me", headers=_kid_headers(client)).status_code == 200


def test_the_owner_cannot_be_disabled(client):
    _grant_kid(client, "users.manage")
    r = _patch(client, _kid_headers(client), 1, disabled=True)
    assert r.status_code == 422
    assert r.json()["field"] == "disabled"
    assert _user_row(client, 1)["disabled"] == 0


def test_you_cannot_disable_yourself(client):
    _grant_kid(client, "users.manage")
    r = _patch(client, _kid_headers(client), 2, disabled=True)
    assert r.status_code == 422
    assert r.json()["field"] == "disabled"
    assert r.json()["message"] == "you can't disable yourself"


def test_you_can_rename_yourself(client):
    _grant_kid(client, "users.manage")
    r = _patch(client, _kid_headers(client), 2, display_name="Big kid")
    assert r.status_code == 200
    assert _user_row(client, 2)["updated_by"] == 2


@pytest.mark.parametrize("deleted", [False, True])
def test_patch_unknown_or_deleted_user_is_404(client, deleted):
    if deleted:
        add_user(client.db_path, 3, "Gone", deleted=True)
    r = _patch(client, owner_headers(client), 3, display_name="Back")
    assert r.status_code == 404


def test_patch_needs_users_manage(client):
    _grant_kid(client, "device.view")
    r = _patch(client, _kid_headers(client), 1, display_name="Mine now")
    assert r.status_code == 403
    assert _user_row(client, 1)["display_name"] == OWNER


# DELETE /api/users/{id}


def test_delete_soft_deletes_the_user_and_their_login(client):
    kid = _kid_headers(client)
    _grant_kid(client, "device.view")
    add_invite(client.db_path, 2, "open", expires_at=LATER)
    add_invite(client.db_path, 2, "used", expires_at=LATER, used=True)
    headers = owner_headers(client)

    r = client.delete("/api/users/2", headers=headers)
    assert r.status_code == 204

    listed = client.get("/api/users", headers=headers).json()
    assert [user["id"] for user in listed["items"]] == [1]
    assert client.get("/api/users/2", headers=headers).status_code == 404

    assert client.get("/api/me", headers=kid).status_code == 403
    assert login(client, "kid", KID_PASSWORD).status_code == 401

    row = _user_row(client, 2)
    assert row["deleted_by"] == 1
    assert row["token_version"] == 1
    assert query(
        client.db_path,
        "SELECT subject, deleted_by FROM auth_identities WHERE user_id = 2",
    ) == [("kid", 1)]
    invites = query(
        client.db_path,
        "SELECT used_at IS NOT NULL, deleted_by FROM invites WHERE user_id = 2 "
        "ORDER BY id",
    )
    assert invites == [(0, 1), (1, None)]
    assert query(
        client.db_path, "SELECT permission_id FROM user_permissions WHERE user_id = 2"
    ) == [("device.view",)]


def test_delete_a_pending_user(client):
    add_user(client.db_path, 3, "Pending")
    r = client.delete("/api/users/3", headers=owner_headers(client))
    assert r.status_code == 204
    assert _user_row(client, 3)["deleted_by"] == 1


def test_the_owner_cannot_be_deleted(client):
    _grant_kid(client, "users.manage")
    r = client.delete("/api/users/1", headers=_kid_headers(client))
    assert r.status_code == 422
    assert r.json()["message"] == "the owner can't be deleted"
    assert _user_row(client, 1)["deleted_at"] is None


def test_you_cannot_delete_yourself(client):
    _grant_kid(client, "users.manage")
    r = client.delete("/api/users/2", headers=_kid_headers(client))
    assert r.status_code == 422
    assert r.json()["message"] == "you can't delete yourself"
    assert _user_row(client, 2)["deleted_at"] is None


def test_delete_twice_is_404(client):
    headers = owner_headers(client)
    assert client.delete("/api/users/2", headers=headers).status_code == 204
    assert client.delete("/api/users/2", headers=headers).status_code == 404


def test_delete_needs_users_manage(client):
    add_user(client.db_path, 3, "Other")
    _grant_kid(client, "device.view")
    r = client.delete("/api/users/3", headers=_kid_headers(client))
    assert r.status_code == 403
    assert _user_row(client, 3)["deleted_at"] is None


# POST /api/users/{id}/unlock


def _lock_kid(client) -> None:
    run_sql(
        client.db_path,
        "UPDATE auth_identities SET failed_attempts = 5, last_failed_at = ?, "
        "locked_until = ? WHERE user_id = 2",
        (T, LATER),
    )


def _identity_row(client, user_id: int) -> tuple:
    (row,) = query(
        client.db_path,
        "SELECT failed_attempts, last_failed_at, locked_until, updated_at "
        "FROM auth_identities WHERE user_id = ? AND deleted_at IS NULL",
        (user_id,),
    )
    return row


def test_unlock_lets_a_locked_user_log_in(client):
    _lock_kid(client)
    assert login(client, "kid", KID_PASSWORD).status_code == 401
    headers = owner_headers(client)
    assert client.get("/api/users/2", headers=headers).json()["locked"] is True

    r = client.post("/api/users/2/unlock", headers=headers)
    assert r.status_code == 204
    assert _identity_row(client, 2) == (0, None, None, T)
    assert client.get("/api/users/2", headers=headers).json()["locked"] is False
    assert login(client, "kid", KID_PASSWORD).status_code == 200


def test_unlock_is_not_an_edit(client):
    _lock_kid(client)
    client.post("/api/users/2/unlock", headers=owner_headers(client))
    row = _user_row(client, 2)
    assert (row["updated_at"], row["updated_by"]) == (T, None)
    assert _identity_row(client, 2)[3] == T


def test_unlock_a_pending_user_changes_nothing(client):
    add_user(client.db_path, 3, "Pending")
    r = client.post("/api/users/3/unlock", headers=owner_headers(client))
    assert r.status_code == 204


def test_unlock_needs_users_manage(client):
    _grant_kid(client, "device.view")
    kid = _kid_headers(client)
    run_sql(
        client.db_path,
        "UPDATE auth_identities SET locked_until = ? WHERE user_id = 1",
        (LATER,),
    )
    r = client.post("/api/users/1/unlock", headers=kid)
    assert r.status_code == 403
    assert _identity_row(client, 1)[2] == LATER


# POST /api/users/{id}/logout-all


def test_logout_all_revokes_the_targets_tokens(client):
    kid = _kid_headers(client)
    headers = owner_headers(client)

    r = client.post("/api/users/2/logout-all", headers=headers)
    assert r.status_code == 204
    assert client.get("/api/me", headers=kid).status_code == 403
    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.get("/api/me", headers=_kid_headers(client)).status_code == 200


def test_logout_all_is_allowed_on_the_owner(client):
    _grant_kid(client, "users.manage")
    owner = owner_headers(client)
    r = client.post("/api/users/1/logout-all", headers=_kid_headers(client))
    assert r.status_code == 204
    assert client.get("/api/me", headers=owner).status_code == 403


def test_logout_all_on_yourself_ends_this_session_too(client):
    headers = owner_headers(client)
    r = client.post("/api/users/1/logout-all", headers=headers)
    assert r.status_code == 204
    assert client.get("/api/me", headers=headers).status_code == 403


def test_logout_all_is_not_an_edit(client):
    client.post("/api/users/2/logout-all", headers=owner_headers(client))
    row = _user_row(client, 2)
    assert row["token_version"] == 1
    assert (row["updated_at"], row["updated_by"]) == (T, None)


def test_logout_all_needs_users_manage(client):
    _grant_kid(client, "device.view")
    owner = owner_headers(client)
    r = client.post("/api/users/1/logout-all", headers=_kid_headers(client))
    assert r.status_code == 403
    assert client.get("/api/me", headers=owner).status_code == 200


@pytest.mark.parametrize("action", ["unlock", "logout-all"])
@pytest.mark.parametrize("deleted", [False, True])
def test_actions_on_an_unknown_or_deleted_user_are_404(client, action, deleted):
    if deleted:
        add_user(client.db_path, 3, "Gone", deleted=True)
    r = client.post(f"/api/users/3/{action}", headers=owner_headers(client))
    assert r.status_code == 404
