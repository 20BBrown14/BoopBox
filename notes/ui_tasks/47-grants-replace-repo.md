# 47 — Replace a user's grants (repository)

Step 7 (Permissions) · Depends on: 11 · Size: S

## Goal

Write a whole grant set as one diff in one transaction.

## Changes

`permissions.replace_grants(conn, user_id, global_ids, devices, actor, now)`:

- Read the current rows with `list_grants` (task 11).
- Hard-delete rows not in the new set, in both tables.
- Insert new rows with `granted_at` and `granted_by`.
- Rows in both sets are left alone, so their original `granted_at` / `granted_by`
  survive.

No validation here; the route does it (task 49).

## Tests

Add, remove and keep in one call; kept rows keep their original stamps; global
and device tables are handled independently.
