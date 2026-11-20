# 57 — Device detail screen

Step 8 (Devices) · Depends on: 56 · Size: M

## Goal

`/devices/:id`: view a box and, with `devices.manage`, manage it.

## Changes

- Read-only details: id, friendly name, MQTT account, last seen, firmware,
  whether each credential is provisioned.
- With `devices.manage`:
  - edit form (friendly name, MQTT account)
  - revoke / unrevoke switch, with a confirm step for revoking
  - regenerate OTA secret and regenerate device token, each through
    `confirmDanger` (the box stops working until it's reflashed), then
    `SecretReveal`
  - delete in a danger zone, then navigate to `/devices`
- Without it, the controls aren't rendered.
- 403 → NoPermission; 404 → NotFound.

## Tests

View-only rendering; the re-key flow; revoke confirms first; delete navigates.
