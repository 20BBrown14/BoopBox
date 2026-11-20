# 09 — `POST /api/auth/login` and `/api/auth/logout`

Step 3 (Browser session) · Depends on: 07, 08 · Size: S

## Goal

Browser login that sets the session and CSRF cookies, and logout that clears
them.

## Changes

- Extract the shared part of `/api/auth/token` (client address, `login_local`,
  generic 401) into a helper used by both login routes.
- `POST /api/auth/login` `{username, password}` → 200
  `{must_change_password}`, plus cookies via `set_session`. `Max-Age` comes from
  `auth.token_lifetime_hours`; `Secure` from `request_is_https`. Guarded by
  `require_json_same_origin`. No token in the body.
- `POST /api/auth/logout` (`require_user_allow_password_change`) → 204 and
  `clear_session`. With bearer auth it is a 204 no-op.

## Tests

- Login sets both cookies with the right flags; `Secure` over an `https`
  base URL and with a trusted `X-Forwarded-Proto: https`.
- Failed login: same generic body as `/api/auth/token`, no cookies, history row
  written.
- Logout with cookie needs the CSRF header and clears both cookies.

## Review focus

Login failure behavior is identical to `/api/auth/token`.
