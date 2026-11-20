# 49 — `GET` / `PUT /api/users/{id}/permissions`

Step 7 (Permissions) · Depends on: 47, 48, 28 · Size: M

## Goal

Read and replace one user's grants, with every rule from ui_design.md
"Permissions".

## Changes

- `GET` → `{is_owner, global, devices}`.
- `PUT` body `{global: [...], devices: {device_id: [...]}}`, validated in order:
  - target is the owner, or yourself → 422
  - unknown permission id → 422 on `global` or `devices.<id>`
  - a `device`-scope id in `global`, or a `global`-scope id under a device → 422
  - unknown or deleted device → 422 on `devices.<id>`
  - `device.control` on a device without `device.view` on it or globally → 422
    on `devices.<id>`
- Unknown or deleted target user → 404. Writes through `replace_grants`.
- Changes take effect on the next request; no token bump needed.

## Tests

One test per rule; a successful replace is readable back; `granted_by` is the
caller.
