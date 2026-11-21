from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Select, case, exists, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import auth_history, auth_identities, invites, users

UserStatus = Literal["active", "pending", "disabled"]


@dataclass(frozen=True)
class LocalLogin:
    identity_id: int
    user_id: int
    secret_hash: str | None
    identity_deleted: bool
    user_disabled: bool
    user_deleted: bool
    locked_until: str | None
    must_change_password: bool


@dataclass(frozen=True)
class Login:
    provider: str
    username: str | None  # local identities only
    label: str | None


@dataclass(frozen=True)
class AuthUser:
    id: int
    display_name: str
    is_owner: bool
    token_version: int
    identity_id: int | None
    must_change_password: bool


@dataclass(frozen=True)
class UserSummary:
    id: int
    display_name: str
    email: str | None
    is_owner: bool
    status: UserStatus
    provider: str | None
    username: str | None  # local identities only
    label: str | None
    last_login_at: str | None
    locked: bool
    created_at: str


@dataclass(frozen=True)
class UserDetail(UserSummary):
    open_invite_expires_at: str | None


def _not_locked(now: str):
    return or_(
        auth_identities.c.locked_until.is_(None),
        auth_identities.c.locked_until <= now,
    )


async def any_user(conn: AsyncConnection) -> bool:
    return bool(await conn.scalar(select(exists().select_from(users))))


async def create_owner(
    conn: AsyncConnection, username: str, secret_hash: str, now: str
) -> int:
    user_id = await conn.scalar(
        insert(users)
        .values(display_name=username, is_owner=1, created_at=now, updated_at=now)
        .returning(users.c.id)
    )
    await conn.execute(
        insert(auth_identities).values(
            user_id=user_id,
            provider="local",
            subject=username,
            secret_hash=secret_hash,
            must_change_password=1,
            created_at=now,
            updated_at=now,
        )
    )
    return user_id


async def find_local(conn: AsyncConnection, username: str) -> LocalLogin | None:
    """The local identity holding a username, deleted or not."""
    i, u = auth_identities.c, users.c
    row = (
        await conn.execute(
            select(
                i.id,
                i.user_id,
                i.secret_hash,
                i.deleted_at,
                i.locked_until,
                i.must_change_password,
                u.disabled,
                u.deleted_at.label("user_deleted_at"),
            )
            .join(users, users.c.id == i.user_id)
            .where(i.provider == "local", i.subject == username)
        )
    ).first()
    if row is None:
        return None
    return LocalLogin(
        identity_id=row.id,
        user_id=row.user_id,
        secret_hash=row.secret_hash,
        identity_deleted=row.deleted_at is not None,
        user_disabled=bool(row.disabled),
        user_deleted=row.user_deleted_at is not None,
        locked_until=row.locked_until,
        must_change_password=bool(row.must_change_password),
    )


async def record_failure(
    conn: AsyncConnection,
    identity_id: int,
    *,
    now: str,
    window_start: str,
    threshold: int,
    lock_until: str,
) -> bool:
    """Count a wrong password in one statement. False if a lock was already in
    place, in which case nothing is counted."""
    c = auth_identities.c
    restart = or_(c.last_failed_at.is_(None), c.last_failed_at < window_start)
    new_count = case((restart, 1), else_=c.failed_attempts + 1)
    result = await conn.execute(
        update(auth_identities)
        .where(c.id == identity_id, _not_locked(now))
        .values(
            failed_attempts=new_count,
            last_failed_at=now,
            locked_until=case((new_count >= threshold, lock_until), else_=None),
        )
    )
    return result.rowcount == 1


async def record_success(
    conn: AsyncConnection, identity_id: int, user_id: int, *, now: str
) -> bool:
    """Clear the failure counters. False if a lock started in the meantime."""
    c = auth_identities.c
    result = await conn.execute(
        update(auth_identities)
        .where(c.id == identity_id, _not_locked(now))
        .values(
            failed_attempts=0, last_failed_at=None, locked_until=None, last_used_at=now
        )
    )
    if result.rowcount != 1:
        return False
    await conn.execute(
        update(users).where(users.c.id == user_id).values(last_login_at=now)
    )
    return True


async def add_history(
    conn: AsyncConnection,
    *,
    at: str,
    outcome: str,
    provider: str,
    user_id: int | None,
    identifier: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    await conn.execute(
        insert(auth_history).values(
            at=at,
            outcome=outcome,
            provider=provider,
            user_id=user_id,
            identifier=identifier[:255] if identifier else identifier,
            client_ip=client_ip[:45] if client_ip else client_ip,
            user_agent=user_agent[:255] if user_agent else user_agent,
        )
    )


async def get_active(conn: AsyncConnection, user_id: int) -> AuthUser | None:
    """A user who may act: live and not disabled."""
    i, u = auth_identities.c, users.c
    row = (
        await conn.execute(
            select(
                u.id,
                u.display_name,
                u.is_owner,
                u.token_version,
                i.id.label("identity_id"),
                i.must_change_password,
            )
            .select_from(
                users.outerjoin(
                    auth_identities,
                    (i.user_id == u.id) & i.deleted_at.is_(None),
                )
            )
            .where(u.id == user_id, u.deleted_at.is_(None), u.disabled == 0)
        )
    ).first()
    if row is None:
        return None
    return AuthUser(
        id=row.id,
        display_name=row.display_name,
        is_owner=bool(row.is_owner),
        token_version=row.token_version,
        identity_id=row.identity_id,
        must_change_password=bool(row.must_change_password),
    )


async def get_login(conn: AsyncConnection, user_id: int) -> Login | None:
    """The user's live identity, as shown to people."""
    i = auth_identities.c
    row = (
        await conn.execute(
            select(i.provider, i.subject, i.label).where(
                i.user_id == user_id, i.deleted_at.is_(None)
            )
        )
    ).first()
    if row is None:
        return None
    return Login(
        provider=row.provider,
        username=row.subject if row.provider == "local" else None,
        label=row.label,
    )


def _summary_select() -> Select:
    """Live users, each with their live identity if they have one."""
    i, u = auth_identities.c, users.c
    return (
        select(
            u.id,
            u.display_name,
            u.email,
            u.is_owner,
            u.disabled,
            u.last_login_at,
            u.created_at,
            i.id.label("identity_id"),
            i.provider,
            i.subject,
            i.label,
            i.locked_until,
        )
        .select_from(
            users.outerjoin(
                auth_identities, (i.user_id == u.id) & i.deleted_at.is_(None)
            )
        )
        .where(u.deleted_at.is_(None))
    )


def _summary_fields(row, now: str) -> dict:
    if row.disabled:
        status: UserStatus = "disabled"
    elif row.identity_id is None:
        status = "pending"
    else:
        status = "active"
    return {
        "id": row.id,
        "display_name": row.display_name,
        "email": row.email,
        "is_owner": bool(row.is_owner),
        "status": status,
        "provider": row.provider,
        "username": row.subject if row.provider == "local" else None,
        "label": row.label,
        "last_login_at": row.last_login_at,
        "locked": row.locked_until is not None and row.locked_until > now,
        "created_at": row.created_at,
    }


async def list_users(
    conn: AsyncConnection, now: str, *, limit: int, offset: int
) -> list[UserSummary]:
    """A page of live users by display name. NOCASE only folds ASCII letters."""
    u = users.c
    rows = await conn.execute(
        _summary_select()
        .order_by(u.display_name.collate("NOCASE"), u.id)
        .limit(limit)
        .offset(offset)
    )
    return [UserSummary(**_summary_fields(row, now)) for row in rows]


async def count_users(conn: AsyncConnection) -> int:
    """Live users, for the total alongside a page from `list_users`."""
    return await conn.scalar(
        select(func.count()).select_from(users).where(users.c.deleted_at.is_(None))
    )


async def get_user(conn: AsyncConnection, user_id: int, now: str) -> UserDetail | None:
    """A live user, with the expiry of their open invite if there is one."""
    inv, u = invites.c, users.c
    open_invite = (
        select(func.max(inv.expires_at))
        .where(
            inv.user_id == u.id,
            inv.used_at.is_(None),
            inv.deleted_at.is_(None),
            inv.expires_at > now,
        )
        .scalar_subquery()
    )
    row = (
        await conn.execute(
            _summary_select()
            .add_columns(open_invite.label("open_invite_expires_at"))
            .where(u.id == user_id)
        )
    ).first()
    if row is None:
        return None
    return UserDetail(
        **_summary_fields(row, now),
        open_invite_expires_at=row.open_invite_expires_at,
    )


async def create_user(
    conn: AsyncConnection, display_name: str, email: str | None, actor: int, now: str
) -> int:
    """A pending user: no identity until an invite is redeemed."""
    return await conn.scalar(
        insert(users)
        .values(
            display_name=display_name,
            email=email,
            created_at=now,
            created_by=actor,
            updated_at=now,
            updated_by=actor,
        )
        .returning(users.c.id)
    )


@dataclass(frozen=True)
class UserChanges:
    """Fields to set on a user; None leaves that field alone. Clearing the email
    is `email=""`, stored as NULL."""

    display_name: str | None = None
    email: str | None = None
    disabled: bool | None = None


async def update_user(
    conn: AsyncConnection, user_id: int, changes: UserChanges, actor: int, now: str
) -> None:
    """Apply what differs from the stored values, stamping `updated_*` only if
    something does. Disabling also revokes the user's tokens."""
    u = users.c
    current = (
        await conn.execute(
            select(u.display_name, u.email, u.disabled).where(u.id == user_id)
        )
    ).one()
    values: dict = {}
    if (
        changes.display_name is not None
        and changes.display_name != current.display_name
    ):
        values["display_name"] = changes.display_name
    if changes.email is not None and (changes.email or None) != current.email:
        values["email"] = changes.email or None
    if changes.disabled is not None and changes.disabled != bool(current.disabled):
        values["disabled"] = int(changes.disabled)
        if changes.disabled:
            values["token_version"] = u.token_version + 1
    if not values:
        return
    await conn.execute(
        update(users)
        .where(u.id == user_id)
        .values(**values, updated_at=now, updated_by=actor)
    )


async def delete_user(
    conn: AsyncConnection, user_id: int, actor: int, now: str
) -> None:
    """Soft delete by hand, since ON DELETE CASCADE only fires on a real delete.
    The identity row stays, so a local username remains reserved. Grants stay
    too; the permission check ignores deleted users."""
    await conn.execute(
        update(users)
        .where(users.c.id == user_id, users.c.deleted_at.is_(None))
        .values(
            deleted_at=now, deleted_by=actor, token_version=users.c.token_version + 1
        )
    )
    i = auth_identities.c
    await conn.execute(
        update(auth_identities)
        .where(i.user_id == user_id, i.deleted_at.is_(None))
        .values(deleted_at=now, deleted_by=actor)
    )
    inv = invites.c
    await conn.execute(
        update(invites)
        .where(inv.user_id == user_id, inv.used_at.is_(None), inv.deleted_at.is_(None))
        .values(deleted_at=now, deleted_by=actor)
    )


async def set_last_login(conn: AsyncConnection, user_id: int, now: str) -> None:
    await conn.execute(
        update(users).where(users.c.id == user_id).values(last_login_at=now)
    )


async def clear_lock(conn: AsyncConnection, user_id: int) -> None:
    """Forget failed logins on the live identity. Telemetry, so not an edit."""
    i = auth_identities.c
    await conn.execute(
        update(auth_identities)
        .where(i.user_id == user_id, i.deleted_at.is_(None))
        .values(failed_attempts=0, last_failed_at=None, locked_until=None)
    )


async def get_secret_hash(conn: AsyncConnection, identity_id: int) -> str | None:
    return await conn.scalar(
        select(auth_identities.c.secret_hash).where(
            auth_identities.c.id == identity_id,
            auth_identities.c.provider == "local",
            auth_identities.c.deleted_at.is_(None),
        )
    )


async def change_password(
    conn: AsyncConnection, user_id: int, identity_id: int, secret_hash: str, now: str
) -> int:
    """Replace the hash, clear any lock and revoke existing tokens. Returns the
    new token version."""
    await conn.execute(
        update(auth_identities)
        .where(auth_identities.c.id == identity_id)
        .values(
            secret_hash=secret_hash,
            must_change_password=0,
            failed_attempts=0,
            last_failed_at=None,
            locked_until=None,
            updated_at=now,
        )
    )
    return await bump_token_version(conn, user_id)


async def bump_token_version(conn: AsyncConnection, user_id: int) -> int:
    """Revoke every token the user holds. Not an edit, so `updated_*` stays.
    Returns the new version."""
    return await conn.scalar(
        update(users)
        .where(users.c.id == user_id)
        .values(token_version=users.c.token_version + 1)
        .returning(users.c.token_version)
    )
