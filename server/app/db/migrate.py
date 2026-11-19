"""Startup schema check: create a new database, or verify an existing one's
version. Migrations to later versions are registered in MIGRATIONS."""

import logging
import sqlite3
from collections.abc import Callable

from sqlalchemy import Connection, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.tables import metadata, schema_info
from app.db.timestamps import timestamp

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MIN_SQLITE_VERSION = (3, 37, 0)

# MIGRATIONS[n] upgrades a database from version n - 1 to n.
MIGRATIONS: dict[int, Callable[[Connection], None]] = {}


class SchemaError(RuntimeError):
    pass


def check_sqlite_version(
    version: tuple[int, int, int] = sqlite3.sqlite_version_info,
) -> None:
    if version < MIN_SQLITE_VERSION:
        need = ".".join(map(str, MIN_SQLITE_VERSION))
        have = ".".join(map(str, version))
        raise SchemaError(f"SQLite {need} or newer is required; found {have}")


async def prepare_database(engine: AsyncEngine) -> None:
    """Bring the database to SCHEMA_VERSION or raise SchemaError.

    Runs in one IMMEDIATE transaction, so a failure leaves the database as it
    was and a second process can't prepare it at the same time.
    """
    check_sqlite_version()
    async with engine.connect() as conn:
        conn = await conn.execution_options(sqlite_begin="IMMEDIATE")
        async with conn.begin():
            await conn.run_sync(_prepare)


def _prepare(conn: Connection) -> None:
    tables = set(
        conn.execute(
            text(
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ).scalars()
    )
    if not tables:
        _create(conn)
        return
    if schema_info.name not in tables:
        raise SchemaError(
            "the database has tables but no schema_info table, so it wasn't "
            "created by BoopBox; point the server at a new file"
        )

    version = conn.execute(select(schema_info.c.version)).scalar_one_or_none()
    if version is None:
        raise SchemaError("schema_info has no row")
    if version > SCHEMA_VERSION:
        raise SchemaError(
            f"the database is at schema version {version}, newer than this "
            f"server's {SCHEMA_VERSION}; upgrade the server"
        )
    if version == SCHEMA_VERSION:
        log.info("database schema is at version %d", version)
        return

    for target in range(version + 1, SCHEMA_VERSION + 1):
        step = MIGRATIONS.get(target)
        if step is None:
            raise SchemaError(f"no migration from schema version {target - 1}")
        log.info("migrating database schema to version %d", target)
        step(conn)
    conn.execute(update(schema_info).values(version=SCHEMA_VERSION))


def _create(conn: Connection) -> None:
    if conn.exec_driver_sql("PRAGMA auto_vacuum").scalar() != 2:
        raise SchemaError("auto_vacuum is not INCREMENTAL on the new database")
    metadata.create_all(conn, checkfirst=False)
    conn.execute(
        insert(schema_info).values(id=1, version=SCHEMA_VERSION, created_at=timestamp())
    )
    log.info("created database schema version %d", SCHEMA_VERSION)
