# 45 — User detail: danger zone

Step 6 (Users and invites) · Depends on: 43, 40 · Size: S

## Goal

Disable, enable and delete, with the server's rules mirrored.

## Changes

- Disable / enable switch, with a confirm step when disabling.
- Delete through `confirmDanger`, naming the user. On success it navigates to
  `/users`.
- The whole section is hidden for the owner and for yourself, with a short note
  explaining why.

## Tests

Hidden for the owner and for self; delete confirms first and navigates; disable
updates the status badge.
