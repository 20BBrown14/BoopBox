# 33 — Invites repository: issue and revoke

Step 6 (Users and invites) · Depends on: — · Size: S

## Goal

Store invites as data_design.md "invites" describes.

## Changes

- `app/auth/invites.py`: `new_code() -> str` (`secrets.token_urlsafe(32)`), and
  hashing through `app/security.hash_secret`.
- New `app/db/invites.py`:
  - `issue(conn, user_id, code_hash, expires_at, actor, now) -> int`: first
    revokes (soft-deletes) the user's open invites, then inserts.
  - `revoke_open(conn, user_id, actor, now) -> int`.

## Tests

Issuing twice leaves one open invite; only the hash is stored; revoke counts
correctly; used invites are never touched by revoke.
