# 63 — README: web UI and development workflow

Step 10 (Docs) · Depends on: 62 · Size: S

## Goal

Someone new can run, develop and deploy the UI from the README.

## Changes

- New "Web UI" section: what it covers; served by the server at `/`;
  `BOOPBOX_WEB_DIR`; API-only mode when it's unset.
- Development: Node version (`.nvmrc`), `npm ci`, running uvicorn and
  `npm run dev` together, the `/api` proxy, `npm run gen:api` after server
  changes.
- First run: the owner from `BOOPBOX_DEFAULT_*`, forced password change,
  inviting users, setting `public_base_url` so invite links work.
- "Run tests" and "Lint and format": add `npm run check`.
- Every human API path under `/api`.
- Stale sections still describing the old `config.yaml` / seed-device setup:
  - "Configuration reference" intro and "`config.yaml` schema"
  - "Media sources → Jellyfin" (`config.yaml` format, `BOOPBOX_SOURCE_<ID>_API_KEY`)
  - "Testing OTA end to end" steps 1 and 3, and the "Provisioning" paragraph
    (seed device env vars; devices are now added in the UI)
  - the mosquitto example comment naming `BOOPBOX_SEED_DEVICE_ID`

## Tests

None (docs only).
