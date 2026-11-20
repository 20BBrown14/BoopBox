# 31 — `DELETE /api/users/{id}`

Step 6 (Users and invites) · Depends on: 30 · Size: S

## Goal

Soft delete as data_design.md "Deleting a user" describes.

## Changes

- Repo `users.delete_user(conn, user_id, actor, now)`, one transaction:
  - set `deleted_*` on the user and bump `token_version`
  - soft-delete the live identity (`deleted_by = actor`); the username stays
    reserved
  - soft-delete the user's unused invites
  - leave grants in place
- Owner and self → 422. Returns 204.

## Tests

The user disappears from the list; their token stops working; their username
can't log in; open invites are revoked; grants are untouched.
