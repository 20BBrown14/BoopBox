# 17 — OpenAPI dump and type generation

Step 4 (Scaffold) · Depends on: 11, 12 · Size: S

## Goal

TypeScript types generated from the server's schema, and a check that they're
current.

## Changes

- `server/scripts/dump_openapi.py`: build `create_app()`, call `app.openapi()`
  (the lifespan doesn't run, so no database is opened) and write
  `web/src/api/openapi.json` with sorted keys. Also write
  `web/src/api/server-setting-keys.json`, the sorted `REGISTRY` keys (task 61
  uses it).
- `openapi-typescript` → `web/src/api/schema.d.ts`.
- npm scripts: `gen:api` (dump + generate), `check:api` (`gen:api`, then
  `git diff --exit-code` on the three files). `check` includes `check:api`.
- The script runs with the server's virtualenv Python; document the command in
  the script's docstring.

## Tests

pytest: the dump is deterministic across two runs and contains `/api/me`.

## Review focus

`create_app()` creates the firmware directory as a side effect
(`Path(...).mkdir` in `main.py`). The dump must not leave a stray
`firmware-bins/` behind. Point `BOOPBOX_FIRMWARE_DIR` at a temp directory, or
move that `mkdir` into the lifespan.
