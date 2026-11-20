# 43 — User detail page: layout and profile

Step 6 (Users and invites) · Depends on: 42 · Size: S

## Goal

`/users/:id` with its section layout, and the editable profile section.

## Changes

- Header: name, owner badge, status badge.
- Sections in order: Profile, Login & invite (task 44), Permissions (task 50),
  Danger zone (task 45). Empty sections are placeholders until their task lands.
- Profile form: display name and email, with dirty tracking; Save sends only the
  changed fields.
- An unknown id renders NotFound.

## Tests

Save sends only changed fields; clearing email sends `null`; a 404 renders
NotFound.
