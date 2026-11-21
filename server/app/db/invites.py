from dataclasses import dataclass

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db import users as user_rows
from app.db.tables import auth_identities, invites, users


class UsernameTaken(Exception):
    """The local username belongs to another user, live or deleted."""


@dataclass(frozen=True)
class InviteMatch:
    invite_id: int
    user_id: int
    display_name: str
    created_by: int | None


@dataclass(frozen=True)
class RedeemResult:
    user_id: int
    token_version: int


async def revoke_open(conn: AsyncConnection, user_id: int, actor: int, now: str) -> int:
    """Revoke the user's unused invites, expired ones included. Returns how many."""
    c = invites.c
    result = await conn.execute(
        update(invites)
        .where(c.user_id == user_id, c.used_at.is_(None), c.deleted_at.is_(None))
        .values(deleted_at=now, deleted_by=actor)
    )
    return result.rowcount


async def issue(
    conn: AsyncConnection,
    user_id: int,
    code_hash: str,
    expires_at: str,
    actor: int,
    now: str,
) -> int:
    """A new invite, replacing any the user still has open."""
    await revoke_open(conn, user_id, actor, now)
    return await conn.scalar(
        insert(invites)
        .values(
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
            created_at=now,
            created_by=actor,
        )
        .returning(invites.c.id)
    )


async def find_valid(
    conn: AsyncConnection, code_hash: str, now: str
) -> InviteMatch | None:
    """An unused, unrevoked, unexpired invite for a live, enabled user."""
    c, u = invites.c, users.c
    row = (
        await conn.execute(
            select(c.id, c.user_id, c.created_by, u.display_name)
            .join(users, u.id == c.user_id)
            .where(
                c.code_hash == code_hash,
                c.used_at.is_(None),
                c.deleted_at.is_(None),
                c.expires_at > now,
                u.deleted_at.is_(None),
                u.disabled == 0,
            )
        )
    ).first()
    if row is None:
        return None
    return InviteMatch(
        invite_id=row.id,
        user_id=row.user_id,
        display_name=row.display_name,
        created_by=row.created_by,
    )


async def redeem_local(
    conn: AsyncConnection, code_hash: str, username: str, secret_hash: str, now: str
) -> RedeemResult | None:
    """Give the invited user a local login, in the caller's write transaction.

    None if the invite is no longer valid. Raises UsernameTaken. A user who
    already had a login is re-invited: their tokens are revoked, and a
    different identity is soft-deleted before the new one goes live, because
    auth_identities_user allows one live identity per user.
    """
    invite = await find_valid(conn, code_hash, now)
    if invite is None:
        return None
    held = await user_rows.find_local(conn, username)
    if held is not None and held.user_id != invite.user_id:
        raise UsernameTaken

    i = auth_identities.c
    live_id = await conn.scalar(
        select(i.id).where(i.user_id == invite.user_id, i.deleted_at.is_(None))
    )
    try:
        if live_id is not None and (held is None or held.identity_id != live_id):
            await conn.execute(
                update(auth_identities)
                .where(i.id == live_id)
                .values(deleted_at=now, deleted_by=invite.created_by)
            )
        login_values = dict(
            secret_hash=secret_hash,
            must_change_password=0,
            failed_attempts=0,
            last_failed_at=None,
            locked_until=None,
            last_used_at=now,
            updated_at=now,
        )
        if held is not None:
            # Their own username, reserved by their old row: revive it.
            await conn.execute(
                update(auth_identities)
                .where(i.id == held.identity_id)
                .values(**login_values, deleted_at=None, deleted_by=None)
            )
        else:
            await conn.execute(
                insert(auth_identities).values(
                    **login_values,
                    user_id=invite.user_id,
                    provider="local",
                    subject=username,
                    created_at=now,
                )
            )
    except IntegrityError as err:
        raise UsernameTaken from err

    await conn.execute(
        update(invites).where(invites.c.id == invite.invite_id).values(used_at=now)
    )
    if live_id is not None:
        version = await user_rows.bump_token_version(conn, invite.user_id)
    else:
        version = await conn.scalar(
            select(users.c.token_version).where(users.c.id == invite.user_id)
        )
    return RedeemResult(user_id=invite.user_id, token_version=version)
