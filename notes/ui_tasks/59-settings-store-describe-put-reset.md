# 59 — `SettingsStore.describe`, `put` and `reset`

Step 9 (Server settings) · Depends on: 58 · Size: M

## Goal

The store can describe, write and reset server settings. Today it can only read
them.

## Context

`app/settings/store.py` has `snapshot`, `get` and `overridden`.
`app/db/settings.py` has `put` but no delete. `keyring.canary` is stored in the
same table but isn't in `REGISTRY`, so it is never exposed.

## Changes

- `describe() -> list[SettingInfo]`, with every field from the entry example in
  ui_design.md "Server settings":
  - secrets: `value` and `default` are None; `is_set` is true when an
    environment value or a row exists
  - `is_default`: no row and no environment value
  - `editable`: false when overridden by the environment or `generated`
  - `restart_required`: `key.startswith("mqtt.")`
- `put(key, value, actor)`:
  - unknown key → `KeyError`; not editable → `SettingError`
  - `Setting.validate`; `json.dumps`; secrets encrypted with
    `setting_aad(key)`; written through `rows.put` with `actor`
  - `backup.directory`: create the directory, then write and delete a probe file;
    a failure is a `SettingError`
- `reset(key, actor)`: new `rows.delete(conn, key)`. Same editability rule.

## Tests

Secrets stored encrypted and never returned by `describe`; environment-overridden
and generated keys refused; reset falls back to the default; an unwritable
backup directory is refused; `snapshot` reflects writes.
