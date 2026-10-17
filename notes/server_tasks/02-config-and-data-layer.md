# P2 — Config + data layer

Implementation task list for piece **P2** from `../task_list.md`. Depends on P1
(scaffolding), which is in place under `server/`.

Delivers typed config loading (`config.yaml` + `.env`) with documented defaults,
a SQLite `devices` store created at startup with the WAL pragma set, a
seed-device upsert, and a slug→(source, item) resolver. All DB access runs off
the event loop.

## Builds on P1 (real, existing scaffolding)

- `app/config.py` — holds `Settings(BaseSettings)` (currently a placeholder with
  `env_prefix="BOOPBOX_"`, `extra="ignore"`) and `get_settings()` (lru_cached).
  **P2 fills this in.** Keep the name `Settings` and the `get_settings()`
  accessor; downstream pieces import them.
- `app/main.py` — `create_app()` and the `lifespan` context manager. The startup
  section already carries a comment reserving it for "P2 initializes the DB". **P2
  wires DB init + seed upsert into that startup block**, and closes the DB in
  shutdown.
- `pyproject.toml` — `aiosqlite==0.22.1` and `pydantic-settings==2.16.0` are
  already pinned. P2 needs a YAML parser (see task 1).
- `README.md` — the "Configuration reference" section exists and says no keys are
  defined yet. **P2 replaces that placeholder with the real `config.yaml` schema
  and `.env` reference.**

Placement (`server/`) and Python 3.12 are fixed.

## Contract this piece must expose

- **`Settings`** — the typed, validated settings object in `app/config.py`,
  loading `config.yaml` (structured) + `.env`/environment (secrets). Reached via
  the existing `get_settings()`.
- **Device repository** — get / upsert / update-last_seen+firmware, in a new
  module (e.g. `app/db.py` or `app/devices.py`). Async surface; every call runs
  off the event loop.
- **Resolver function** — `resolve(slug) -> (source, item) | None` over the
  `config.yaml` mapping. Returns `None` when the slug is absent.

P3 defines the `unknown_tag` error code; P2 ships before P3 in the dependency
graph, so the resolver represents a miss with a local sentinel (return `None`) and
P7 maps it to the P3 vocabulary. The resolver never imports P3.

## Target layout after P2

```
server/
  app/
    config.py        # Settings filled in: config.yaml + .env, typed, defaults
    db.py            # connection factory, schema init, pragmas, device repo
    resolver.py      # slug -> (source, item) over the config mapping
    main.py          # lifespan: DB init + seed upsert on startup; close on shutdown
  config.yaml        # committed structured config with sample mappings; no secrets
  .env.example       # documented env template with placeholders (committed)
  tests/
    test_config.py
    test_db.py
    test_resolver.py
```

`config.yaml` is committed with sample mappings (human-edited, no-secrets data).
`.env` stays gitignored (P1 already ignores it) with a committed `.env.example`.

## Tasks

### 1. YAML dependency & committed samples
- [ ] Add a YAML parser to `pyproject.toml` runtime deps, pinned (`pyyaml`). Pick
      the current version at implementation time and pin with `==`.
- [ ] Commit `config.yaml` with sample mappings (no secrets).
- [ ] Add a committed `.env.example` with placeholders (`.env` stays gitignored
      from P1).

### 2. `Settings` — config.yaml + .env loading
Fill in `app/config.py`'s `Settings` to load and validate both sources with typed
models and documented defaults.

- [ ] **`.env` / environment fields** (secrets + deploy-specific), all under the
      existing `BOOPBOX_` prefix:
  - [ ] `stream_secret` (`BOOPBOX_STREAM_SECRET`) — required, no default. The HMAC
        signing secret (consumed by P4).
  - [ ] MQTT connection: `mqtt_host` (default `localhost`), `mqtt_port` (default
        `1883`), `mqtt_username` (default empty), `mqtt_password` (default empty),
        `mqtt_tls` (default `false`), `mqtt_tls_ca` (default empty). Consumed by
        P7/P10.
  - [ ] `public_base_url` (`BOOPBOX_PUBLIC_BASE_URL`) — default
        `http://127.0.0.1:8000`. Consumed by P7 to build stream URLs.
  - [ ] Per-source API keys, keyed by source id:
        `BOOPBOX_SOURCE_<ID>_API_KEY` (sketch convention; the design flags this as
        an open question, so centralize the name derivation in one helper so a
        later change is one edit). Consumed by P9.
  - [ ] Seed device: `BOOPBOX_SEED_DEVICE_ID` (default `boop-test`),
        `BOOPBOX_SEED_DEVICE_MQTT_PASSWORD` (default empty). MVP-only.
- [ ] **`config.yaml` fields** (structured, no secrets), loaded and validated into
      typed pydantic models:
  - [ ] `sources` — array of source entries: `id`, `type`, `base_url`, optional
        `user_id`. (API key is injected from `.env` by id, not stored here.)
  - [ ] `mappings` — `slug -> { source, item }`. `source` references a `sources[].id`.
  - [ ] `streaming.mode` — `proxy | redirect`, default `proxy` (redirect is later;
        validate the enum but only `proxy` need function).
  - [ ] `streaming.pause_budget_seconds` — default `1800`. Consumed by P4's TTL.
  - [ ] `ota.manifest_version` — string. Consumed by P8.
- [ ] Wire `config.yaml` into `Settings` loading: choose the config path (env var
      like `BOOPBOX_CONFIG_PATH` with a sensible default, or a fixed `server/`
      relative path) and parse+validate on construction. Keep `get_settings()`
      lru_cached as the single accessor.
- [ ] **Validation**: invalid config is rejected at load with a clear error
      (unknown source `type` left permissive for now, but malformed structure,
      wrong types, a mapping referencing an undefined source id, missing required
      `stream_secret` should fail fast). Decide and document whether a mapping
      pointing at an unknown source id is a hard error (recommended) or a warning.

### 3. SQLite connection + pragmas (off-loop)
- [ ] `app/db.py`: an async connection factory over `aiosqlite` (which runs each
      connection on its own thread — keeps blocking SQLite off the event loop).
- [ ] Set these pragmas on **every** connection at open:
  - [ ] `PRAGMA journal_mode = WAL;`
  - [ ] `PRAGMA synchronous = NORMAL;`
  - [ ] `PRAGMA foreign_keys = ON;`
  - [ ] `PRAGMA busy_timeout = 5000;`
- [ ] DB file path from config/env with a default under a local (non-network)
      volume. Document the networked-FS caveat (WAL needs local locking) in the
      README/config reference briefly as an operational note.
- [ ] Ensure no DB call runs directly on the event loop — aiosqlite's threaded
      connections satisfy this; if any raw `sqlite3` is used, wrap in
      `asyncio.to_thread`.

### 4. `devices` schema init at startup
- [ ] Create the `devices` table if absent, matching the design schema exactly:
      `id` (TEXT PK), `friendly_name`, `mqtt_account`, `revoked` (INTEGER NOT NULL
      DEFAULT 0), `last_seen_at`, `firmware_version`, `created_at` (NOT NULL),
      `updated_at` (NOT NULL). Timestamps ISO-8601 UTC.
- [ ] Run schema init in `main.py`'s `lifespan` startup (the reserved comment is
      already there). Idempotent — safe on every boot.

### 5. Device repository
- [ ] In `app/db.py` (or `app/devices.py`), async functions:
  - [ ] `get(device_id) -> device | None`.
  - [ ] `upsert(device)` — insert or update; sets/refreshes `updated_at`, sets
        `created_at` on insert only.
  - [ ] `update_last_seen(device_id, firmware_version=None)` — stamps
        `last_seen_at` (and `firmware_version` when provided). Consumed off-loop by
        P7 on boop/OTA traffic.
- [ ] All repo functions async + off-loop.

### 6. Seed-device upsert at startup
- [ ] In `lifespan` startup, after schema init: read `BOOPBOX_SEED_DEVICE_ID`
      (+ `mqtt_account`/password-as-broker-concern per design — the device row
      holds the non-secret `mqtt_account` pointer, never the password) and upsert
      the seed device if absent. Idempotent across restarts.
- [ ] Clarify in a comment: the MQTT password is a broker concern, not stored in
      `devices`; the seed env var exists for broker provisioning, not for a DB
      column.

### 7. Slug resolver
- [ ] `app/resolver.py`: `resolve(slug) -> (source, item) | miss` over the
      validated `config.yaml` mappings from `Settings`.
- [ ] On hit, return the source id + opaque item id. On miss, return `None` (the
      local sentinel) that P7 maps to `unknown_tag` (P3). The resolver does not
      import P3 (not built yet).
- [ ] Pure/deterministic over config; no DB, no I/O.

### 8. README — config reference (same piece per the documentation rule)
Replace the placeholder "Configuration reference" section with the real schema.
Describe what exists and how to operate it — no rationale.
- [ ] **`config.yaml` schema** — document every key from task 2 with types and
      defaults, mark `streaming.mode` redirect as not-yet-functional if shipped as
      enum-only. Show a placeholder example (no real item ids/secrets).
- [ ] **`.env` reference** — document every variable from task 2 with defaults,
      clearly marking which are **secrets** (`BOOPBOX_STREAM_SECRET`, source API
      keys, seed MQTT password) vs non-secret deploy values. Show
      `.env.example`-style placeholders, never real secrets.
- [ ] State which file is which (structured vs secret) per the documentation rule,
      and note the DB file location + the networked-FS/WAL caveat as an operational
      note.
- [ ] Reference the committed `config.yaml` sample and `.env.example` from this
      section.

### 9. Tests
- [ ] `test_config.py`:
  - [ ] parses with defaults (minimal env + minimal config) — defaults applied as
        documented.
  - [ ] overrides via env + config take effect.
  - [ ] invalid config rejected: malformed structure, wrong types, mapping to an
        undefined source id (per the task-2 decision), missing `stream_secret`.
- [ ] `test_db.py`:
  - [ ] schema created; the four pragmas are actually applied on a connection
        (query `PRAGMA journal_mode` etc.).
  - [ ] seed upsert is idempotent (two boots → one row, `created_at` stable,
        `updated_at` may refresh).
  - [ ] repo get/upsert/update_last_seen round-trip.
  - [ ] a DB call runs off the event loop (assert it doesn't block / uses a
        thread — e.g. via aiosqlite, or a timing/instrumentation check).
- [ ] `test_resolver.py`: hit returns correct source+item; miss returns `None`.

## Verification / demo (piece acceptance)

- [ ] Boot with a sample `config.yaml` + `.env`: app starts, `devices.db` is
      created, the seed device row is present.
- [ ] A resolver lookup returns source+item for a known slug and `None` for an
      unknown slug.
- [ ] Config parses with defaults and with overrides; an invalid config is
      rejected at startup with a clear error.
- [ ] Pragmas verified applied; seed upsert idempotent across a second boot; a DB
      call confirmed off-loop.
- [ ] README config reference documents the full schema with secret-vs-structured
      marking; every example uses placeholders.

## Notes / watch-outs

- **Off-loop is non-negotiable.** `busy_timeout = 5000` means a contended write can
  block its caller up to 5s; on the event loop that freezes HTTP proxying and the
  MQTT loop. aiosqlite's per-connection thread is the mechanism; don't call raw
  blocking `sqlite3` on the loop.
- **No secrets in `devices`.** The table is deliberately secret-free: `mqtt_account`
  is a non-secret pointer, the MQTT password lives in the broker, the stream has no
  stored credential. Don't add password/hash columns.
- **P3 isn't built yet.** The resolver and config layer must not import the P3 error
  vocabulary. The resolver returns `None` on a miss; P7 maps it to `unknown_tag`.
- **API-key env naming is an open question** in the design (`BOOPBOX_SOURCE_<ID>_API_KEY`).
  Centralize the name derivation in one helper so a convention change is a single
  edit.
- Keep `Settings` / `get_settings()` names stable — P4/P7/P8/P9 all read config
  through them.
