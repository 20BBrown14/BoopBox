# 22 — Account screen

Step 4 (Scaffold) · Depends on: 21 · Size: S

## Goal

`/account`: your own login, sessions and preferences.

## Changes

- Shows display name and login (local username, or the provider label).
- Link to change password.
- Log out: `POST /api/auth/logout`, clear the query cache, go to `/login`.
- Log out everywhere: confirm, then `POST /api/auth/logout-all`; this session
  stays logged in.
- Preferences: language select from `languages.ts`; color scheme
  light / dark / auto through `useMantineColorScheme` (Mantine persists it).

## Tests

Logout clears the cache and redirects; logout-everywhere confirms first;
changing language updates the text and `<html lang>`.
