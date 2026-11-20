# 10 — Password change for cookie sessions, and `logout-all`

Step 3 (Browser session) · Depends on: 09 · Size: S

## Goal

A password change keeps the browser logged in, and a user can log out every
other session.

## Changes

- `POST /api/auth/password`: when `request.state.auth_via == "cookie"`, respond
  `{must_change_password: false}` and set new cookies for the new
  `token_version`. Bearer callers keep today's body with `access_token`.
- A wrong current password is 403 `forbidden` with `field = "current_password"`
  (task 21 shows it on that field).
- New repo function `users.bump_token_version(conn, user_id) -> int`.
- `POST /api/auth/logout-all` (`require_user`): bump, then re-issue this
  session the same way (cookie or token body).

## Tests

- After a cookie password change: the old session cookie and the old CSRF value
  fail, the new ones work.
- After `logout-all`: another token for the same user is rejected, the caller's
  re-issued session works, other users are unaffected.

## Review focus

The bump and the new token use the same version, so the caller isn't logged out
by their own request.
