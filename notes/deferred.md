# BoopBox — Deferred Items

Things deliberately left out of a milestone, with where they were decided.
Remove an item when it ships.

## Web UI and management API

Left out of the admin-foundation milestone ([ui_design.md](ui_design.md)).

### Features

- **Media sources UI** (`sources.manage`): add, edit, enable/disable, delete,
  replace the credential.
- **Mappings UI** (`mappings.edit`): create and edit slug mappings, reorder
  entries, box scope, play order and type.
- **Jellyfin browse proxy** for picking items and collections in the mapping
  editor, without exposing source credentials.
- **Unmapped tags screen** ("unknown tag, set it up?") from `tags.last_slug`.
- **Entry health list**: entries with `status = 'missing'`, replace or re-check.
- **Boop history screen**, with filters and paging.
- **Authentication history screen**, with filters and paging.
- **Backups UI**: list, last success and failures, manual backup, and the
  reminder to save the encryption keys when backups are first enabled.
- **OTA management UI** (`ota.manage`): manifest version, firmware status per
  box, check-now.
- **Device commands** (`device.control`): check-now nudge per box, play from the
  UI.
- **Google and Jellyfin login**, including invite redemption with them.
- **Self-service profile**: change own display name without `users.manage`
  (also an open question in data_design.md).
- **Admin password reset.** Re-invite covers lost access for now.
- **Permission groups with a grant ceiling.** Group permissions into tiers and
  only let a user grant groups at or below their own highest one. Today
  `users.manage` can grant anything, including itself.
- **Device settings** (per-box configuration), as a separate kind from server
  settings.

### Server settings

- **Rotating generated secrets** (`secrets.stream`, `secrets.auth_token`) from
  the UI.
- **Keyring reload** from the UI, and the **re-encrypt job** with its per-`kid`
  progress.
- **Live MQTT reconnect** when `mqtt.*` settings change. Until then the UI says a
  restart is needed.

### Engineering

- **Playwright end-to-end tests** against a real server.
- **TanStack Router**, if the history and mapping screens make URL search
  params heavy enough to want typed routes.
- **Paging** on list endpoints. Needed for history screens; the
  admin-foundation lists are small enough to return whole.
- **Revoking a single token.** Revocation is per user (`token_version`).
- **Accessibility audit** beyond Mantine's defaults.
- **Light/dark flash on page load**, only if it turns out to be noticeable.
  Mantine's `ColorSchemeScript` is inline and blocked by the CSP. Fixes: load
  the same code from a small file in `web/public/` in the `<head>`, or allow the
  inline script by its SHA-256 hash in `script-src`.

### Translation

- **Languages beyond English.**
- **Translatable server validation messages**: the server returns a reason code
  and parameters instead of an English `message`.
- **Language preference stored on the user**, so it follows them across
  browsers. Needs a schema change.
- **Right-to-left layouts** (Mantine `DirectionProvider`).
