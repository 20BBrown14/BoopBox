import aiosqlite

from app.db.schema import apply_pragmas


async def connect(db_path: str) -> aiosqlite.Connection:
    """Open a connection with the standard pragmas applied.

    aiosqlite runs each connection on its own thread, keeping blocking SQLite
    calls off the event loop.
    """
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await apply_pragmas(conn)
    return conn
