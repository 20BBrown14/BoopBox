# 32 — Unlock and log a user out everywhere

Step 6 (Users and invites) · Depends on: 28, 10 · Size: S

## Goal

Two admin actions on another user.

## Changes

- `POST /api/users/{id}/unlock` → 204. Repo `users.clear_lock(conn, user_id)`
  clears `failed_attempts`, `last_failed_at` and `locked_until` on the live
  identity. It is telemetry, so `updated_*` isn't bumped.
- `POST /api/users/{id}/logout-all` → 204 through `bump_token_version`. Allowed
  on the owner.

## Tests

A locked user can log in after unlock; `updated_at` unchanged by unlock; the
target's token rejected after logout-all.
