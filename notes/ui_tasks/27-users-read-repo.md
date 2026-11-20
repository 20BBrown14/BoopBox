# 27 — Users read repository

Step 6 (Users and invites) · Depends on: — · Size: M

## Goal

List and detail queries for live users, with status derived as data_design.md
describes.

## Changes

In `app/db/users.py`:

- `UserSummary` dataclass: `id, display_name, email, is_owner, status, provider,
  username, label, last_login_at, locked, created_at`.
- `status`: `disabled` if disabled; else `pending` if there's no live identity;
  else `active`.
- `username` is the `subject` when the provider is `local`; `locked` is
  `locked_until > now`.
- `list_users(conn, now)`: live users only, ordered by display name.
- `get_user(conn, user_id, now) -> UserDetail | None`: adds
  `open_invite_expires_at` (the latest valid invite: unused, not revoked, not
  expired).

## Tests

Against a real database using the `conftest` helpers: each status, the locked
flag before and after `locked_until`, deleted users excluded, the open-invite
expiry ignoring used, revoked and expired invites.

## Review focus

One query with outer joins rather than a query per user.
