# 42 — Users list screen

Step 6 (Users and invites) · Depends on: 38, 39, 41, 19 · Size: S

## Goal

`/users`: everyone, with their status at a glance, and a way to add one.

## Changes

- `RequirePermission("users.manage")`.
- Columns through `ResponsiveList`: name (primary, with an owner badge), login
  (username or provider label), status badge (active, pending, disabled),
  locked icon, last login (`Timestamp`).
- "Add user" opens a modal form: display name (1–64), email (optional, one
  `@`). On success it navigates to `/users/:id`.
- New namespace `src/locales/en/users.json`.

## Tests

Rows render with the right badges; create flow navigates; a server `field` error
lands on the form; the page is hidden without the permission.
