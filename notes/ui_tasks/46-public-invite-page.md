# 46 — Public invite page

Step 6 (Users and invites) · Depends on: 41, 20 · Size: M

## Goal

`/invite#code=…`: the invited person sets up a login.

## Changes

- Outside `RequireAuth`.
- On mount: read `code` from `location.hash`, keep it in component state, and
  remove the fragment with `history.replaceState`, so it isn't left in history
  or bookmarks.
- `POST /api/invites/check`: valid → "Welcome, {name}"; invalid → a translated
  "invalid or expired" message.
- Form: username (3–32, `a-z 0-9 . _ -`, lowercased as typed), password
  (12–128), confirm.
- `POST /api/invites/redeem`; a 409 shows on the username field.
- Success: invalidate `['me']`, navigate to `/`.
- If someone is already logged in, a note says redeeming will switch accounts.
- New namespace `src/locales/en/invite.json`.

## Tests

The fragment is read and then stripped; invalid code message; field
validation; taken username; successful redeem navigates.
