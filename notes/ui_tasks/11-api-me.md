# 11 — `GET /api/me`

Step 3 (Browser session) · Depends on: 07 · Size: M

## Goal

One call that tells the UI who is logged in and what they may see.

## Changes

- Repo `permissions.list_grants(conn, user_id) -> Grants(global_ids: set[str],
  devices: dict[str, set[str]])`, excluding grants on deleted devices.
- Repo query for the caller's live identity: provider, local username
  (`subject` when local) and `label`.
- `GET /api/me` (`require_user_allow_password_change`) returns:
  `id, display_name, is_owner, must_change_password, login {provider, username,
  label}, permissions {global, devices}`.
- Owner: `global` is every catalog id and `devices` is empty, matching the
  implicit-owner rule in `can()`.
- Pydantic response model, so the OpenAPI schema describes it.

## Tests

- Works while `must_change_password` is set.
- Owner gets the full catalog.
- Global and per-device grants appear; a grant on a deleted device doesn't.
- No hashes or token internals in the response.

## Review focus

`list_grants` is reused by tasks 47 and 49, so check its shape.
