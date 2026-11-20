# 07 — Cookie authentication and CSRF enforcement in `require_user`

Step 3 (Browser session) · Depends on: 06 · Size: M

## Goal

User dependencies accept the session cookie as well as the bearer header, and
cookie-authenticated writes must carry a valid CSRF header.

## Context

`app/auth/deps.py::_authenticate` reads only `Authorization: Bearer`. Both
`require_user` and `require_user_allow_password_change` go through it.

## Changes

- Header present → bearer path, exactly as today. Otherwise the session cookie.
  Neither → 401 as today.
- Record how the request authenticated on `request.state.auth_via`
  (`"bearer"` / `"cookie"`). Tasks 09 and 10 need it.
- Cookie auth on `POST` / `PUT` / `PATCH` / `DELETE`: `X-CSRF-Token` must match
  `csrf_token(cookie_jwt, secrets.auth_token)`, else 403 `forbidden`.
- Token checks (signature, expiry, live user, `token_version`) are unchanged.

## Tests

Using `/_test/user`-style routes as in `test_auth.py`, with a GET and a POST:

- cookie GET works; cookie POST without, or with a wrong, CSRF header is 403
- cookie POST with the right header works
- bearer POST needs no CSRF header
- header wins when both are present (bad header + good cookie → rejected)
- device credentials still never work as a user credential

## Review focus

The bearer path is byte-for-byte the old behavior.
