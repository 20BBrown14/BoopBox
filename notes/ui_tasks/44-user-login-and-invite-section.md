# 44 — User detail: login and invite section

Step 6 (Users and invites) · Depends on: 43, 40 · Size: M

## Goal

Everything about how a user gets in.

## Changes

- Login method: local username, or "pending, no login yet".
- Lock state with an Unlock button.
- Open invite and its expiry (`Timestamp`), with a Revoke button.
- "Invite", or "Re-invite" for an active user. Hidden for the owner.
  - Opens `SecretReveal` with the link (primary) and the raw code.
  - Loopback warning when the link's host is `localhost`, in `127.0.0.0/8`, or
    `::1`. It links to `/server-settings`.
- "Log out everywhere" for this user, with a confirm step.

## Tests

The invite reveal shows the link; the loopback warning appears for a
`127.0.0.1` URL and not for a LAN address; the owner has no invite button;
unlock refreshes the user.
