# 03 — Fix the README authentication section

Step 1 (Move routes) · Depends on: 01, 02 · Size: S

## Goal

The README "Authentication" section describes a design that no longer exists.
Make it match the code.

## Context

- README says `POST /auth/token` checks `BOOPBOX_AUTH_USERNAME` /
  `BOOPBOX_AUTH_PASSWORD` and signs with `BOOPBOX_JWT_SECRET`.
- Reality (`app/startup.py`, `app/auth/*`): the owner is bootstrapped from
  `BOOPBOX_DEFAULT_USERNAME` / `BOOPBOX_DEFAULT_PASSWORD` on first run and must
  change the password at first login. Users live in SQLite. Tokens are signed
  with the generated `secrets.auth_token` setting, last
  `auth.token_lifetime_hours`, and are revoked through `token_version`. Local
  logins lock after `auth.lockout_threshold` failures.

## Changes

- Rewrite the "User auth" paragraph and the principal table row to the above,
  with `/api/auth/token` and `/api/auth/password`.
- Remove stale auth variables from the `.env` reference section and list
  `BOOPBOX_DEFAULT_USERNAME` / `BOOPBOX_DEFAULT_PASSWORD`.

## Tests

None (docs only).

## Out of scope

UI and dev-workflow docs (task 63). Other stale README sections.

## Review focus

Accuracy against the code; keep it short.
