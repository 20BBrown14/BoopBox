# 01 — `/api` router and the `/auth/*` move

Step 1 (Move routes) · Depends on: — · Size: S

## Goal

Create the `/api` router package and move the two existing auth routes under it
with no behavior change.

## Context

- `app/routes/auth.py` defines `POST /auth/token` and `POST /auth/password`.
- `app/routes/__init__.py` exports the routers; `app/main.py` includes them.
- Callers: `tests/conftest.py::login`, `tests/test_auth.py` (`/auth/password`),
  `scripts/ota_trigger.sh`, README OTA curl example.

## Changes

- New package `app/routes/api/` with `__init__.py` exposing `api_router`
  (`APIRouter(prefix="/api")`) that includes each resource router.
- Move `app/routes/auth.py` to `app/routes/api/auth.py`; paths become
  `/auth/token` and `/auth/password` relative to the prefix.
- `app/routes/__init__.py` and `main.py` include `api_router` instead of
  `auth_router`.
- Update `conftest.login`, `test_auth.py`, `scripts/ota_trigger.sh` and the
  README OTA curl example to `/api/auth/token`.

## Tests

- Existing suite passes unchanged apart from paths.
- New: `POST /auth/token` returns 404.

## Out of scope

Cookie login, error shape, README auth prose (task 03).

## Review focus

Pure move: the diff of the route bodies should be empty.
