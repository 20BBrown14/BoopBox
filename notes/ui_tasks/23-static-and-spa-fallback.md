# 23 — Serve the built UI with an SPA fallback

Step 5 (Serving) · Depends on: 05 · Size: M

## Goal

FastAPI serves `web/dist` when it's configured, and never shadows an API or box
route.

## Changes

- `Environment.web_dir: str = ""` in `app/config.py` (`BOOPBOX_WEB_DIR`). It is
  reserved automatically through `RESERVED_ENV_NAMES`.
- `app/routes/web.py`: `mount_web(app, web_dir)`, called last in `create_app()`.
  - Unset or missing directory: log once that the UI isn't served, and add
    nothing.
  - `/assets/*`: files with `Cache-Control: public, max-age=31536000, immutable`.
  - Catch-all `GET` / `HEAD`: reserved prefixes (`/api`, `/stream`, `/ota`,
    `/firmware`, `/health`, `/docs`, `/redoc`, `/openapi.json`) → JSON 404
    `not_found`. An existing top-level file in `dist` (`color-scheme.js`,
    favicon and the like) is served with
    `Cache-Control: no-cache`, since those names carry no content hash.
    Anything else → `index.html` with `Cache-Control: no-cache`.
  - Paths are resolved inside `web_dir` only; `..` can't escape it.

## Tests

With a temporary dist directory: deep UI path → index; asset cache header;
every reserved prefix → JSON 404; traversal attempt → 404; unset dir → `/` 404
and the API still works.

## Review focus

Route order, and the reserved list matching ui_design.md.
