# 53 — `GET /api/devices` and `GET /api/devices/{id}`

Step 8 (Devices) · Depends on: 52 · Size: S

## Goal

Read routes for the device screens.

## Changes

- `app/routes/api/devices.py`.
- List (`require_user`): the owner or a holder of global `device.view` gets
  `list_all`; anyone else gets `list_for_user`.
- Detail: `require_permission("device.view", device_param="device_id")`, then
  404 if the device doesn't exist.
- Pydantic `DeviceOut`.

## Tests

The visibility matrix (owner, global view, per-device view, none); detail 403
vs 404; no hash fields anywhere in the responses.

## Review focus

A non-holder gets 403 even for a device that doesn't exist, so they can't probe
which ids exist. Holders get 404.
