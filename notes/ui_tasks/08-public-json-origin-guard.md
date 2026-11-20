# 08 — Guard for unauthenticated JSON posts

Step 3 (Browser session) · Depends on: 04 · Size: S

## Goal

Login and invite redemption have no session to bind CSRF to. Protect them with
a dependency that rejects requests a cross-site form could send.

## Changes

New dependency `require_json_same_origin` in `app/auth/session.py` (or
`deps.py`):

- `Content-Type` must be `application/json` (parameters allowed), else 422
  `invalid_request`.
- If `Origin` is present, its host and port must match the request's `Host`
  (or `X-Forwarded-Host` when `auth.trust_forwarded_header` is on), else 403
  `forbidden`. No `Origin` passes, so scripts and curl keep working.
- Apply it to `POST /api/auth/token` now. Tasks 09, 35 and 37 apply it to their
  routes.

## Tests

Form-encoded body rejected; matching Origin passes; foreign Origin 403; no
Origin passes; forwarded host honored only with trust on.

## Review focus

Whether the `Origin` comparison should include the scheme. The plan compares
host and port only, because behind a TLS proxy without trust the app sees
`http`.
