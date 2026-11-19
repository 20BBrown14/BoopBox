from dataclasses import dataclass

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import mapping_devices, mapping_entries, mappings, media_sources


@dataclass(frozen=True)
class Mapping:
    id: int
    slug: str
    all_devices: bool
    play_order: str
    play_type: str


@dataclass(frozen=True)
class Entry:
    id: int
    source_id: int
    item: str
    kind: str
    status: str
    source_usable: bool


async def find_by_slug(conn: AsyncConnection, slug: str) -> Mapping | None:
    m = mappings.c
    row = (
        await conn.execute(
            select(m.id, m.slug, m.all_devices, m.play_order, m.play_type).where(
                m.slug == slug
            )
        )
    ).first()
    if row is None:
        return None
    return Mapping(**{**row._mapping, "all_devices": bool(row.all_devices)})


async def device_listed(conn: AsyncConnection, mapping_id: int, device_id: str) -> bool:
    d = mapping_devices.c
    return bool(
        await conn.scalar(
            select(exists().where(d.mapping_id == mapping_id, d.device_id == device_id))
        )
    )


async def live_entries(conn: AsyncConnection, mapping_id: int) -> list[Entry]:
    """Live entries in play order, each flagged with whether its source is
    live and enabled."""
    e, s = mapping_entries.c, media_sources.c
    usable = (s.deleted_at.is_(None) & (s.enabled == 1)).label("source_usable")
    rows = await conn.execute(
        select(e.id, e.source_id, e.item, e.kind, e.status, usable)
        .join(media_sources, s.id == e.source_id)
        .where(e.mapping_id == mapping_id, e.deleted_at.is_(None))
        .order_by(e.position, e.created_at, e.id)
    )
    return [
        Entry(**{**row._mapping, "source_usable": bool(row.source_usable)})
        for row in rows
    ]


async def set_entry_status(
    conn: AsyncConnection, entry_id: int, status: str, now: str
) -> None:
    """Telemetry: doesn't bump updated_*."""
    await conn.execute(
        update(mapping_entries)
        .where(mapping_entries.c.id == entry_id)
        .values(status=status, status_checked_at=now)
    )
