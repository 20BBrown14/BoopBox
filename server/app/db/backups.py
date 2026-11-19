from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import backups as t


async def fail_interrupted(conn: AsyncConnection, now: str) -> int:
    """A `running` row at startup was left behind by a crash."""
    result = await conn.execute(
        update(t)
        .where(t.c.status == "running")
        .values(status="failed", finished_at=now, error="interrupted")
    )
    return result.rowcount
