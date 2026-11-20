# 35 — `POST /api/invites/check`

Step 6 (Users and invites) · Depends on: 33, 08 · Size: S

## Goal

The public invite page can confirm a code is valid and greet the person by
name.

## Changes

- Repo `invites.find_valid(conn, code_hash, now) -> InviteMatch | None`
  (`invite_id, user_id, display_name, created_by`). The invite must be unused,
  not revoked and not expired, and the user live and not disabled.
- Route (no auth, `require_json_same_origin`): body `{code}`, at most 128
  characters. Valid → `{display_name}`. Every other case → one generic 404
  `not_found` on `code`.

## Tests

Valid; expired; used; revoked; unknown; oversized; user deleted or disabled —
all failures give an identical response.

## Review focus

No rate limit. The codes are 256-bit random values, so guessing isn't
practical.
