from dataclasses import dataclass

from sqlalchemy import insert
from sqlalchemy.dialects.sqlite import insert as upsert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import boops, tags


@dataclass(frozen=True)
class BoopRecord:
    device_id: str
    outcome: str
    uid: str | None = None
    slug: str | None = None
    correlation_id: str | None = None
    box_at: str | None = None
    mapping_id: int | None = None
    entry_id: int | None = None
    source_id: int | None = None
    item: str | None = None


async def record(conn: AsyncConnection, rec: BoopRecord, now: str) -> None:
    """Upsert the tag (when the payload was readable) and log the boop."""
    tag_id = None
    if rec.uid is not None:
        slug = rec.slug or ""
        stmt = upsert(tags).values(
            uid=rec.uid,
            first_seen_at=now,
            first_seen_device_id=rec.device_id,
            first_slug=slug,
            last_seen_at=now,
            last_seen_device_id=rec.device_id,
            last_slug=slug,
        )
        tag_id = await conn.scalar(
            stmt.on_conflict_do_update(
                index_elements=[tags.c.uid],
                set_={
                    "last_seen_at": stmt.excluded.last_seen_at,
                    "last_seen_device_id": stmt.excluded.last_seen_device_id,
                    "last_slug": stmt.excluded.last_slug,
                },
            ).returning(tags.c.id)
        )
    await conn.execute(
        insert(boops).values(
            received_at=now,
            device_id=rec.device_id,
            tag_id=tag_id,
            slug=rec.slug,
            box_at=rec.box_at,
            correlation_id=rec.correlation_id,
            outcome=rec.outcome,
            mapping_id=rec.mapping_id,
            entry_id=rec.entry_id,
            source_id=rec.source_id,
            item=rec.item,
        )
    )
