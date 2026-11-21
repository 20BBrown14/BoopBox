import pytest

from app.auth.invites import hash_code, new_code
from app.db import invites
from tests.conftest import T, add_identity, add_invite, add_user, query, run_sql

EARLIER = "2026-11-13T09:00:00.000Z"
LATER = "2026-11-20T09:30:00.000Z"
NOW = "2026-11-13T09:45:00.000Z"
HASH = "argon2-hash-stand-in"


@pytest.fixture
def db_path(env, services):
    return env.db_path


async def _write(services, fn, *args):
    async with services.db.write() as conn:
        return await fn(conn, *args)


async def _read(services, fn, *args):
    async with services.db.read() as conn:
        return await fn(conn, *args)


def _invite_rows(db_path, user_id):
    return query(
        db_path,
        "SELECT code_hash, used_at, deleted_at, deleted_by, created_by "
        "FROM invites WHERE user_id = ? ORDER BY id",
        (user_id,),
    )


def _identities(db_path, user_id):
    return query(
        db_path,
        "SELECT provider, subject, secret_hash, deleted_at, deleted_by "
        "FROM auth_identities WHERE user_id = ? ORDER BY id",
        (user_id,),
    )


def _token_version(db_path, user_id):
    return query(db_path, "SELECT token_version FROM users WHERE id = ?", (user_id,))[
        0
    ][0]


# Codes


def test_codes_are_random_and_long():
    codes = {new_code() for _ in range(100)}
    assert len(codes) == 100
    assert all(len(code) == 43 for code in codes)


# issue and revoke_open


async def test_issuing_twice_leaves_one_open_invite(services, db_path):
    add_user(db_path, 2, "Kid")
    await _write(services, invites.issue, 2, hash_code("first"), LATER, 1, T)
    await _write(services, invites.issue, 2, hash_code("second"), LATER, 1, NOW)

    rows = _invite_rows(db_path, 2)
    assert rows == [
        (hash_code("first"), None, NOW, 1, 1),
        (hash_code("second"), None, None, None, 1),
    ]


async def test_only_the_hash_is_stored(services, db_path):
    add_user(db_path, 2, "Kid")
    code = new_code()
    await _write(services, invites.issue, 2, hash_code(code), LATER, 1, T)

    dump = "\n".join(
        str(row) for row in query(db_path, "SELECT * FROM invites WHERE user_id = 2")
    )
    assert code not in dump
    assert hash_code(code) in dump


async def test_revoke_counts_unused_invites_and_leaves_used_ones(services, db_path):
    add_user(db_path, 2, "Kid")
    add_invite(db_path, 2, "open", expires_at=LATER)
    add_invite(db_path, 2, "expired", expires_at=EARLIER)
    add_invite(db_path, 2, "used", expires_at=LATER, used=True)
    add_invite(db_path, 2, "revoked", expires_at=LATER, revoked=True)

    assert await _write(services, invites.revoke_open, 2, 1, NOW) == 2
    assert [(row[2], row[3]) for row in _invite_rows(db_path, 2)] == [
        (NOW, 1),
        (NOW, 1),
        (None, None),
        (T, None),
    ]
    assert await _write(services, invites.revoke_open, 2, 1, NOW) == 0


async def test_revoke_only_touches_that_user(services, db_path):
    add_user(db_path, 2, "Kid")
    add_user(db_path, 3, "Other")
    add_invite(db_path, 3, "theirs", expires_at=LATER)
    assert await _write(services, invites.revoke_open, 2, 1, NOW) == 0
    assert _invite_rows(db_path, 3)[0][2] is None


# find_valid


async def test_find_valid_matches_an_open_invite(services, db_path):
    add_user(db_path, 2, "Kid")
    add_invite(db_path, 2, "open", expires_at=LATER, created_by=1)
    match = await _read(services, invites.find_valid, hash_code("open"), NOW)
    assert match == invites.InviteMatch(
        invite_id=match.invite_id, user_id=2, display_name="Kid", created_by=1
    )


@pytest.mark.parametrize(
    "setup",
    [
        lambda db: add_invite(db, 2, "code", expires_at=EARLIER),
        lambda db: add_invite(db, 2, "code", expires_at=NOW),
        lambda db: add_invite(db, 2, "code", expires_at=LATER, used=True),
        lambda db: add_invite(db, 2, "code", expires_at=LATER, revoked=True),
        lambda db: add_invite(db, 2, "other", expires_at=LATER),
        lambda db: (
            add_invite(db, 2, "code", expires_at=LATER),
            run_sql(db, "UPDATE users SET disabled = 1 WHERE id = 2"),
        ),
        lambda db: (
            add_invite(db, 2, "code", expires_at=LATER),
            run_sql(db, f"UPDATE users SET deleted_at = '{T}' WHERE id = 2"),
        ),
    ],
    ids=["expired", "expires-now", "used", "revoked", "unknown", "disabled", "deleted"],
)
async def test_find_valid_rejects(services, db_path, setup):
    add_user(db_path, 2, "Kid")
    setup(db_path)
    assert await _read(services, invites.find_valid, hash_code("code"), NOW) is None


# redeem_local


async def _redeem(services, code, username, secret_hash=HASH):
    async with services.db.write() as conn:
        return await invites.redeem_local(
            conn, hash_code(code), username, secret_hash, NOW
        )


async def test_first_redemption_creates_the_login(services, db_path):
    add_user(db_path, 2, "Kid")
    add_invite(db_path, 2, "code", expires_at=LATER, created_by=1)

    result = await _redeem(services, "code", "kid")
    assert result == invites.RedeemResult(user_id=2, token_version=0)
    assert query(
        db_path,
        "SELECT provider, subject, secret_hash, must_change_password, last_used_at, "
        "created_at, deleted_at FROM auth_identities WHERE user_id = 2",
    ) == [("local", "kid", HASH, 0, NOW, NOW, None)]
    assert _invite_rows(db_path, 2)[0][1] == NOW


async def test_an_invite_cannot_be_redeemed_twice(services, db_path):
    add_user(db_path, 2, "Kid")
    add_invite(db_path, 2, "code", expires_at=LATER)
    assert await _redeem(services, "code", "kid") is not None
    assert await _redeem(services, "code", "kid-again") is None
    assert len(_identities(db_path, 2)) == 1


async def test_an_invalid_invite_changes_nothing(services, db_path):
    add_user(db_path, 2, "Kid")
    add_invite(db_path, 2, "code", expires_at=EARLIER)
    assert await _redeem(services, "code", "kid") is None
    assert _identities(db_path, 2) == []


async def test_reinvite_with_a_new_username_replaces_the_login(services, db_path):
    add_user(db_path, 2, "Kid")
    add_identity(db_path, 2, "kid", secret_hash="old-hash")
    add_invite(db_path, 2, "code", expires_at=LATER, created_by=1)

    result = await _redeem(services, "code", "kiddo")
    assert result == invites.RedeemResult(user_id=2, token_version=1)
    assert _identities(db_path, 2) == [
        ("local", "kid", "old-hash", NOW, 1),
        ("local", "kiddo", HASH, None, None),
    ]


async def test_reinvite_revives_their_own_deleted_username(services, db_path):
    add_user(db_path, 2, "Kid")
    add_identity(db_path, 2, "kid", secret_hash="old-hash", deleted=True)
    add_identity(
        db_path, 2, "g-123", provider="google", issuer="https://accounts.google.com"
    )
    add_invite(db_path, 2, "code", expires_at=LATER, created_by=1)

    result = await _redeem(services, "code", "kid")
    assert result.token_version == 1
    assert _identities(db_path, 2) == [
        ("local", "kid", HASH, None, None),
        ("google", "g-123", None, NOW, 1),
    ]


async def test_reinvite_with_the_current_username_resets_it(services, db_path):
    add_user(db_path, 2, "Kid")
    add_identity(db_path, 2, "kid", secret_hash="old-hash", locked_until=LATER)
    run_sql(db_path, "UPDATE auth_identities SET failed_attempts = 5 WHERE user_id = 2")
    add_invite(db_path, 2, "code", expires_at=LATER, created_by=1)

    result = await _redeem(services, "code", "kid")
    assert result.token_version == 1
    assert query(
        db_path,
        "SELECT subject, secret_hash, failed_attempts, locked_until, deleted_at "
        "FROM auth_identities WHERE user_id = 2",
    ) == [("kid", HASH, 0, None, None)]


@pytest.mark.parametrize("deleted", [False, True])
async def test_someone_elses_username_is_taken(services, db_path, deleted):
    add_user(db_path, 2, "Kid")
    add_identity(db_path, 2, "kid")
    add_user(db_path, 3, "Other", deleted=deleted)
    add_identity(db_path, 3, "taken", deleted=deleted)
    add_invite(db_path, 2, "code", expires_at=LATER)

    with pytest.raises(invites.UsernameTaken):
        await _redeem(services, "code", "taken")
    assert _identities(db_path, 2) == [("local", "kid", None, None, None)]
    assert _invite_rows(db_path, 2)[0][1] is None
    assert _token_version(db_path, 2) == 0
