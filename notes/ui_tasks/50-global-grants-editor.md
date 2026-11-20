# 50 — Permissions section: global grants

Step 7 (Permissions) · Depends on: 49, 43 · Size: M

## Goal

Edit a user's global grants on the user detail page.

## Changes

- Regenerate the API types. Hooks: `usePermissionCatalog` (key
  `['permissions']`), `useUserPermissions(id)` (key `['users', id,
  'permissions']`), `useReplaceUserPermissions`. Success invalidates the user's
  permissions and `['me']`.
- `src/locales/en/permissions.json`: label and description per permission id.
- A checkbox per global-capable permission (scope `global` or `both`).
- Save and Reset buttons, enabled only when something changed.
- Owner → "All permissions", read-only. Yourself → read-only, with a note.
- The form state holds the whole set (global and devices), so task 51 adds
  device rows to the same Save.

## Tests

Toggling and saving sends the full set; Reset restores; owner and self are
read-only; a server field error shows a notification.
