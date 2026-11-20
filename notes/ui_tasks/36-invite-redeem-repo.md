# 36 — Invite redemption transaction

Step 6 (Users and invites) · Depends on: 35 · Size: M

## Goal

The data side of data_design.md "Invite and redeem" and "Re-invite", as one
transaction.

## Changes

`invites.redeem_local(conn, code_hash, username, secret_hash, now) ->
RedeemResult(user_id, token_version)` in a write transaction:

1. Re-read the invite with `find_valid` inside the transaction. Gone → None.
2. `users.find_local(username)`:
   - held by a different user (live or deleted) → raise conflict
   - held by this user → revive that row: clear `deleted_*`, set the new hash,
     clear lock counters
3. If the user has a different live identity, soft-delete it with
   `deleted_by` = the invite's `created_by`.
4. Insert the new identity unless one was revived.
5. Set the invite's `used_at`.
6. Bump `token_version` when an identity was replaced.

A unique-index `IntegrityError` (a race) becomes conflict.

## Tests

First redemption; re-invite with a new username; re-invite reviving the same
username; another live or deleted user's username → conflict; an invite can't be
redeemed twice; the old identity's `deleted_by` is the issuer.

## Review focus

Ordering inside the transaction against the unique indexes on
`auth_identities`.
