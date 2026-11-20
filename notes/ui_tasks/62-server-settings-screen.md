# 62 — Server settings screen

Step 9 (Server settings) · Depends on: 61, 40 · Size: M

## Goal

`/server-settings`, grouped and safe to edit.

## Changes

- `RequirePermission("server_settings.manage")`.
- Sections by key prefix, titled from `groups.*`.
- Each row: label, help, `SettingField`, a "changed from default" marker, a
  Reset button (editable and non-default only), and its own Save. Each setting
  saves on its own, so there's no page-wide form.
- Environment-overridden rows: a lock icon and the `env_name`.
- Generated secrets: "set; rotation isn't available yet".
- Retention keys (`*.retention_days`): saving a shorter period confirms first.
  Changing `0` (forever) to anything else counts as shorter.
- After saving an `mqtt.*` key: a persistent "restart the server to apply"
  alert.

## Tests

Grouping; reset; the overridden row is read-only and shows the variable name;
the retention confirm appears only when the period gets shorter; the MQTT
restart alert.
