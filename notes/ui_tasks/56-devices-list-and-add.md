# 56 — Devices list and add device

Step 8 (Devices) · Depends on: 55, 38, 39, 40 · Size: M

## Goal

`/devices`, the landing page for every user.

## Changes

- Regenerate the API types. Hooks with keys `['devices', 'list', {limit, offset}]`
  and `['devices', id]`; mutations invalidate `['devices']`. The add and re-key
  mutations follow the secret rule from task 40.
- Paginated like the users list (task 42): `Pagination` when `total > limit`,
  page number in `?page`.
- `src/locales/en/devices.json`.
- Columns through `ResponsiveList`: name (friendly name, with the id beneath it),
  revoked badge, last seen (`Timestamp`), firmware version.
- Empty state for users who can see no devices.
- "Add device" (only with `devices.manage`): id (with a live character-set
  hint), friendly name, MQTT account. Then a `SecretReveal` with both secrets,
  and a hint naming the firmware `secrets.yaml` keys they go into.

## Tests

The list renders; the empty state; the add button is hidden without the
permission; the add flow shows both secrets; a 409 lands on `id`.
