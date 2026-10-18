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

Uvicorn binds to its default (`127.0.0.1:9685`) for local bare runs. Check the
health endpoint:

```bash
curl http://127.0.0.1:9685/health
```

### Run via Docker Compose

```bash
cd server
docker compose up --build
```

The container binds `0.0.0.0:9685` and Compose maps it to host port `9685`:

```bash
curl http://127.0.0.1:9685/health
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

- `config.yaml` — structured, human-edited configuration. No secrets. Committed.
  A sample lives at [`server/config.yaml`](server/config.yaml).
- `.env` — secrets and deploy-specific values. Gitignored, never committed. Copy
  [`server/.env.example`](server/.env.example) to `server/.env` and fill it in.

### `config.yaml` schema

```yaml
sources:                       # array of media sources
  - id: jellyfin-main          # unique source id, referenced by mappings and API-key env var
    type: jellyfin             # source backend type
    base_url: http://jellyfin:8096
    user_id: ""                # optional

mappings:                      # slug -> list of entries; server picks one to play
  "boop/example":
    - source: jellyfin-main    # must reference a sources[].id
      item: "REPLACE_WITH_SOURCE_ITEM_ID"   # opaque source-internal id
      kind: item               # item | collection; default item
  "boop/soundtracks":
    - source: jellyfin-main
      item: "REPLACE_WITH_COLLECTION_ID"    # a collection/album id
      kind: collection         # a collection expands to its member items
    - source: jellyfin-main
      item: "REPLACE_WITH_SOURCE_ITEM_ID"
      kind: item

streaming:
  mode: proxy                  # proxy | redirect; default proxy. redirect is not yet functional
  pause_budget_seconds: 1800   # default 1800

ota:
  manifest_version: "0.1.0"    # default "0.1.0"
```

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `sources[].id` | string | — | Unique id; referenced by mappings and the API-key env var. |
| `sources[].type` | string | — | Source backend type (e.g. `jellyfin`). |
| `sources[].base_url` | string | — | Source base URL. |
| `sources[].user_id` | string | `null` | Optional. |
| `mappings.<slug>` | list | — | A list of entries; the server picks one to play. |
| `mappings.<slug>[].source` | string | — | Must reference a `sources[].id`; an unknown id is rejected at startup. |
| `mappings.<slug>[].item` | string | — | Opaque source-internal id. An item for `kind: item`, a collection/album for `kind: collection`. |
| `mappings.<slug>[].kind` | `item` \| `collection` | `item` | `collection` points at a set (e.g. a Jellyfin collection, a Spotify album later) that expands to its member items; the server picks one item at random to play. |
| `streaming.mode` | `proxy` \| `redirect` | `proxy` | `redirect` is accepted but not yet functional. |
| `streaming.pause_budget_seconds` | int | `1800` | Added to item duration for stream-token expiry. |
| `ota.manifest_version` | string | `0.1.0` | Drives the hosted OTA manifest. |

The config file path defaults to `config.yaml` relative to the working directory;
override with `BOOPBOX_CONFIG_PATH`.

### `.env` reference

All variables use the `BOOPBOX_` prefix. Values tagged **(secret)** must never be
committed — keep them in `.env`, not `config.yaml`.

| Variable | Default | Notes |
|----------|---------|-------|
| `BOOPBOX_STREAM_SECRET` | — (required) | **(secret)** HMAC signing secret for stream tokens. |
| `BOOPBOX_CONFIG_PATH` | `config.yaml` | Path to `config.yaml`. |
| `BOOPBOX_DB_PATH` | `devices.db` | SQLite file path. |
| `BOOPBOX_MQTT_HOST` | `localhost` | |
| `BOOPBOX_MQTT_PORT` | `1883` | |
| `BOOPBOX_MQTT_USERNAME` | empty | |
| `BOOPBOX_MQTT_PASSWORD` | empty | **(secret)** |
| `BOOPBOX_MQTT_TLS` | `false` | |
| `BOOPBOX_MQTT_TLS_CA` | empty | Path to a CA bundle when TLS is on. |
| `BOOPBOX_PUBLIC_BASE_URL` | `http://127.0.0.1:9685` | URL boxes use to reach the server. |
| `BOOPBOX_SOURCE_<ID>_API_KEY` | empty | **(secret)** API key per source. `<ID>` is the source id uppercased with non-alphanumeric runs replaced by `_` (e.g. `jellyfin-main` → `BOOPBOX_SOURCE_JELLYFIN_MAIN_API_KEY`). |
| `BOOPBOX_SEED_DEVICE_ID` | `boop-test` | MVP seed device, upserted at startup. |
| `BOOPBOX_SEED_DEVICE_MQTT_PASSWORD` | empty | **(secret)** Provisioned at the broker; never stored in the database. |

#### Generating `BOOPBOX_STREAM_SECRET`

Use a 32-byte (256-bit) random value, the right size for the HMAC-SHA256 signing
key. Generate one with either:

```bash
openssl rand -base64 32
```

```bash
head -c 32 /dev/urandom | base64
```

Paste the output into `BOOPBOX_STREAM_SECRET` in `.env`. Rotating the secret
invalidates all outstanding stream tokens.

### Database

Device metadata is stored in a SQLite database at `BOOPBOX_DB_PATH` (default
`devices.db`), created at startup. Keep this file on a **local** filesystem:
SQLite WAL mode relies on local file locking and can corrupt or misbehave on a
networked filesystem (NFS, SMB).
