from datetime import UTC, datetime

import aiosqlite

from app.types.device import Device


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class DeviceRepository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def get(self, device_id: str) -> Device | None:
        async with self._conn.execute(
            "SELECT id, friendly_name, mqtt_account, revoked, last_seen_at, "
            "firmware_version, created_at, updated_at FROM devices WHERE id = ?",
            (device_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return Device(
            id=row["id"],
            friendly_name=row["friendly_name"],
            mqtt_account=row["mqtt_account"],
            revoked=bool(row["revoked"]),
            last_seen_at=row["last_seen_at"],
            firmware_version=row["firmware_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def upsert(self, device: Device) -> None:
        """Insert or update. Sets created_at on insert only; always refreshes
        updated_at."""
        now = _utcnow()
        await self._conn.execute(
            """
            INSERT INTO devices (
                id, friendly_name, mqtt_account, revoked,
                last_seen_at, firmware_version, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                friendly_name = excluded.friendly_name,
                mqtt_account = excluded.mqtt_account,
                revoked = excluded.revoked,
                last_seen_at = excluded.last_seen_at,
                firmware_version = excluded.firmware_version,
                updated_at = excluded.updated_at
            """,
            (
                device.id,
                device.friendly_name,
                device.mqtt_account,
                int(device.revoked),
                device.last_seen_at,
                device.firmware_version,
                now,
                now,
            ),
        )
        await self._conn.commit()

    async def update_last_seen(
        self, device_id: str, firmware_version: str | None = None
    ) -> None:
        """Stamp last_seen_at (and firmware_version when provided)."""
        now = _utcnow()
        if firmware_version is not None:
            await self._conn.execute(
                "UPDATE devices SET last_seen_at = ?, firmware_version = ?, "
                "updated_at = ? WHERE id = ?",
                (now, firmware_version, now, device_id),
            )
        else:
            await self._conn.execute(
                "UPDATE devices SET last_seen_at = ?, updated_at = ? WHERE id = ?",
                (now, now, device_id),
            )
        await self._conn.commit()


async def seed_device(repo: DeviceRepository, device_id: str) -> None:
    """Upsert the seed device if absent. Idempotent: an existing row keeps its
    created_at. The MQTT password is a broker concern and is not stored here."""
    existing = await repo.get(device_id)
    if existing is None:
        await repo.upsert(Device(id=device_id, friendly_name="Seed test device"))
