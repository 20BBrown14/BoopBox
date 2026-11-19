from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    id: str
    friendly_name: str | None = None
    mqtt_account: str | None = None
    revoked: bool = False
    # SHA-256 hex of the HTTP credentials; None means not provisioned.
    ota_secret_hash: str | None = None
    device_token_hash: str | None = None
    last_seen_at: str | None = None
    firmware_version: str | None = None
