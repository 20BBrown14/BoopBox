from sqlalchemy import Row, select, union_all
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import media_sources
from app.db.tables import settings as t


async def all_rows(conn: AsyncConnection) -> list[Row]:
    result = await conn.execute(select(t.c.key, t.c.value, t.c.encrypted))
    return list(result)


async def get(conn: AsyncConnection, key: str) -> Row | None:
    result = await conn.execute(
        select(t.c.key, t.c.value, t.c.encrypted).where(t.c.key == key)
    )
    return result.first()


async def put(
    conn: AsyncConnection,
    key: str,
    value: str,
    *,
    encrypted: bool,
    now: str,
    actor: int | None = None,
) -> None:
    stmt = insert(t).values(
        key=key, value=value, encrypted=int(encrypted), updated_at=now, updated_by=actor
    )
    await conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[t.c.key],
            set_={
                "value": stmt.excluded.value,
                "encrypted": stmt.excluded.encrypted,
                "updated_at": stmt.excluded.updated_at,
                "updated_by": stmt.excluded.updated_by,
            },
        )
    )


async def encrypted_values(conn: AsyncConnection) -> list[str]:
    """Every stored ciphertext, including those on deleted sources."""
    query = union_all(
        select(t.c.value).where(t.c.encrypted == 1),
        select(media_sources.c.secret_encrypted).where(
            media_sources.c.secret_encrypted.is_not(None)
        ),
    )
    return list((await conn.execute(query)).scalars())
