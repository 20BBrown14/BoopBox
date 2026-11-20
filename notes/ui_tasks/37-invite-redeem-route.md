# 37 — `POST /api/invites/redeem`

Step 6 (Users and invites) · Depends on: 36, 09 · Size: S

## Goal

The person picks a username and password and is logged in.

## Changes

- No auth, `require_json_same_origin`. Body `{code, username, password}`.
- `normalize_username` + `username_problem` → error on `username`;
  `normalize_password` + `password_problem` → error on `password`.
- Hash the password before opening the transaction.
- Invalid code → the same response as `/api/invites/check`. Conflict → 409 on
  `username`.
- Success counts as a login, inside the redemption transaction:
  - an `auth_history` row: outcome `success`, provider `local`, the typed
    username as `identifier`, and `client_ip` / `user_agent` the way
    `/api/auth/login` records them (`client_address`)
  - `users.last_login_at` and the new identity's `last_used_at` set to now
- Then issue a JWT and set the session cookies as login does; respond
  `{must_change_password: false}`.
- Failed redemptions (bad code, taken username, validation) write no history
  row.

## Tests

End to end: issue, check, redeem, then `/api/me` works with the cookie;
validation errors on the right fields; a taken username is 409 on `username`;
a successful redeem writes exactly one `success` history row and sets
`last_login_at`; a failed one writes none.

## Review focus

The history row and the redemption commit or roll back together.
