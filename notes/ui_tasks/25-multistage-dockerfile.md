# 25 — Multi-stage Dockerfile

Step 5 (Serving) · Depends on: 12, 23 · Size: S

## Goal

One image that contains the built UI but no Node.

## Changes

- `server/Dockerfile`: a `node:26-slim` stage copies `web/package*.json`,
  runs `npm ci`, copies `web/` and runs `npm run build`. The Python stage copies
  `/web/dist` to `/app/web-dist` and sets `BOOPBOX_WEB_DIR=/app/web-dist`.
- `server/.dockerignore`: add `web/node_modules/` and `web/dist/`. The existing
  `dist/` entry only matches at the context root.
- The healthcheck and command are unchanged.

## Tests

Manual: `docker compose build` succeeds and `GET /` returns the UI. Not run
automatically.

## Review focus

Layer order, so dependency installs are cached across source changes.
