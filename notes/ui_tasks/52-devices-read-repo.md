# 52 — Devices read repository

Step 8 (Devices) · Depends on: 11 · Size: S

## Goal

Queries for the device screens, following data_design.md "Device visibility".

## Changes

In `app/db/devices.py`:

- `DeviceSummary` dataclass: `id, friendly_name, mqtt_account, revoked,
  last_seen_at, firmware_version, ota_secret_set, device_token_set,
  created_at, updated_at`. No hashes.
- `list_all(conn)` and `list_for_user(conn, user_id)`. The second returns live
  devices with a `device.view` row for that user.
- `get_summary(conn, device_id)`.

The existing `get()` (which returns hashes for authentication) is unchanged.

## Tests

The visibility split; deleted devices excluded; the `*_set` flags.
