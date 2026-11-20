# BoopBox

An open source, open-design, media-source-agnostic tap-and-play media box.

The BoopBox server bridges the fleet of boxes to media sources. It acts as an
MQTT client of a Mosquitto broker for the control channel, and serves audio over
HTTP by proxying from media sources (Jellyfin first). A box reads an NFC tag,
publishes a boop over MQTT, and the server resolves the tag to media and returns
a signed stream URL the box plays. The server also hosts OTA firmware updates for
the fleet.

The Python server lives under [`server/`](server/). The box ↔ server MQTT message
contract is documented in [`server/docs/mqtt.md`](server/docs/mqtt.md).

## Development Guide

All commands run from the `server/` directory unless noted.

### Prerequisites

- Python 3.12
- Docker and Docker Compose (for the containerized run)
### Install dependencies

Create a virtual environment and install the project with its dev extras.

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Run locally (bare)

```bash
cd server
uvicorn app.main:create_app --factory --port 9685
```

This binds `127.0.0.1:9685`, matching the port the container serves on. Check the
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
  playlist, or album id. The server flattens it to playable audio tracks —
  expanding any album or sub-collection it contains to that container's tracks —
  then plays one at random.

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

- One **chip subfolder** per chip family. Only `esp32s3` (→ `ESP32-S3`) is supported;
  unknown subfolders are skipped.
- Bin naming: `boopbox-<version>.bin`. The server locates the bin whose version
  matches `ota.manifest_version` in each chip dir.

To publish a build: drop the new bin in the chip subdir and set
`ota.manifest_version` to its version.

The hosted `/firmware/manifest.json` is generated from these bins and exists for
**browser-based provisioning** (ESP-Web-Tools flashing a fresh box over USB).
On-device updates are **server-pushed** over MQTT, not polled from this manifest.

The bin fetch at `/firmware/<chip>/boopbox-<version>.bin` requires **per-device
HTTP Basic auth**: the username is the device id and the password is the device's
OTA secret (checked against a stored hash; a revoked device is refused). The
generated `/firmware/manifest.json` stays **public** — it is USB-side
provisioning metadata, not a box-authenticated fetch. See the Authentication
section for how device secrets are provisioned.

#### Testing OTA end to end

The box firmware (`firmware/BoopBox_v0.1.0.yaml`) handles `get_version` and
`flash` on `boopbox/<id>/cmd`, and `get_version` on `boopbox/all/cmd`. On
`flash` it downloads `${server_base_url}<url>` over HTTP Basic (device id plus
the OTA secret) and verifies the md5 before rebooting.

Setup, with `<server>` as the host the box can reach:

1. Set `BOOPBOX_SEED_DEVICE_OTA_SECRET` in `server/.env` and put the same value
   in `firmware/secrets.yaml` as `boopbox_ota_secret` (gitignored).
2. Build the baseline and the target from the same YAML, overriding the
   substitutions as needed (`mqtt_broker`, `mqtt_port`, `server_base_url`,
   `firmware_version`). The target must be the OTA-format bin
   (`firmware.ota.bin`), not the factory image.
   e.g. `esphome -s firmware_version 0.2.0 compile BoopBox_v0.1.0.yaml`, then
   take `.esphome/build/boopbox/.pioenvs/boopbox/firmware.ota.bin`.
3. Put the target at `server/firmware-bins/esp32s3/boopbox-<target>.bin` (bins
   there are gitignored; compose mounts the dir at `/firmware-bins`) and set
   `ota.manifest_version` in `config.yaml` to `<target>`. Restart the app so the
   index picks it up.
4. Flash the baseline over USB once. It reports its version on connect, which
   already triggers the flash if it is stale.
5. To re-trigger manually, run `server/scripts/ota_trigger.sh [device_id]`
   (reads the login from `.env`; `BASE=` overrides the URL), or:

```
TOKEN=$(curl -s -X POST http://<server>:9685/api/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"<user>","password":"<pass>"}' | jq -r .access_token)
curl -X POST http://<server>:9685/api/ota/update \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"device_id":"boop-test"}'
```

The server logs `ota: flashing ...`, the box fetches the bin and reboots, and
its next `version` report shows the target.

### Authentication

The server recognizes three separate credentials, each accepted only on its own
surface. A credential for one principal is never valid for another.

| Principal | Credential | Presented as | Guards |
|-----------|-----------|--------------|--------|
| User (UI/API) | JWT from `POST /api/auth/token` | `Authorization: Bearer <jwt>` | Human/UI actions under `/api` (e.g. `POST /api/ota/update`). |
| Device — OTA | Per-device OTA secret | HTTP Basic password (username = device id) | Firmware bin fetch (`/firmware/<chip>/…bin`). |
| Device — API | Per-device API token | `Authorization: Bearer <token>` (+ `X-Device-Id`) | Device-facing API routes. |

**User auth.** Users are stored in the SQLite database. On first run, while no
user exists, the server creates the owner account from
`BOOPBOX_DEFAULT_USERNAME` / `BOOPBOX_DEFAULT_PASSWORD`; both are ignored after
that. The owner must change that password at first login.

- `POST /api/auth/token` with `{"username", "password"}` returns a JWT and
  `must_change_password`. Any failure is the same generic `401`. Present the
  token as a bearer token on user routes.
- `POST /api/auth/password` with `{"current_password", "new_password"}` changes
  your own password and returns a new token. Until it is called, a user who must
  change their password gets `403` on every other user route.
- Tokens are HS256, signed with the generated `secrets.auth_token` setting, and
  last `auth.token_lifetime_hours` (8 by default). A password change revokes the
  user's other tokens.
- After `auth.lockout_threshold` wrong passwords (5 by default) within
  `auth.lockout_minutes` (15), the login is locked for `auth.lockout_minutes`.

**Device auth.** Each device holds two independent secrets, stored server-side
only as SHA-256 hashes on the device row and checked in constant time. A revoked
device (`revoked` flag) is refused on both immediately, server-side, with no box
interaction. The two secrets are deliberately distinct so a leak of one (the OTA
secret is the more log-exposed) cannot authorize the other.

**Provisioning.** There is no provisioning flow yet. The seed
device's secrets are supplied via `BOOPBOX_SEED_DEVICE_OTA_SECRET` and
`BOOPBOX_SEED_DEVICE_API_TOKEN`, hashed onto its row at startup. Generate secrets
the same way as the stream secret (e.g. `openssl rand -hex 32`).

Transport security (HTTPS/mTLS) is out of scope for now and is expected to be
terminated ahead of the server. Keep reverse-proxy and application logs from
capturing the `Authorization` header, since the OTA secret rides in it.

### `.env` reference

All variables use the `BOOPBOX_` prefix. Values tagged **(secret)** must never be
committed. Keep them in `.env`. Everything else is a server setting stored in the
database.

| Variable | Default | Notes |
|----------|---------|-------|
| `BOOPBOX_SECRET_KEY` | — (required unless `BOOPBOX_SECRET_KEYS_FILE` is set) | **(secret)** Encrypts the secrets stored in the database. 32 random bytes, base64url; `boopbox generate-key` prints one. Keep a copy outside the database. |
| `BOOPBOX_SECRET_KEYS_FILE` | empty | Alternative to `BOOPBOX_SECRET_KEY`: a file with one key per line, the first active. Wins when both are set. |
| `BOOPBOX_DEFAULT_USERNAME` | empty | Owner username, used only on first run while no user exists. Required then. |
| `BOOPBOX_DEFAULT_PASSWORD` | empty | **(secret)** Owner's first-login password (12–128 characters), used only on first run. Must be changed at first login. |
| `BOOPBOX_DB_PATH` | `boopbox.db` | SQLite file path. |
| `BOOPBOX_FIRMWARE_DIR` | `firmware-bins` | Directory of built OTA `.bin` files the `/firmware` host serves. See the OTA firmware directory section for layout. Distinct from the repo's `firmware/` ESPHome-source dir. |
| `BOOPBOX_LOG_LEVEL` | `INFO` | Python log level for the server. |
| `BOOPBOX_BROKER_HOST_PORT` | `1884` | Host port for the bundled broker. Read by Docker Compose, not the server. |

**Setting overrides.** Any server setting can be pinned from the environment as
`BOOPBOX_` plus its key upper-cased with `.` replaced by `_` (`mqtt.host` is
`BOOPBOX_MQTT_HOST`). The environment wins over the database. An empty value
counts as unset, and an invalid one fails startup. The ones most often set:

| Variable | Default | Notes |
|----------|---------|-------|
| `BOOPBOX_MQTT_HOST` | `localhost` | Broker host the server connects to. |
| `BOOPBOX_MQTT_PORT` | `1883` | Broker port. |
| `BOOPBOX_MQTT_USERNAME` | empty | Broker username; empty connects anonymously. |
| `BOOPBOX_MQTT_PASSWORD` | empty | **(secret)** Broker password. Held in memory only when set here. |
| `BOOPBOX_MQTT_TLS` | `false` | Enable TLS to the broker. |
| `BOOPBOX_MQTT_TLS_CA` | empty | PEM text of the broker's CA certificate when TLS is on. |
| `BOOPBOX_PUBLIC_BASE_URL` | `http://127.0.0.1:9685` | URL boxes use to reach the server; used verbatim to build signed `/stream` URLs. |
| `BOOPBOX_OTA_MANIFEST_VERSION` | empty | Target firmware version. No manifest is served while empty. |

The MQTT settings are live runtime config: the server opens an MQTT connection to
the broker at startup and subscribes to `boopbox/+/boop`, so the broker must be
reachable with these settings for boops to be answered. `public_base_url` is used
to build the signed stream URL returned in each `play`.

For the **bundled** broker, set `BOOPBOX_MQTT_HOST=mosquitto` (the Compose
service name), `BOOPBOX_MQTT_PORT=1883`, and the server account
`BOOPBOX_MQTT_USERNAME` / `BOOPBOX_MQTT_PASSWORD` you provisioned with
`mosquitto_passwd`. For an **external** broker, point `BOOPBOX_MQTT_HOST` at the
admin's broker and set its credentials (and `BOOPBOX_MQTT_TLS` + CA if it fronts
TLS). See "MQTT broker: bundled vs external" above.

#### Generating `BOOPBOX_SECRET_KEY`

The key is 32 random bytes, base64url-encoded. Generate one with either:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

```bash
docker compose run --rm app boopbox generate-key
```

Paste the output into `BOOPBOX_SECRET_KEY` in `.env`. Without it the secrets
stored in the database can't be decrypted, so keep a copy somewhere safe. The
stream and login-token signing secrets are generated by the server and stored
encrypted with this key.

### Database

Users, devices, settings and history are stored in a SQLite database at
`BOOPBOX_DB_PATH` (default `boopbox.db`), created at startup. Keep this file on a **local** filesystem:
SQLite WAL mode relies on local file locking and can corrupt or misbehave on a
networked filesystem (NFS, SMB).
