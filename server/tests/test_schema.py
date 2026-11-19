import re
import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db import migrate
from app.db.engine import create_db_engine
from app.db.migrate import (
    SCHEMA_VERSION,
    SchemaError,
    check_sqlite_version,
    prepare_database,
)
from app.db.tables import metadata
from app.db.timestamps import timestamp

T = "2026-11-13T09:30:00.000Z"


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "boopbox.db")


@pytest.fixture
async def engine(db_path):
    eng = create_db_engine(db_path)
    try:
        yield eng
    finally:
        await eng.dispose()


def _open(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
async def db(engine, db_path):
    await prepare_database(engine)
    conn = _open(db_path)
    conn.executescript(
        f"""
        INSERT INTO users (id, display_name, is_owner, created_at, updated_at)
            VALUES (1, 'Owner', 1, '{T}', '{T}');
        INSERT INTO users (id, display_name, created_at, updated_at)
            VALUES (2, 'Kid', '{T}', '{T}');
        INSERT INTO devices (id, created_at, updated_at)
            VALUES ('boop-1', '{T}', '{T}');
        INSERT INTO media_sources (id, type, name, name_key, base_url,
                                   created_at, updated_at)
            VALUES (1, 'jellyfin', 'Home', 'home', 'http://jf', '{T}', '{T}');
        INSERT INTO mappings (id, slug, name, created_at, updated_at)
            VALUES (1, 'boop/zelda', 'Zelda', '{T}', '{T}');
        """
    )
    try:
        yield conn
    finally:
        conn.close()


def _scalar(conn, sql):
    return conn.execute(sql).fetchone()[0]


# --- startup states ---------------------------------------------------------


async def test_creates_schema(engine, db_path):
    await prepare_database(engine)
    conn = _open(db_path)
    rows = conn.execute(
        "SELECT name, strict FROM pragma_table_list "
        "WHERE schema = 'main' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    assert {name for name, _ in rows} == set(metadata.tables)
    assert all(strict == 1 for _, strict in rows)
    assert conn.execute("SELECT id, version FROM schema_info").fetchall() == [
        (1, SCHEMA_VERSION)
    ]
    assert _scalar(conn, "PRAGMA auto_vacuum") == 2
    assert _scalar(conn, "PRAGMA journal_mode") == "wal"
    conn.close()


async def test_engine_connection_pragmas(engine):
    async with engine.connect() as conn:
        assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar() == 5000


async def test_prepare_twice_is_a_no_op(engine, db_path):
    await prepare_database(engine)
    await prepare_database(engine)
    conn = _open(db_path)
    assert _scalar(conn, "SELECT count(*) FROM schema_info") == 1
    conn.close()


async def test_refuses_unversioned_database(engine, db_path):
    conn = _open(db_path)
    conn.execute("CREATE TABLE devices (id TEXT PRIMARY KEY)")
    conn.close()
    with pytest.raises(SchemaError, match="no schema_info"):
        await prepare_database(engine)


async def test_refuses_newer_database(engine, db_path):
    await prepare_database(engine)
    conn = _open(db_path)
    conn.execute("UPDATE schema_info SET version = ?", (SCHEMA_VERSION + 1,))
    conn.close()
    with pytest.raises(SchemaError, match="newer than this server"):
        await prepare_database(engine)


async def test_refuses_older_database_without_migration(engine, db_path):
    await prepare_database(engine)
    conn = _open(db_path)
    conn.execute("UPDATE schema_info SET version = ?", (SCHEMA_VERSION - 1,))
    conn.close()
    with pytest.raises(SchemaError, match="no migration"):
        await prepare_database(engine)


async def test_migration_runs_and_bumps_version(engine, db_path, monkeypatch):
    await prepare_database(engine)
    conn = _open(db_path)
    conn.execute("UPDATE schema_info SET version = ?", (SCHEMA_VERSION - 1,))
    conn.close()

    def step(c):
        c.exec_driver_sql("CREATE TABLE migrated (x INTEGER) STRICT")

    monkeypatch.setitem(migrate.MIGRATIONS, SCHEMA_VERSION, step)
    await prepare_database(engine)

    conn = _open(db_path)
    assert _scalar(conn, "SELECT version FROM schema_info") == SCHEMA_VERSION
    assert _scalar(conn, "SELECT count(*) FROM sqlite_schema WHERE name = 'migrated'")
    conn.close()


async def test_failed_migration_rolls_back_ddl(engine, db_path, monkeypatch):
    await prepare_database(engine)
    conn = _open(db_path)
    conn.execute("UPDATE schema_info SET version = ?", (SCHEMA_VERSION - 1,))
    conn.close()

    def step(c):
        c.exec_driver_sql("CREATE TABLE half_done (x INTEGER) STRICT")
        raise RuntimeError("boom")

    monkeypatch.setitem(migrate.MIGRATIONS, SCHEMA_VERSION, step)
    with pytest.raises(RuntimeError, match="boom"):
        await prepare_database(engine)

    conn = _open(db_path)
    assert _scalar(conn, "SELECT version FROM schema_info") == SCHEMA_VERSION - 1
    assert not _scalar(
        conn, "SELECT count(*) FROM sqlite_schema WHERE name = 'half_done'"
    )
    conn.close()


def test_sqlite_version_check():
    check_sqlite_version((3, 37, 0))
    with pytest.raises(SchemaError, match="3.37.0 or newer"):
        check_sqlite_version((3, 36, 9))


# --- timestamps -------------------------------------------------------------


def test_timestamp_format():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", timestamp())
    local = datetime(
        2026, 11, 13, 4, 30, 0, 123999, tzinfo=timezone(timedelta(hours=-5))
    )
    assert timestamp(local) == "2026-11-13T09:30:00.123Z"
    with pytest.raises(ValueError):
        timestamp(datetime(2026, 1, 1))


async def test_timestamp_helper_passes_db_check(db):
    now = timestamp(datetime.now(UTC))
    db.execute("UPDATE users SET last_login_at = ? WHERE id = 2", (now,))


# --- constraints ------------------------------------------------------------

REJECTED = {
    "timestamp with offset": (
        "UPDATE users SET last_login_at = '2026-11-13T09:30:00.000+00:00' WHERE id = 2"
    ),
    "timestamp without millis": (
        "UPDATE users SET last_login_at = '2026-11-13T09:30:00Z' WHERE id = 2"
    ),
    "impossible date": (
        "UPDATE users SET last_login_at = '2026-02-30T09:30:00.000Z' WHERE id = 2"
    ),
    "flag out of range": "UPDATE users SET disabled = 2 WHERE id = 2",
    "strict type": "UPDATE users SET token_version = 'abc' WHERE id = 2",
    "second owner": "UPDATE users SET is_owner = 1 WHERE id = 2",
    "disabled owner": "UPDATE users SET disabled = 1 WHERE id = 1",
    "deleted owner": f"UPDATE users SET deleted_at = '{T}' WHERE id = 1",
    "empty display name": "UPDATE users SET display_name = '' WHERE id = 2",
    "uppercase device id": (
        "INSERT INTO devices (id, created_at, updated_at) "
        f"VALUES ('Boop', '{T}', '{T}')"
    ),
    "slash in device id": (
        f"INSERT INTO devices (id, created_at, updated_at) VALUES ('a/b', '{T}', '{T}')"
    ),
    "device id too long": (
        "INSERT INTO devices (id, created_at, updated_at) "
        f"VALUES ('{'a' * 33}', '{T}', '{T}')"
    ),
    "short token hash": "UPDATE devices SET device_token_hash = 'abc'",
    "uppercase slug": (
        "INSERT INTO mappings (slug, name, created_at, updated_at) "
        f"VALUES ('Boop/X', 'X', '{T}', '{T}')"
    ),
    "duplicate slug": (
        "INSERT INTO mappings (slug, name, created_at, updated_at) "
        f"VALUES ('boop/zelda', 'X', '{T}', '{T}')"
    ),
    "bad play_type": "UPDATE mappings SET play_type = 'shuffle'",
    "lowercase tag uid": (
        "INSERT INTO tags (uid, first_seen_at, first_seen_device_id, first_slug, "
        "last_seen_at, last_seen_device_id, last_slug) "
        f"VALUES ('04:a1', '{T}', 'boop-1', '', '{T}', 'boop-1', '')"
    ),
    "uppercase setting key": (
        "INSERT INTO settings (key, value, updated_at) "
        f"VALUES ('MQTT.host', '1', '{T}')"
    ),
    "played boop without item": (
        "INSERT INTO boops (received_at, device_id, outcome, source_id) "
        f"VALUES ('{T}', 'boop-1', 'played', 1)"
    ),
    "unknown boop device": (
        f"INSERT INTO boops (received_at, device_id, outcome) "
        f"VALUES ('{T}', 'nope', 'unknown_tag')"
    ),
    "succeeded backup without path": (
        "INSERT INTO backups (started_at, finished_at, status, origin, size_bytes) "
        f"VALUES ('{T}', '{T}', 'succeeded', 'manual', 1)"
    ),
    "duplicate live source name": (
        "INSERT INTO media_sources (type, name, name_key, base_url, "
        f"created_at, updated_at) VALUES ('jellyfin', 'HOME', 'home', 'http://b', "
        f"'{T}', '{T}')"
    ),
    "duplicate live source endpoint": (
        "INSERT INTO media_sources (type, name, name_key, base_url, "
        f"created_at, updated_at) VALUES ('jellyfin', 'Other', 'other', 'http://jf', "
        f"'{T}', '{T}')"
    ),
}


@pytest.mark.parametrize("sql", REJECTED.values(), ids=REJECTED.keys())
async def test_rejected(db, sql):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql)


def _identity(db, user_id, provider, subject, *, issuer="", deleted=False):
    db.execute(
        "INSERT INTO auth_identities (user_id, provider, issuer, subject, "
        "created_at, updated_at, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, provider, issuer, subject, T, T, T if deleted else None),
    )


async def test_one_live_identity_per_user(db):
    _identity(db, 2, "local", "kid", deleted=True)
    _identity(db, 2, "google", "sub-1", issuer="https://accounts.google.com")
    with pytest.raises(sqlite3.IntegrityError):
        _identity(db, 2, "local", "kid2")


async def test_local_username_stays_reserved_after_delete(db):
    _identity(db, 2, "local", "kid", deleted=True)
    with pytest.raises(sqlite3.IntegrityError):
        _identity(db, 1, "local", "kid")


async def test_external_account_freed_after_delete(db):
    google = "https://accounts.google.com"
    _identity(db, 2, "google", "sub-1", issuer=google, deleted=True)
    _identity(db, 1, "google", "sub-1", issuer=google)
    with pytest.raises(sqlite3.IntegrityError):
        _identity(db, 2, "google", "sub-1", issuer=google)


async def test_deleted_source_frees_name_and_endpoint(db):
    db.execute(f"UPDATE media_sources SET deleted_at = '{T}' WHERE id = 1")
    db.execute(
        "INSERT INTO media_sources (type, name, name_key, base_url, created_at, "
        f"updated_at) VALUES ('jellyfin', 'Home', 'home', 'http://jf', '{T}', '{T}')"
    )


async def test_deleting_mapping_cascades_and_keeps_boops(db):
    db.executescript(
        f"""
        INSERT INTO mapping_entries (id, mapping_id, source_id, item, position,
                                     created_at, updated_at)
            VALUES (1, 1, 1, 'item-1', 0, '{T}', '{T}');
        INSERT INTO mapping_devices (mapping_id, device_id, created_at)
            VALUES (1, 'boop-1', '{T}');
        INSERT INTO playback_progress (mapping_id, device_id, queue, created_at,
                                       last_played_at)
            VALUES (1, 'boop-1', '[]', '{T}', '{T}');
        INSERT INTO boops (id, received_at, device_id, slug, outcome, mapping_id,
                           entry_id, source_id, item)
            VALUES (1, '{T}', 'boop-1', 'boop/zelda', 'played', 1, 1, 1, 'item-1');
        DELETE FROM mappings WHERE id = 1;
        """
    )
    for table in ("mapping_entries", "mapping_devices", "playback_progress"):
        assert _scalar(db, f"SELECT count(*) FROM {table}") == 0
    assert db.execute(
        "SELECT mapping_id, entry_id, slug, item FROM boops WHERE id = 1"
    ).fetchone() == (None, None, "boop/zelda", "item-1")


async def test_autoincrement_never_reuses_ids(db):
    db.execute(
        f"INSERT INTO backups (id, started_at, status, origin) "
        f"VALUES (5, '{T}', 'failed', 'manual')"
    )
    db.execute("DELETE FROM backups WHERE id = 5")
    db.execute(
        f"INSERT INTO backups (started_at, status, origin) "
        f"VALUES ('{T}', 'failed', 'manual')"
    )
    assert _scalar(db, "SELECT max(id) FROM backups") == 6
