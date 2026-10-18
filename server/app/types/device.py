from dataclasses import dataclass


@dataclass
class Device:
    id: str
    friendly_name: str | None = None
    mqtt_account: str | None = None
    revoked: bool = False
    last_seen_at: str | None = None
    firmware_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
