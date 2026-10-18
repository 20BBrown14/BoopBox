"""Database schema and per-connection pragmas.

Schema DDL lives here (not in the repositories) so new tables and future
migration steps are added in one place. `init_schema` is idempotent and runs on
every startup; it is the seam where a real migration runner would slot in later.
"""

import aiosqlite

PRAGMAS = (
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA foreign_keys = ON;",
    "PRAGMA busy_timeout = 5000;",
)

# Ordered DDL statements applied at startup. Append new tables here; each should
# be idempotent (CREATE TABLE IF NOT EXISTS).
SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS devices (
        id                 TEXT PRIMARY KEY,
        friendly_name      TEXT,
        mqtt_account       TEXT,
        revoked            INTEGER NOT NULL DEFAULT 0,
        last_seen_at       TEXT,
        firmware_version   TEXT,
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL
    );
    """,
)


async def apply_pragmas(conn: aiosqlite.Connection) -> None:
    for pragma in PRAGMAS:
        await conn.execute(pragma)


async def init_schema(conn: aiosqlite.Connection) -> None:
    """Create all tables if absent. Idempotent."""
    for statement in SCHEMA_STATEMENTS:
        await conn.execute(statement)
    await conn.commit()
