import pytest
from sqlalchemy import event

from app.db import users
from tests.conftest import OWNER, T, add_identity, add_invite, add_user

EARLIER = "2026-11-13T09:00:00.000Z"
LATER = "2026-11-13T10:00:00.000Z"
MUCH_LATER = "2026-11-14T09:30:00.000Z"


@pytest.fixture
def db_path(env, services):
    return env.db_path


async def _list(services, now=T, *, limit=100, offset=0):
    async with services.db.read() as conn:
        return await users.list_users(conn, now, limit=limit, offset=offset)


async def _get(services, user_id, now=T):
    async with services.db.read() as conn:
        return await users.get_user(conn, user_id, now)


async def _by_id(services, now=T):
    return {user.id: user for user in await _list(services, now)}


async def test_status_is_derived(services, db_path):
    add_user(db_path, 2, "Active")
    add_identity(db_path, 2, "active")
    add_user(db_path, 3, "Pending")
    add_user(db_path, 4, "Re-invited")
    add_identity(db_path, 4, "old-name", deleted=True)
    add_user(db_path, 5, "Disabled", disabled=True)
    add_identity(db_path, 5, "disabled")
    add_user(db_path, 6, "Disabled pending", disabled=True)

    by_id = await _by_id(services)
    assert {user_id: user.status for user_id, user in by_id.items()} == {
        1: "active",
        2: "active",
        3: "pending",
        4: "pending",
        5: "disabled",
        6: "disabled",
    }


async def test_local_login_shows_the_username(services, db_path):
    add_user(db_path, 2, "Kid", email="kid@example.com", last_login_at=EARLIER)
    add_identity(db_path, 2, "kid")

    kid = (await _by_id(services))[2]
    assert kid == users.UserSummary(
        id=2,
        display_name="Kid",
        email="kid@example.com",
        is_owner=False,
        status="active",
        provider="local",
        username="kid",
        label=None,
        last_login_at=EARLIER,
        locked=False,
        created_at=T,
    )


async def test_external_login_shows_the_label_not_the_subject(services, db_path):
    add_user(db_path, 2, "Google user")
    add_identity(
        db_path,
        2,
        "109876543210",
        provider="google",
        issuer="https://accounts.google.com",
        label="someone@gmail.com",
    )

    user = (await _by_id(services))[2]
    assert (user.provider, user.username, user.label) == (
        "google",
        None,
        "someone@gmail.com",
    )


async def test_a_pending_user_has_no_login(services, db_path):
    add_user(db_path, 2, "Pending")
    add_identity(db_path, 2, "gone", deleted=True)

    user = (await _by_id(services))[2]
    assert (user.provider, user.username, user.label, user.locked) == (
        None,
        None,
        None,
        False,
    )


@pytest.mark.parametrize(
    ("locked_until", "now", "locked"),
    [
        (None, T, False),
        (LATER, T, True),
        (LATER, LATER, False),
        (LATER, MUCH_LATER, False),
    ],
)
async def test_locked_compares_with_now(services, db_path, locked_until, now, locked):
    add_user(db_path, 2, "Kid")
    add_identity(db_path, 2, "kid", locked_until=locked_until)

    assert (await _by_id(services, now))[2].locked is locked
    assert (await _get(services, 2, now)).locked is locked


async def test_deleted_users_are_left_out(services, db_path):
    add_user(db_path, 2, "Deleted", deleted=True)
    add_identity(db_path, 2, "deleted", deleted=True)

    assert 2 not in await _by_id(services)
    assert await _get(services, 2) is None


async def test_unknown_user_is_none(services):
    assert await _get(services, 999) is None


async def test_list_is_ordered_by_display_name(services, db_path):
    add_user(db_path, 2, "zed")
    add_user(db_path, 3, "Alice")
    add_user(db_path, 4, "bob")
    add_user(db_path, 5, "Bob")

    names = [user.display_name for user in await _list(services)]
    assert names == ["Alice", "bob", "Bob", OWNER, "zed"]


async def test_pages_follow_the_order(services, db_path):
    for user_id, name in enumerate(["Alice", "Bob", "Cat", "Dan"], start=2):
        add_user(db_path, user_id, name)

    async def names(limit, offset):
        return [
            u.display_name for u in await _list(services, limit=limit, offset=offset)
        ]

    assert await names(2, 0) == ["Alice", "Bob"]
    assert await names(2, 2) == ["Cat", "Dan"]
    assert await names(2, 4) == [OWNER]
    assert await names(2, 6) == []


async def test_count_users_counts_live_users(services, db_path):
    add_user(db_path, 2, "Pending")
    add_user(db_path, 3, "Disabled", disabled=True)
    add_user(db_path, 4, "Deleted", deleted=True)

    async with services.db.read() as conn:
        assert await users.count_users(conn) == 3


async def test_detail_matches_the_summary(services, db_path):
    add_user(db_path, 2, "Kid", email="kid@example.com")
    add_identity(db_path, 2, "kid")

    summary = (await _by_id(services))[2]
    detail = await _get(services, 2)
    assert detail == users.UserDetail(**vars(summary), open_invite_expires_at=None)


async def test_open_invite_ignores_finished_invites(services, db_path):
    add_user(db_path, 2, "Invited")
    add_invite(db_path, 2, "used", expires_at=MUCH_LATER, used=True)
    add_invite(db_path, 2, "revoked", expires_at=MUCH_LATER, revoked=True)
    add_invite(db_path, 2, "expired", expires_at=EARLIER)

    assert (await _get(services, 2)).open_invite_expires_at is None

    add_invite(db_path, 2, "open", expires_at=LATER)
    assert (await _get(services, 2)).open_invite_expires_at == LATER


async def test_open_invite_expires_with_time(services, db_path):
    add_user(db_path, 2, "Invited")
    add_invite(db_path, 2, "open", expires_at=LATER)

    assert (await _get(services, 2, now=T)).open_invite_expires_at == LATER
    assert (await _get(services, 2, now=LATER)).open_invite_expires_at is None


async def test_open_invite_is_the_latest_valid_one(services, db_path):
    add_user(db_path, 2, "Invited")
    add_invite(db_path, 2, "first", expires_at=LATER)
    add_invite(db_path, 2, "second", expires_at=MUCH_LATER)

    assert (await _get(services, 2)).open_invite_expires_at == MUCH_LATER


async def test_open_invite_belongs_to_that_user(services, db_path):
    add_user(db_path, 2, "Invited")
    add_user(db_path, 3, "Other")
    add_invite(db_path, 3, "theirs", expires_at=LATER)

    assert (await _get(services, 2)).open_invite_expires_at is None
    assert (await _get(services, 3)).open_invite_expires_at == LATER


async def test_list_is_one_query(services, db_path):
    for user_id in range(2, 7):
        add_user(db_path, user_id, f"User {user_id}")
        add_identity(db_path, user_id, f"user-{user_id}")

    selects = []
    async with services.db.read() as conn:
        sync_engine = conn.sync_engine

        def record(_conn, _cursor, statement, *_args):
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        event.listen(sync_engine, "before_cursor_execute", record)
        try:
            assert len(await users.list_users(conn, T, limit=100, offset=0)) == 6
        finally:
            event.remove(sync_engine, "before_cursor_execute", record)
    assert len(selects) == 1, selects
