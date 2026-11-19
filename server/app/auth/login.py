"""Local username/password login with lockout and login history.

Every failure looks the same to the caller; the history row says which it was.
"""

from datetime import UTC, datetime, timedelta

from app.auth.passwords import normalize_password, normalize_username, verify_password
from app.db import users
from app.db.engine import Database
from app.db.timestamps import timestamp
from app.db.users import AuthUser


async def login_local(
    db: Database,
    settings: dict,
    *,
    username: str,
    password: str,
    client_ip: str | None,
    user_agent: str | None,
) -> AuthUser | None:
    now_dt = datetime.now(UTC)
    now = timestamp(now_dt)
    subject = normalize_username(username)
    password = normalize_password(password)

    async def log(outcome: str, user_id: int | None, conn=None) -> None:
        values = dict(
            at=now,
            outcome=outcome,
            provider="local",
            user_id=user_id,
            identifier=username,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        if conn is not None:
            await users.add_history(conn, **values)
            return
        async with db.write() as own:
            await users.add_history(own, **values)

    async with db.read() as conn:
        found = await users.find_local(conn, subject)

    if found is None or found.identity_deleted:
        await verify_password(None, password)
        if found is None:
            await log("unknown_user", None)
        else:
            await log(
                "deleted" if found.user_deleted else "unknown_user", found.user_id
            )
        return None

    if found.locked_until is not None and found.locked_until > now:
        await log("locked", found.user_id)
        return None

    correct = await verify_password(found.secret_hash, password)
    minutes = timedelta(minutes=settings["auth.lockout_minutes"])

    async with db.write() as conn:
        if not correct:
            counted = await users.record_failure(
                conn,
                found.identity_id,
                now=now,
                window_start=timestamp(now_dt - minutes),
                threshold=settings["auth.lockout_threshold"],
                lock_until=timestamp(now_dt + minutes),
            )
            await log("bad_credentials" if counted else "locked", found.user_id, conn)
            return None
        if found.user_deleted:
            await log("deleted", found.user_id, conn)
            return None
        if found.user_disabled:
            await log("disabled", found.user_id, conn)
            return None
        if not await users.record_success(
            conn, found.identity_id, found.user_id, now=now
        ):
            await log("locked", found.user_id, conn)
            return None
        await log("success", found.user_id, conn)
        return await users.get_active(conn, found.user_id)


def client_address(
    peer: str | None, forwarded_for: str | None, trust_forwarded: bool
) -> str | None:
    """The rightmost X-Forwarded-For entry is the one the trusted proxy added."""
    if trust_forwarded and forwarded_for:
        last = forwarded_for.split(",")[-1].strip()
        if last:
            return last
    return peer
