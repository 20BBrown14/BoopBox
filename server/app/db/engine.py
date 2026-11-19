from contextlib import asynccontextmanager

from sqlalchemy import URL, event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
)


def create_db_engine(db_path: str) -> AsyncEngine:
    """Async engine with the connection pragmas and explicit BEGIN.

    The sqlite3 driver's default transaction handling doesn't wrap DDL, so it
    is switched off and BEGIN is emitted here. Pass the execution option
    `sqlite_begin="IMMEDIATE"` to take the write lock when the transaction
    starts.
    """
    engine = create_async_engine(URL.create("sqlite+aiosqlite", database=db_path))

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn, _record) -> None:
        dbapi_conn.isolation_level = None
        cursor = dbapi_conn.cursor()
        # Must precede journal_mode = WAL, which writes the file's first page.
        # A no-op on a database that already has tables.
        cursor.execute("PRAGMA auto_vacuum = INCREMENTAL")
        for pragma in PRAGMAS:
            cursor.execute(pragma)
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(conn) -> None:
        mode = conn.get_execution_options().get("sqlite_begin", "DEFERRED")
        if mode not in ("DEFERRED", "IMMEDIATE", "EXCLUSIVE"):
            raise ValueError(f"unknown sqlite_begin mode: {mode}")
        conn.exec_driver_sql(f"BEGIN {mode}")

    return engine


class Database:
    """Reads run in a deferred transaction; writes take the write lock up
    front, so a read-then-write can't fail on a lock upgrade."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @classmethod
    def open(cls, db_path: str) -> "Database":
        return cls(create_db_engine(db_path))

    @asynccontextmanager
    async def read(self):
        async with self.engine.connect() as conn:
            yield conn

    @asynccontextmanager
    async def write(self):
        async with self.engine.connect() as conn:
            conn = await conn.execution_options(sqlite_begin="IMMEDIATE")
            async with conn.begin():
                yield conn

    async def ping(self) -> None:
        async with self.read() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()


__all__ = ["AsyncConnection", "Database", "create_db_engine"]
