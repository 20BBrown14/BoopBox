# 06 — Session cookie and CSRF helpers

Step 3 (Browser session) · Depends on: 04 · Size: S

## Goal

Pure helpers for the browser session, with no routes yet.

## Changes

New `app/auth/session.py`:

- Constants: `SESSION_COOKIE = "boopbox_session"`, `CSRF_COOKIE =
  "boopbox_csrf"`, `CSRF_HEADER = "x-csrf-token"`.
- `request_is_https(request, trust_forwarded) -> bool`: `request.url.scheme`,
  or the rightmost `X-Forwarded-Proto` value when trust is on (same rule as
  `client_address` in `app/auth/login.py`).
- `csrf_token(jwt, secret) -> str`: base64url `HMAC-SHA256(secret, "csrf:" +
  jwt)`.
- `csrf_matches(jwt, secret, presented) -> bool`: constant-time.
- `set_session(response, jwt, *, max_age, secure)`: session cookie httpOnly,
  `SameSite=Strict`, `Path=/api`; CSRF cookie readable, `SameSite=Strict`,
  `Path=/`.
- `clear_session(response, *, secure)`.

## Tests

Unit tests: cookie attributes, `Secure` toggling, forwarded-proto trust on/off,
CSRF determinism and mismatch.

## Review focus

Cookie attributes against ui_design.md "Session cookie" and "CSRF".
