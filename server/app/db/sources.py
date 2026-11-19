from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import media_sources as t


@dataclass(frozen=True)
class SourceRow:
    id: int
    type: str
    name: str
    base_url: str
    settings: str
    secret_encrypted: str | None
    enabled: bool


async def get(conn: AsyncConnection, source_id: int) -> SourceRow | None:
    """A live source, enabled or not."""
    row = (
        await conn.execute(
            select(
                t.c.id,
                t.c.type,
                t.c.name,
                t.c.base_url,
                t.c.settings,
                t.c.secret_encrypted,
                t.c.enabled,
            ).where(t.c.id == source_id, t.c.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        return None
    return SourceRow(**{**row._mapping, "enabled": bool(row.enabled)})


async def set_secret(
    conn: AsyncConnection, source_id: int, ciphertext: str | None, now: str
) -> bool:
    result = await conn.execute(
        update(t)
        .where(t.c.id == source_id, t.c.deleted_at.is_(None))
        .values(secret_encrypted=ciphertext, updated_at=now, updated_by=None)
    )
    return result.rowcount == 1
