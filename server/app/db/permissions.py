from sqlalchemy import exists, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import permissions, user_device_permissions, user_permissions


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
