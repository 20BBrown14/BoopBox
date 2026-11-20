# 05 — Validation and 404 handlers

Step 2 (Error shape) · Depends on: 04 · Size: S

## Goal

Framework-generated errors use the same `{code, message, field}` shape.

## Changes

- Handler for `RequestValidationError`: 422 `invalid_request`. `field` is the
  first error's location with the leading `body` / `query` / `path` removed and
  the rest joined by `.`. `message` is that error's `msg`. The submitted input
  is never echoed.
- Handler for Starlette `HTTPException` with status 404: `not_found` shape.
  Other statuses keep FastAPI's default.
- `routes/api/ota.py`: replace `HTTPException(404)` with
  `ApiError(not_found, field="device_id")`.

## Tests

- Missing body field → 422 with `field` set.
- Wrong type in a nested field → dotted `field`.
- Unknown `/api/...` path → 404 `not_found` JSON.
- OTA unknown device → 404 with `field = "device_id"`.

## Out of scope

SPA fallback 404s (task 23).

## Review focus

That no handler leaks request input into `message`.
