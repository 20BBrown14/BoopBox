from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import devices as t
from app.types.device import Device


async def get(conn: AsyncConnection, device_id: str) -> Device | None:
    """A live (not deleted) device, revoked or not."""
    row = (
        await conn.execute(
            select(
                t.c.id,
                t.c.friendly_name,
                t.c.mqtt_account,
                t.c.revoked,
                t.c.ota_secret_hash,
                t.c.device_token_hash,
                t.c.last_seen_at,
                t.c.firmware_version,
            ).where(t.c.id == device_id, t.c.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        return None
    return Device(**{**row._mapping, "revoked": bool(row.revoked)})


async def touch(
    conn: AsyncConnection,
    device_id: str,
    now: str,
    firmware_version: str | None = None,
) -> None:
    """Telemetry: never bumps updated_*, never touches a revoked device."""
    values: dict = {"last_seen_at": now}
    if firmware_version is not None:
        values["firmware_version"] = firmware_version
    await conn.execute(
        update(t)
        .where(t.c.id == device_id, t.c.revoked == 0, t.c.deleted_at.is_(None))
        .values(**values)
    )
