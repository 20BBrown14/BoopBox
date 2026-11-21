# 41 — Users query hooks and MSW handlers

Step 6 (Users and invites) · Depends on: 18, 37 (types) · Size: S

## Goal

The data layer for the users screens.

## Changes

- Regenerate the API types (`npm run gen:api`).
- `src/features/users/api.ts`: `useUsers`, `useUser(id)`, `useCreateUser`,
  `useUpdateUser`, `useDeleteUser`, `useIssueInvite`, `useRevokeInvites`,
  `useUnlockUser`, `useLogOutUserEverywhere`.
- Keys `['users', 'list', {limit, offset}]` and `['users', id]`. Mutations
  invalidate `['users']`, which covers every page and every detail.
- `useUsers({limit, offset})` returns the `UserPage` from `GET /api/users`
  (`items`, `total`, `limit`, `offset`); see task 28.
- `useIssueInvite` follows the secret rule from task 40.
- `src/test/handlers/users.ts`: MSW handlers typed against `schema.d.ts`, with an
  in-memory fixture store.

## Tests

Invalidation after each mutation; the invite result isn't cached.
