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

This runs the app alone. The app is always just an MQTT **client**; it never
starts a broker. Point it at a broker with the `BOOPBOX_MQTT_*` settings, or
bring up the bundled broker with the profile below.

### MQTT broker: bundled vs external

The broker is a separate service. "Bundled vs external" is purely a Compose/env
choice — there is no app-side detection.

**Bundled broker** (local Mosquitto under the `bundled-broker` profile):

```bash
cd server
docker compose --profile bundled-broker up
```

This starts both the broker and the app. Before first run, provision the broker
accounts (see "Broker accounts & ACLs" below) and set these in `server/.env` so
the app reaches the bundled service:

```
BOOPBOX_MQTT_HOST=mosquitto
BOOPBOX_MQTT_PORT=1883
BOOPBOX_MQTT_USERNAME=boopbox-server
BOOPBOX_MQTT_PASSWORD=<server account password>
```

The app's reconnect loop tolerates a not-yet-up broker, so start ordering is a
nicety, not a requirement.

**External broker** (omit the profile):

```bash
cd server
docker compose up
```

No bundled broker starts. Point `BOOPBOX_MQTT_*` in `server/.env` at the admin's
broker and its credentials.

#### Ports: local vs TLS

- **1883** — local/plain, the bundled-broker default.
- **8883** — TLS/remote. TLS and cert provisioning are **deferred** and not wired
  in this repo. The app already supports `BOOPBOX_MQTT_TLS` + `BOOPBOX_MQTT_TLS_CA`
  for when an admin fronts the broker with TLS; fuller production/fleet deployment
  is out of scope here.

#### Broker config & ACL files

The bundled broker's config lives under `server/mosquitto/`:

- `mosquitto.conf` — listener on 1883, `allow_anonymous false`, and pointers to
  the password and ACL files. Authenticated usernames are required so the ACL
  pattern can key on `%u`.
- `aclfile` — the topic ACLs (see below). ACLs live entirely in the broker; the
  app enforces nothing.
- `password_file.example` — a documented sample. Generate the real
  `server/mosquitto/password_file` with `mosquitto_passwd` (it holds hashed
  secrets and is gitignored).

Compose mounts these read-only into the container at
`/mosquitto/config/{mosquitto.conf,aclfile,password_file}` and persists broker
data in `server/mosquitto-data/`.

#### Broker accounts & ACLs

Two kinds of account:

- **Server account** — one user with broad read/write across `boopbox/#`. It
  talks to every device and owns the broadcast publish. Its username must match
  `BOOPBOX_MQTT_USERNAME` (the sample uses `boopbox-server`).
- **Per-device box accounts** — one per box, whose **username is its device id**.
  Each box is confined to its own `boopbox/<id>/#` subtree: it may publish only
  its `boop`/`version`, read only its `play`/`error`/`cmd`, and may **read** the
  broadcast `boopbox/all/cmd` but never publish there. The per-device publish
  restriction is the security priority — without it a leaked box credential could
  inject commands to other devices or the `cmd`/`flash` channel.

Generate the password file (hashed; keep it out of git):

```bash
cd server
# Server account (must match BOOPBOX_MQTT_USERNAME)
mosquitto_passwd -c mosquitto/password_file boopbox-server
# Seed box account (username = BOOPBOX_SEED_DEVICE_ID, e.g. boop-test)
mosquitto_passwd mosquitto/password_file boop-test
# Each additional box, by device id
mosquitto_passwd mosquitto/password_file <device-id>
```

Replace the `boopbox-server` placeholder in `mosquitto/aclfile` if you use a
different server username. Use placeholders in committed files; never commit real
secrets.

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

## Testing audio

The firmware's web UI has an **Audio Test** section: a URL field, a volume slider and a
Play button. The box fetches the URL itself, so the file just has to be reachable over
the network. The easiest way is to serve `test-audio/` from your machine.

### 1. Start the file server

```sh
cd test-audio
python -m http.server 8000
```

Leave it running. Find your machine's LAN IP with `ip -4 addr` (Linux) or
`ipconfig getifaddr en0` (macOS).

If your machine has a firewall, it must let the box in on port 8000. For example, with
nftables (temporary, gone on reboot):

```sh
sudo nft insert rule inet filter input ip saddr <box-ip> tcp dport 8000 accept
```

### 2. Play it from the test page

1. Open the box's web UI at `http://<box-ip>/`. The box's IP is in your router's client
   list, or in the serial log after it joins Wi-Fi.
2. In **Audio Test**, set **Test Audio URL** to
   `http://<your-ip>:8000/beeps_sweep.mp3`.
3. Set **Volume** (0–100; 100 is the firmware's safety cap, not full power).
4. Press **Play Test Audio**.

You should hear three short beeps, a pause, then a sweep from low to high. If you hear
only two beeps, the start of playback is being clipped.

### Test files

| File | What it's for |
|---|---|
| `beeps_sweep.mp3` | Stereo MP3, the default check |
| `beeps_sweep.wav` | Mono WAV, rules out the MP3 decoder |
| `beeps_sweep_mono.mp3` | Mono MP3, reproduces a known issue: it does **not** play on ESPHome 2026.6.5 |

### Using your own music

Drop files into `test-audio/` and use `http://<your-ip>:8000/<file>`. The folder is
gitignored, so personal music is never committed by accident (only the clips above are
tracked). Write spaces in file names as `%20` in the URL, e.g. `01%20Song.mp3`.

Supported: stereo MP3, WAV, FLAC, Opus. Not supported: mono MP3 (see above), AAC/M4A,
Ogg Vorbis. HTTPS URLs and redirects work too.

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
| `ota.manifest_version` | string | `0.1.0` | Single source of truth for the OTA target version: drives both the hosted `manifest.json` `version` and the version the server locates on disk and pushes to boxes. Not derived from a filename. |

The config file path defaults to `config.yaml` relative to the working directory;
override with `BOOPBOX_CONFIG_PATH`.

### Media sources

#### Jellyfin (`type: jellyfin`)

```yaml
sources:
  - id: jellyfin-main                 # referenced by mappings and the API-key env var
    type: jellyfin
    base_url: http://jellyfin:8096    # Jellyfin server URL
    user_id: ""                       # optional
```

- The API key is read from the environment, not `config.yaml`:
  `BOOPBOX_SOURCE_<ID>_API_KEY` (for `id: jellyfin-main`,
  `BOOPBOX_SOURCE_JELLYFIN_MAIN_API_KEY`). See the `.env` reference for the `<ID>` naming rule.
- `base_url` points at the Jellyfin server reachable from the BoopBox server.
- `user_id` is optional; set it if item metadata lookups require a user context.
- A `mapping` entry of `kind: collection` may point at a Jellyfin collection,
  playlist, or album id; the server lists its members and plays one.

Jellyfin credentials and URLs stay server-side: they never appear in a `play`
command or the signed `/stream` URL, and upstream errors are returned to the box
as generic codes (`item_unavailable` / `source_unavailable`) with no upstream
detail.

### OTA firmware directory

The server hosts built firmware `.bin` files at `/firmware`. The directory is set
by `BOOPBOX_FIRMWARE_DIR` (default `firmware-bins`, relative to the working
directory). This is distinct from the repo's `firmware/` directory, which holds
ESPHome *source* YAML; the server serves built bins and does not build firmware.

Layout the admin must follow:

```
<firmware_dir>/esp32s3/boopbox-0.1.0.bin   # one chip subdir per chip family
<firmware_dir>/esp32s3/boopbox-0.2.0.bin   # older versions may be kept for rollback
```

- One **chip subfolder** per chip family. MVP supports `esp32s3` (→ `ESP32-S3`);
  unknown subfolders are skipped.
- Bin naming: `boopbox-<version>.bin`. The server locates the bin whose version
  matches `ota.manifest_version` in each chip dir.

To publish a build: drop the new bin in the chip subdir and set
`ota.manifest_version` to its version.

The hosted `/firmware/manifest.json` is generated from these bins and exists for
**browser-based provisioning** (ESP-Web-Tools flashing a fresh box over USB).
On-device updates are **server-pushed** over MQTT, not polled from this manifest.

### `.env` reference

All variables use the `BOOPBOX_` prefix. Values tagged **(secret)** must never be
committed — keep them in `.env`, not `config.yaml`.

| Variable | Default | Notes |
|----------|---------|-------|
| `BOOPBOX_STREAM_SECRET` | — (required) | **(secret)** HMAC signing secret for stream tokens. |
| `BOOPBOX_CONFIG_PATH` | `config.yaml` | Path to `config.yaml`. |
| `BOOPBOX_DB_PATH` | `devices.db` | SQLite file path. |
| `BOOPBOX_FIRMWARE_DIR` | `firmware-bins` | Non-secret, deploy-specific. Directory of built OTA `.bin` files the `/firmware` host serves. See the OTA firmware directory section for layout. Distinct from the repo's `firmware/` ESPHome-source dir. |
| `BOOPBOX_MQTT_HOST` | `localhost` | Broker host the server connects to at startup. |
| `BOOPBOX_MQTT_PORT` | `1883` | Broker port. |
| `BOOPBOX_MQTT_USERNAME` | empty | Broker username; empty connects anonymously. |
| `BOOPBOX_MQTT_PASSWORD` | empty | **(secret)** Broker password. |
| `BOOPBOX_MQTT_TLS` | `false` | Enable TLS to the broker. |
| `BOOPBOX_MQTT_TLS_CA` | empty | Path to a CA bundle when TLS is on. |
| `BOOPBOX_PUBLIC_BASE_URL` | `http://127.0.0.1:9685` | URL boxes use to reach the server; used verbatim to build signed `/stream` URLs. |
| `BOOPBOX_SOURCE_<ID>_API_KEY` | empty | **(secret)** API key per source. `<ID>` is the source id uppercased with non-alphanumeric runs replaced by `_` (e.g. `jellyfin-main` → `BOOPBOX_SOURCE_JELLYFIN_MAIN_API_KEY`). |
| `BOOPBOX_SEED_DEVICE_ID` | `boop-test` | MVP seed device, upserted at startup. |
| `BOOPBOX_SEED_DEVICE_MQTT_PASSWORD` | empty | **(secret)** Provisioned at the broker; never stored in the database. |

The `BOOPBOX_MQTT_*` variables are live runtime config: the server opens an MQTT
connection to the broker at startup and subscribes to `boopbox/+/boop`, so the
broker must be reachable with these settings for boops to be answered.
`BOOPBOX_PUBLIC_BASE_URL` is consumed to build the signed stream URL returned in
each `play`.

For the **bundled** broker, set `BOOPBOX_MQTT_HOST=mosquitto` (the Compose
service name), `BOOPBOX_MQTT_PORT=1883`, and the server account
`BOOPBOX_MQTT_USERNAME` / `BOOPBOX_MQTT_PASSWORD` you provisioned with
`mosquitto_passwd`. For an **external** broker, point `BOOPBOX_MQTT_HOST` at the
admin's broker and set its credentials (and `BOOPBOX_MQTT_TLS` + CA if it fronts
TLS). See "MQTT broker: bundled vs external" above.

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
