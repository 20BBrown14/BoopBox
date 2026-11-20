# 58 — `server_settings.manage` permission

Step 9 (Server settings) · Depends on: — · Size: S

## Goal

The permission the server settings routes require.

## Changes

- `CATALOG` in `app/permissions.py`: `"server_settings.manage": ("global",
  "edit server settings")`. Startup's `upsert_catalog` seeds it.
- data_design.md already lists it.

## Tests

The catalog row exists after startup; the owner passes `can()`; a granted user
passes.
