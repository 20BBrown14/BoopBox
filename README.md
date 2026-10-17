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

- `config.yaml` — structured, human-edited configuration. No secrets.
- `.env` — secrets and deploy-specific values. Never committed.

No `config.yaml` keys or `.env` variables are defined yet. This section is
populated as later pieces introduce config. Config examples use placeholders,
never real secrets.
