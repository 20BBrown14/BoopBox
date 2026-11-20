# 02 — Move `POST /ota/update` to `/api/ota/update`

Step 1 (Move routes) · Depends on: 01 · Size: S

## Goal

`POST /ota/update` is a human action guarded by `ota.manage`, not a box route.
Under decision 12b (everything human-facing under `/api`) it moves to
`/api/ota/update`.

## Context

- `app/routes/ota.py` holds only this route. Box-facing firmware routes live in
  `app/routes/firmware.py` and are untouched.
- ui_design.md lists `/ota` as an unchanged box-facing prefix. That was wrong
  for this route; task 64 corrects the doc.
- Callers: `tests/test_ota_policy.py` (several), `scripts/ota_trigger.sh`,
  README "Testing OTA end to end" curl example.

## Changes

- Move the file to `app/routes/api/ota.py` and include it in `api_router`.
- Update the test paths, the script and the README example.

## Tests

- Existing OTA endpoint tests pass at the new path.
- New: `POST /ota/update` returns 404.

## Out of scope

Replacing its `HTTPException(404)` with the new error type (task 05).

## Review focus

Confirm you agree this route is human-facing and should move.
