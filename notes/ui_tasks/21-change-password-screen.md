# 21 — Change password screen

Step 4 (Scaffold) · Depends on: 20, 10 · Size: S

## Goal

One form for both the forced first-login change and a voluntary change.

## Changes

- `/change-password`: current, new, confirm. Client checks: 12–128 characters,
  confirm matches. `POST /api/auth/password`.
- Forced mode (from `me.must_change_password`): explains why, and has no way
  to go anywhere else except logging out.
- On success: invalidate `['me']`, notification, go to `next` or `/`.
- A wrong current password shows on the current-password field.

## Tests

Forced mode text and navigation lock; length and confirm checks; wrong current
password; success refreshes `me`.
