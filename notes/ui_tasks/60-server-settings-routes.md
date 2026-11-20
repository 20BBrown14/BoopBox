# 60 — `/api/server-settings` routes

Step 9 (Server settings) · Depends on: 59, 05 · Size: S

## Goal

HTTP access to task 59.

## Changes

`app/routes/api/server_settings.py`, all behind
`require_permission("server_settings.manage")`:

- `GET /api/server-settings` → list of `SettingInfoOut`.
- `PUT /api/server-settings/{key}` `{value}` → the updated entry. Unknown key →
  404; `SettingError` → 422 on `value` (the message names the environment
  variable when a key is overridden).
- `DELETE /api/server-settings/{key}` → the updated entry.

## Tests

Permission checks; a secret round trip never returns the value; an
environment-overridden key gives 422; a retention value of `0` is accepted; the
MQTT entry has `restart_required`.

## Review focus

`value` is typed `Any` in OpenAPI. The UI narrows it by `kind`.
