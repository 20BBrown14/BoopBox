# BoopBox
An open source open-design and media source agnostic tap and play media box. 

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
