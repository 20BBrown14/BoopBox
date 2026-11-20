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
- `openapi-typescript` → `web/src/api/schema.d.ts`. It declares TypeScript 5 as
  a peer, so `package.json` has an `overrides` entry pointing it at ours.
- `web/tools/genApi.ts` runs the dump and `openapi-typescript`. `gen:api` writes
  `src/api`; `check:api` (`--check`) generates into a temp directory and fails
  when any of the three files differs from the committed one. No git involved,
  because `git diff` compares against the staging area. `check` includes
  `check:api`.
- The script runs with the server's virtualenv Python (`BOOPBOX_PYTHON`
  overrides the default `server/.venv`); document the command in the script's
  docstring.
- The generated files are excluded from Prettier and ESLint.

## Tests

pytest: the dump is deterministic across two runs and contains `/api/me`.

## Review focus

`create_app()` used to create the firmware directory as a side effect, which
would leave a stray `firmware-bins/` behind after a dump. The `mkdir` is now in
the lifespan in `main.py`.
