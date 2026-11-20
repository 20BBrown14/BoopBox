# 29 — `POST /api/users`

Step 6 (Users and invites) · Depends on: 26, 28 · Size: S

## Goal

Create a pending user.

## Changes

- Repo `users.create_user(conn, display_name, email, actor, now) -> int`, which
  stamps `created_*` and `updated_*`.
- Route: body `{display_name, email?}`. `display_name` is cleaned, single-line,
  1–64. `email` is cleaned; empty becomes NULL; otherwise `email_problem`.
- Returns 201 with `UserDetailOut`; status is `pending`.

## Tests

Field errors for each rule; empty email stored as NULL; actor stamped;
`users.manage` required.
