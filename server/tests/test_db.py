import asyncio
import threading

import pytest

from app.db import DeviceRepository, connect, init_schema, seed_device
from app.types.device import Device


@pytest.fixture
async def conn(tmp_path):
    db_path = str(tmp_path / "devices.db")
    connection = await connect(db_path)
    await init_schema(connection)
    try:
        yield connection
    finally:
        await connection.close()


async def test_pragmas_applied(conn):
    async def scalar(pragma):
        async with conn.execute(pragma) as cur:
            row = await cur.fetchone()
        return row[0]

    assert (await scalar("PRAGMA journal_mode;")).lower() == "wal"
    assert int(await scalar("PRAGMA synchronous;")) == 1  # NORMAL
    assert int(await scalar("PRAGMA foreign_keys;")) == 1  # ON
    assert int(await scalar("PRAGMA busy_timeout;")) == 5000


async def test_schema_created(conn):
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='devices'"
    ) as cur:
        row = await cur.fetchone()
    assert row is not None


async def test_repo_round_trip(conn):
    repo = DeviceRepository(conn)
    await repo.upsert(Device(id="boop-1", friendly_name="Kitchen"))

    fetched = await repo.get("boop-1")
    assert fetched is not None
    assert fetched.friendly_name == "Kitchen"
    assert fetched.revoked is False
    assert fetched.created_at is not None
    assert fetched.updated_at is not None

    assert await repo.get("missing") is None


async def test_update_last_seen(conn):
    repo = DeviceRepository(conn)
    await repo.upsert(Device(id="boop-1"))

    await repo.update_last_seen("boop-1", firmware_version="0.2.0")
    fetched = await repo.get("boop-1")
    assert fetched.last_seen_at is not None
    assert fetched.firmware_version == "0.2.0"


async def test_seed_idempotent(conn):
    repo = DeviceRepository(conn)
    await seed_device(repo, "boop-test")
    first = await repo.get("boop-test")
    assert first is not None

    await seed_device(repo, "boop-test")
    second = await repo.get("boop-test")

    # Still exactly one row, created_at unchanged by the second seed.
    async with conn.execute("SELECT COUNT(*) FROM devices") as cur:
        count = (await cur.fetchone())[0]
    assert count == 1
    assert second.created_at == first.created_at


async def test_db_call_runs_off_loop(conn):
    # aiosqlite dispatches to a dedicated connection thread. A SQL-invoked
    # callback runs on that thread; assert it is not the event loop's thread.
    loop_thread = threading.current_thread().ident
    captured = {}

    def _record() -> int:
        captured["thread"] = threading.current_thread().ident
        return 1

    await conn.create_function("record_thread", 0, _record)
    async with conn.execute("SELECT record_thread()"):
        pass

    assert captured["thread"] is not None
    assert captured["thread"] != loop_thread
    assert asyncio.get_running_loop() is not None
