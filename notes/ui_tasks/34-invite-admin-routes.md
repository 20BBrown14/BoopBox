# 34 — Issue and revoke invites (admin routes)

Step 6 (Users and invites) · Depends on: 33, 28 · Size: S

## Goal

An admin issues an invite and receives the code and link exactly once.

## Changes

- `POST /api/users/{id}/invites` → 201 `{code, url, expires_at}` with
  `Cache-Control: no-store`.
  - `expires_at` = now + `invites.expiry_days`.
  - `url` = `public_base_url` + `/invite#code=` + code. The setting is already
    stored without a trailing slash.
  - Owner → 422 with a clear message. Deleted or unknown user → 404.
  - Allowed for both pending and active users; for an active user it is a
    re-invite.
  - A disabled user → 422 ("enable the user before inviting them"), since
    `find_valid` would refuse the invite anyway.
- `DELETE /api/users/{id}/invites` → 204.

## Tests

`url` follows the setting and `BOOPBOX_PUBLIC_BASE_URL`; an earlier invite is
revoked; owner rejected; the response has `no-store`.
