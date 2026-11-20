# 55 — Device write routes

Step 8 (Devices) · Depends on: 53, 54 · Size: M

## Goal

The `devices.manage` routes from ui_design.md "Devices".

## Changes

All require `devices.manage`. Responses carrying secrets set
`Cache-Control: no-store`.

- `POST /api/devices` `{id, friendly_name?, mqtt_account?}` → 201 `{device,
  ota_secret, device_token}`. Both secrets are generated; only their hashes are
  stored.
- `PATCH /api/devices/{id}`: `friendly_name`, `mqtt_account`, `revoked`
  (applying only fields that were sent).
- `DELETE /api/devices/{id}` → 204.
- `POST /api/devices/{id}/ota-secret` and `/device-token` → `{secret}`.
- Length limits from data_design.md, using the task 26 helpers.

## Tests

- Returned secrets work against `require_device_ota` and `require_device_api`;
  regenerating invalidates the old one.
- Revoking blocks both credentials.
- 409 on a taken or deleted id.
- No hash appears in any response.
