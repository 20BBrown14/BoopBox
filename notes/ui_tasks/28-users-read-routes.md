# 28 — `GET /api/users` and `GET /api/users/{id}`

Step 6 (Users and invites) · Depends on: 27, 05 · Size: S

## Goal

Read routes for the users screens.

## Changes

- `app/routes/api/users.py`, both routes behind
  `require_permission("users.manage")`.
- Pydantic `UserOut` and `UserDetailOut` matching task 27, except that the
  login is nested as `login: LoginOut | null`, the same shape as `GET /api/me`.
- An unknown or deleted id → 404 `not_found`.
- Add the router to `api_router`.
- The list is paginated: `?limit=` (1–200, default 50) and `?offset=`, answered
  with `{items, total, limit, offset}`. The shared `Page` and `PageParams` live
  in `app/routes/api/pagination.py`.

## Tests

- 403 without the permission; allowed with a grant; allowed for the owner.
- Response contains no `secret_hash`, `token_version` or identity internals.

## Review focus

Response model field names; the frontend types come from them.
