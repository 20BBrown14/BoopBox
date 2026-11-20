from dataclasses import dataclass, field

from sqlalchemy import exists, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import (
    devices,
    permissions,
    user_device_permissions,
    user_permissions,
)


@dataclass
class Grants:
    global_ids: set[str] = field(default_factory=set)
    devices: dict[str, set[str]] = field(default_factory=dict)


async def list_grants(conn: AsyncConnection, user_id: int) -> Grants:
    """Stored grants only; the owner's implicit access isn't included. Grants on
    deleted devices are inert and left out."""
    g = user_permissions.c
    global_rows = await conn.execute(
        select(g.permission_id).where(g.user_id == user_id)
    )
    grants = Grants(global_ids=set(global_rows.scalars()))
    d = user_device_permissions.c
    rows = await conn.execute(
        select(d.device_id, d.permission_id)
        .join(devices, devices.c.id == d.device_id)
        .where(d.user_id == user_id, devices.c.deleted_at.is_(None))
    )
    for device_id, permission_id in rows:
        grants.devices.setdefault(device_id, set()).add(permission_id)
    return grants


async def upsert_catalog(
    conn: AsyncConnection, catalog: dict[str, tuple[str, str]]
) -> None:
    """Rows not in the catalog are left alone; grants may still reference them."""
    for perm_id, (scope, description) in catalog.items():
        stmt = insert(permissions).values(
            id=perm_id, scope=scope, description=description
        )
        await conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[permissions.c.id],
                set_={
                    "scope": stmt.excluded.scope,
                    "description": stmt.excluded.description,
                },
            )
        )


async def has_grant(
    conn: AsyncConnection, user_id: int, permission: str, device_id: str | None
) -> bool:
    g = user_permissions.c
    if await conn.scalar(
        select(exists().where(g.user_id == user_id, g.permission_id == permission))
    ):
        return True
    if device_id is None:
        return False
    d = user_device_permissions.c
    return bool(
        await conn.scalar(
            select(
                exists().where(
                    d.user_id == user_id,
                    d.device_id == device_id,
                    d.permission_id == permission,
                )
            )
        )
    )
