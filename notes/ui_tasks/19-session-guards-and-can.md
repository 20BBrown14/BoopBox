# 19 — Session, route guards and `can()`

Step 4 (Scaffold) · Depends on: 16, 18 · Size: M

## Goal

The UI knows who is logged in, sends people to the right place, and hides what
they can't use.

## Changes

- `useMe()` on `GET /api/me`, key `['me']`.
- `RequireAuth` around the layout routes: loading state; unauthenticated →
  `/login?next=`; `must_change_password` → `/change-password`, and nothing else
  is reachable. A 403 from `/api/me` counts as logged out, because the server
  answers a rejected session (disabled user, bumped token version) with 403.
  Other failures show a retry button.
- `useCan()` → `can(permission, deviceId?)`, mirroring the server: owner →
  true, then a global grant, then a device grant.
- `RequirePermission` page wrapper renders `NoPermission`.
- Nav items carry a required permission (Users → `users.manage`, Server
  settings → `server_settings.manage`) and are hidden without it.

## Tests

Guard redirects (logged out, must-change); nav hiding per permission set; `can()`
truth table including owner and device-scoped grants.

## Review focus

`can()` stays a UI hint. Every route still relies on the server's check.
