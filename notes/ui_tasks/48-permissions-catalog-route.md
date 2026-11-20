# 48 — `GET /api/permissions`

Step 7 (Permissions) · Depends on: 05 · Size: S

## Goal

Everything the grant editor needs to draw itself.

## Changes

- `users.manage` required.
- Response: `{permissions: [{id, scope}], devices: [{id, friendly_name,
  revoked}]}`, where `devices` is every live device.
- No descriptions. The UI translates by permission id (task 50); the English
  descriptions in `CATALOG` stay for the database row.

## Tests

Shape; deleted devices excluded; 403 without `users.manage`.

## Review focus

**Decision to check.** Device ids are included here because `GET /api/devices`
only returns devices the caller can `device.view`. A `users.manage` holder
without `device.view` couldn't otherwise grant per-device permissions. The cost
is that `users.manage` reveals every device's id and name.
