# 54 — Devices write repository

Step 8 (Devices) · Depends on: 52, 26 · Size: M

## Goal

Create, edit, revoke, delete and re-key devices.

## Changes

- `app/devices.py` (or `app/auth/`): `new_device_secret()`
  (`secrets.token_urlsafe(32)`); `device_id_problem(value)` (1–32 characters,
  `a-z 0-9 _ -`). Ids are validated as typed, not lowercased for the user.
- Repo in `app/db/devices.py`:
  - `create(conn, id, friendly_name, mqtt_account, ota_hash, token_hash, actor,
    now)`. A primary-key `IntegrityError` becomes conflict; a deleted device's
    row still holds its id.
  - `update(conn, id, values, actor, now)`, applying only the given fields.
  - `soft_delete(conn, id, actor, now)`: sets `deleted_*` and deletes the
    device's `playback_progress` rows in the same transaction.
  - `set_ota_secret_hash` and `set_device_token_hash`; each bumps `updated_*`.

## Tests

Conflict on a live id and on a deleted id; delete removes progress rows; re-key
changes the hash and `updated_at`; telemetry columns are never written.

## Review focus

Grants on a deleted device are left in place. They are inert (the device is
hidden and treated as revoked), which matches how user deletion is handled.
