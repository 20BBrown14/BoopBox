# 30 — `PATCH /api/users/{id}`

Step 6 (Users and invites) · Depends on: 29, 10 · Size: S

## Goal

Edit a user's name and email, and disable or enable them.

## Changes

- Body fields are all optional: `display_name`, `email`, `disabled`. Only fields
  actually sent are applied (`model_fields_set`), so `"email": null` clears the
  email and an absent `email` leaves it alone.
- Rules:
  - the owner can't be disabled → 422 on `disabled`
  - you can't disable yourself → 422 on `disabled`
  - disabling bumps `token_version` in the same transaction; enabling doesn't
- Repo `users.update_user(...)` stamps `updated_*` only when something changed.

## Tests

Partial updates; clearing email; owner and self rules; disabling revokes an
existing token; 404 for a deleted user.
