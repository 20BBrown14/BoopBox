# 51 — Permissions section: per-device grants

Step 7 (Permissions) · Depends on: 50 · Size: M

## Goal

Grant `device.view` and `device.control` on single boxes.

## Changes

- A row per device from the catalog response, with View and Control toggles.
  Rows are cards on phones.
- Control is disabled unless View is on for that device or granted globally.
  Turning View off also turns Control off.
- When a global `device.view` / `device.control` is on, the device toggles show
  as covered ("all boxes") and are disabled.
- Revoked devices are listed with a badge.
- No devices → a short empty state (devices arrive in step 8).

## Tests

Control can't be enabled without View; removing View clears Control; a global
grant covers the device rows; the saved payload contains only real per-device
grants.
