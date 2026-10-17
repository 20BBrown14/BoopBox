# P1 — Project scaffolding & app skeleton

Implementation task list for piece **P1** from `../task_list.md`.

Delivers a runnable, empty-but-wired Python project: a FastAPI app factory on a
single asyncio loop with a lifespan hook (reserved for the later MQTT loop), a
`GET /health` endpoint, a Uvicorn entrypoint, a Dockerfile + Compose app service,
linter/formatter config, and a seeded README (project intro, Development Guide,
config-reference scaffold).

## Contract this piece must expose

Downstream pieces (P2, P3, P8, P10) depend on these existing and not moving:

- **App factory** — `create_app() -> FastAPI` in `app/main.py`. Builds and returns
  the app; wires the lifespan hook. P2/P3/P6/P8 register routers and attach state
  here.
- **Lifespan hook** — an `async` lifespan context manager wired into the app at
  creation. Empty startup/shutdown bodies for now; P7 owns the MQTT loop here, P2
  the DB init, P8 the manifest build.
- **Settings entrypoint location** — `app/config.py` holds a `Settings` object and
  a `get_settings()` accessor. P1 ships a minimal placeholder (nothing loaded from
  `config.yaml`/`.env` yet); P2 fills it in. Fixing the location now means P2 is
  additive.
- **Uvicorn entrypoint** — `app.main:create_app` as an ASGI factory, invoked by the
  container CMD and the documented local run command.

Keep these names/paths stable; later pieces import against them.

## Target layout after P1

```
BoopBox/
  server/
    pyproject.toml
    Dockerfile
    docker-compose.yml
    .dockerignore
    app/
      __init__.py
      main.py            # create_app(), lifespan, GET /health
      config.py          # Settings placeholder + get_settings()
    tests/
      __init__.py
      test_health.py
  README.md              # updated: intro + Development Guide + config scaffold
  .gitignore             # updated with Python/venv/build ignores
```

The Python project lives under `server/`: the repo already holds `firmware/` and
`notes/` siblings, so the Python project gets its own root rather than scattering
its `pyproject.toml`, Dockerfile, and venv across the repo top level. Target
Python is **3.12**.

## Tasks

### 1. `pyproject.toml` with pinned deps
- [ ] Create `server/pyproject.toml` using a PEP 621 `[project]` table.
- [ ] Set `requires-python = ">=3.12"`.
- [ ] Pin runtime deps to exact versions (`==`), latest confirmed at authoring:
  - `fastapi==0.143.3`
  - `uvicorn[standard]==0.54.0`
  - `aiomqtt==2.5.1`
  - `aiosqlite==0.22.1`
  - `pydantic==2.14.1`
  - `pydantic-settings==2.16.0`  _(settings loader used by P2; include now so the
    `config.py` placeholder can import it)_
  - `httpx==0.28.1`
- [ ] Pin dev deps under an optional-dependency group (e.g. `[project.optional-dependencies] dev`):
  - `pytest==9.1.1`
  - `pytest-asyncio==1.4.0`
  - `ruff==0.17.1`  _(linter + formatter; one tool for both)_
- [ ] Add a `[project.scripts]` or document the module entrypoint
      (`app.main:create_app`).
- [ ] Choose a build backend (e.g. `hatchling`) and declare `[build-system]`, OR
      keep it dependency-only if not packaging. Pick one and be consistent with the
      Dockerfile install step.
- [ ] Re-verify each pinned version is current at implementation time; bump if PyPI
      has moved and nothing breaks.

### 2. Linter / formatter config
- [ ] Add `[tool.ruff]` to `pyproject.toml`: `line-length`, target version, and the
      lint rule selection. Ruff handles both lint and format, so no separate black
      config.
- [ ] Add `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` (so async tests
      need no per-test marker) and `testpaths = ["tests"]`.

### 3. App factory + lifespan + `GET /health`
- [ ] `app/__init__.py` (empty package marker).
- [ ] `app/config.py`: a minimal `Settings` (pydantic-settings `BaseSettings`) with
      no fields required yet, plus `get_settings()` (cache with
      `functools.lru_cache`). This is the placeholder P2 extends.
- [ ] `app/main.py`:
  - [ ] An `async` lifespan context manager (via
        `contextlib.asynccontextmanager`) with empty startup and shutdown sections,
        each with a brief comment noting which later piece populates it.
  - [ ] `create_app() -> FastAPI` that constructs `FastAPI(lifespan=...)` and
        registers routes.
  - [ ] `GET /health` returning HTTP 200 with a small JSON body
        (e.g. `{"status": "ok"}`).
- [ ] Ensure the app runs on a single asyncio loop (default Uvicorn behavior; no
      extra worker processes configured).

### 4. Uvicorn entrypoint
- [ ] Verify `uvicorn app.main:create_app --factory` boots locally from the
      `server/` dir.
- [ ] Pick the bind host/port for the container (`0.0.0.0:8000`) and document it;
      note that `0.0.0.0` is for the container, local bare runs can use the Uvicorn
      default.

### 5. Dockerfile
- [ ] `server/Dockerfile`: a slim Python base matching the chosen version
      (e.g. `python:3.12-slim`).
- [ ] Install deps from `pyproject.toml` (copy the project, `pip install .` or the
      chosen backend's install).
- [ ] Set the CMD to run Uvicorn with the factory entrypoint binding `0.0.0.0:8000`.
- [ ] `server/.dockerignore` excluding `.venv`, `__pycache__`, `tests/`, caches,
      and the SQLite db file.

### 6. docker-compose.yml (app service only)
- [ ] `server/docker-compose.yml` with a single `app` service building the local
      Dockerfile.
- [ ] Map container `8000` to a host port.
- [ ] No broker, no volumes beyond what the app needs yet (P10 adds the broker
      profile; P2 may add a db volume). Leave a brief structural placeholder only if
      it doesn't run anything.

### 7. `.gitignore` additions
- [ ] Append Python ignores to the existing root `.gitignore` (currently only
      `.kiro`): `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`,
      `.ruff_cache/`, build/dist artifacts, `*.db`/`*.db-wal`/`*.db-shm` (SQLite
      WAL sidecars, for P2), and `.env` (secrets never committed).

### 8. Tests
- [ ] `tests/__init__.py`.
- [ ] `tests/test_health.py`: use FastAPI's `TestClient` (or httpx `ASGITransport`)
      to assert `GET /health` returns 200 and the expected JSON. This exercises the
      app factory and lifespan startup/shutdown.

### 9. README updates (same piece per the documentation rule)
Docs describe what exists and how to operate it — no rationale, no
design-history. Rationale stays in `notes/`.
- [ ] **Project intro** — expand the one-liner into a short operational intro of
      what the server does (bridges the fleet to media sources; MQTT client + HTTP
      audio proxy).
- [ ] **Development Guide** section with every command spelled out and verified:
  - [ ] Prerequisites (Python version, Docker/Compose, how to get `uv`/`pip`).
  - [ ] Install deps (create venv, install project + dev extras).
  - [ ] Run locally bare (the Uvicorn factory command, from `server/`).
  - [ ] Run via `docker compose up` (from `server/`).
  - [ ] Run tests (`pytest`).
  - [ ] Run lint + format (`ruff check`, `ruff format`).
- [ ] **Config reference scaffold** — a section documenting only what exists so
      far. P1 introduces no `config.yaml` keys or `.env` vars yet, so state that
      explicitly and note the split convention (structured `config.yaml` vs secret
      `.env`) and which is which, so P2 slots entries in. Use placeholders, never
      real secrets.

## Verification / demo (piece acceptance)

- [ ] `GET /health` returns 200 — confirmed by the test and a manual curl.
- [ ] The app boots under Uvicorn inside the container: `docker compose up` serves
      `/health` on the mapped host port.
- [ ] Every command in the Development Guide runs clean, top to bottom, on a fresh
      checkout: install → run bare → run via compose → tests pass → `ruff check`
      clean → `ruff format --check` clean.
- [ ] A new contributor can follow the Development Guide to a running server with
      no steps missing.

## Notes / watch-outs

- Nothing from `config.yaml`/`.env` is loaded in P1 — `config.py` is a placeholder
  whose only job is to fix the import location for P2. Don't add fields P2 owns.
- The lifespan hook must exist and be wired even though it does nothing yet; P7
  attaches the MQTT loop to it and P2 the DB init. Getting it in place now avoids a
  later refactor of `create_app`.
- Keep the app single-loop: no Uvicorn `--workers`, no process pool. The whole
  design assumes one asyncio loop shared by HTTP and (later) MQTT.
- Placement (`server/`) and Python version (3.12) are fixed decisions; they ripple
  through every path and the Dockerfile base image, so hold them steady across the
  piece.
