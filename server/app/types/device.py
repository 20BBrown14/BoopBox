from dataclasses import dataclass


@dataclass
class Device:
    id: str
    friendly_name: str | None = None
    mqtt_account: str | None = None
    revoked: bool = False
    # SHA-256 hashes of the device's auth secrets. ota_secret_hash backs the
    # HTTP Basic password on the firmware bin fetch; device_token_hash backs the
    # Authorization: Bearer token on device API routes. None until provisioned.
    ota_secret_hash: str | None = None
    device_token_hash: str | None = None
    last_seen_at: str | None = None
    firmware_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
