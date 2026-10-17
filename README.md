# BoopBox

An open source, open-design, media-source-agnostic tap-and-play media box.

The BoopBox server bridges the fleet of boxes to media sources. It acts as an
MQTT client of a Mosquitto broker for the control channel, and serves audio over
HTTP by proxying from media sources (Jellyfin first). A box reads an NFC tag,
publishes a boop over MQTT, and the server resolves the tag to media and returns
a signed stream URL the box plays. The server also hosts OTA firmware updates for
the fleet.

The Python server lives under [`server/`](server/).

## Development Guide

All commands run from the `server/` directory unless noted.

### Prerequisites

- Python 3.12
- Docker and Docker Compose (for the containerized run)
- A Python installer: either [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
  or `pip` (bundled with Python)

### Install dependencies

Create a virtual environment and install the project with its dev extras.

Using `uv`:

```bash
cd server
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'
```

Using `pip`:

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Run locally (bare)

```bash
cd server
uvicorn app.main:create_app --factory
```

Uvicorn binds to its default (`127.0.0.1:8000`) for local bare runs. Check the
health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

### Run via Docker Compose

```bash
cd server
docker compose up --build
```

The container binds `0.0.0.0:8000` and Compose maps it to host port `8000`:

```bash
curl http://127.0.0.1:8000/health
```

### Run tests

```bash
cd server
pytest
```

### Lint and format

```bash
cd server
ruff check
ruff format
```

Ruff handles both linting and formatting. Use `ruff format --check` to verify
formatting without writing changes.

## Configuration reference

Configuration is split by nature of the data:

- `config.yaml` — structured, human-edited configuration. No secrets.
- `.env` — secrets and deploy-specific values. Never committed.

No `config.yaml` keys or `.env` variables are defined yet. This section is
populated as later pieces introduce config. Config examples use placeholders,
never real secrets.
