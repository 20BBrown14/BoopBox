# 04 — `ApiError`, `field`, and the new error codes

Step 2 (Error shape) · Depends on: 01 · Size: S

## Goal

One way for any `/api` handler to fail: raise `ApiError(code, message?, field?)`
and get `{code, message, field?}` with the right status.

## Context

- `app/errors.py` has `ErrorCode`, `HTTP_STATUS`, `http_error()`. Routes
  currently build `JSONResponse` by hand (`routes/api/auth.py`).
- `AuthError` (in `app/auth/deps.py`) uses the code's default message, which for
  `unauthorized` / `forbidden` says "stream token". User routes return that text
  today.

## Changes

- `ErrorCode.not_found` (404) and `ErrorCode.conflict` (409), with generic
  default messages.
- `http_error(code, message=None, field=None)` adds `field` only when given.
- `ApiError(Exception)` in `app/errors.py` and an exception handler in
  `main.py`.
- `AuthError` raised by the user dependencies carries a neutral message
  ("authentication required" / "not allowed"). Stream route messages are
  unchanged.
- Convert the hand-built error responses in `routes/api/auth.py` to `ApiError`
  (the login 401 keeps its `WWW-Authenticate` header).

## Tests

- `test_errors.py`: new codes map to their statuses; `field` present only when
  set.
- A user route rejection no longer mentions "stream token".
- Stream error tests unchanged.

## Out of scope

Pydantic validation errors (task 05).

## Review focus

The `HTTP_STATUS` invariant (MQTT-only codes stay absent) still holds.
