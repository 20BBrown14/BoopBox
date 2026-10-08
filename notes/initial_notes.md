NFC Music Box — Project Notes

## Hardware (the box)
- ESP32 to handle WiFi, NFC card reading, and driving a good speaker.
- Power: battery or wall powered. Rechargeable? Needs to be robust.
- Onboard memory for caching and/or out-of-network playback?

## Case (3D printed)
- Small printed case with access for the NFC reader and possibly a WiFi antenna.
- Include an indent for the character to sit in.
- Magnets probably won't work — they'd likely interfere with NFC reading.

## Character Bases (3D printed)
- Bases with nfc tags will be printed that other cheap characters can be added to.
- Protect the sticker with a cover or super glue? Should be hard to remove to avoid choking hazard or read failures.

## Server (new build)
- Handles requests from the boxes; should work well for both local and remote users.
- Auth: hardcoded keys? Some form of TOTP?
- MVP will support a Jellyfin media server.
- Flow:
  - Box sends a request containing a tag ID.
  - Tag IDs map to character names/IDs.
  - Server checks Jellyfin for music collections matching the character name.
  - Server picks a random song from collection and sends it back to play.

## Tag Technology Decision (NFC vs RFID)
- Going with NFC
- Safety is mainly mechanical: fully encapsulate the tag in the printed base so it can't be pried out and swallowed.

## Firmware (ESPHome)
- Keep the box dumb: it reads a tag, publishes it, and plays whatever URL the server sends back. All mapping/media-source logic lives on the server.
- Stock ESPHome covers everything we need with no custom C++:
  - `pn532_i2c` with an `on_tag` trigger exposes the tag UID (as `x`).
  - `mqtt` component publishes the boop and subscribes for play commands (see Transport).
  - `i2s_audio` + `media_player` plays the stream URL from the play command.
- ESPHome strengths for a multi-box fleet: WiFi, OTA updates, per-device config/secrets, auto-reconnect, captive-portal fallback — all declarative.
- Friction point to watch: audio playback is the least mature part of ESPHome. Validate the stream-URL playback path early.
- Plan: prototype the full experience in ESPHome, then decide whether audio/caching requirements justify native ESP-IDF/Arduino firmware later.
- Media player config on the box:
```yaml
i2s_audio:
  i2s_lrclk_pin: GPIO25
  i2s_bclk_pin: GPIO26

media_player:
  - platform: i2s_audio
    name: "BoopBox Speaker"
    id: boopbox_speaker
    dac_type: external
    i2s_dout_pin: GPIO22
```

## Transport (decided: MQTT)
- Control channel is MQTT. The box opens a persistent outbound connection to the admin's broker, publishes boops to `boopbox/<deviceid>/boop`, and subscribes to `boopbox/<deviceid>/play` for server-pushed play commands. Works through home NAT because the box initiates the connection.
- TLS vs plaintext (admin's choice):
  - Remote: MQTT over TLS on port 8883 (the HTTPS equivalent for MQTT).
  - Local-only: plain MQTT on port 1883 is acceptable if the admin trusts their LAN.
- Audio stream is separate: the play command carries an `http(s)://` stream URL the box's media player fetches. HTTPS for remote, plain HTTP acceptable for local-only.
- Caveat for on-device TLS: the box must carry the broker's CA cert and have accurate time (SNTP) for cert validity. Admins using TLS need a broker cert the box can verify (public CA, or their own CA provided at provisioning).

## Auth: Box → Server
- The box authenticates to the admin's broker/server; this is separate from server→media-source auth. The box is hardware we flash, so provision the secret at flash time.
- Per-device credentials: each box gets a unique auth token (MQTT username/password or token) baked into its ESPHome `secrets`. The server keeps `deviceId → token` and rejects mismatches. Per-device (not one shared key) means a lost/compromised box can be revoked without reflashing the fleet.
- TLS (MQTT over 8883) keeps the token off the wire for remote boxes; see the Transport section for the cert strategy.

## Provisioning (two-phase)
- Split setup so the server-side details and the WiFi are handled by different people at different times.
- Phase 1 — admin, at flash time (box in hand): bake in broker host/port, auth token, and CA strategy. Admin is technical and controls the server, so this is the easy phase.
- Phase 2 — recipient/family, on arrival: WiFi only, via ESPHome captive portal (box boots as AP → join → pick network → password → done). They should never see broker URL or a cert.
- Example (gifting a box to a remote relative): admin bakes everything server-side before shipping; the family just enters WiFi.

### Gotchas
- SNTP ordering: TLS validation needs correct time, but the box boots knowing nothing. It must reach NTP after WiFi connects but before the first TLS handshake, or validation fails with a confusing "cert not valid yet" error. Use `time: sntp` and mind the ordering.
- Baked vs entered / re-gift tension: baking broker/token/cert means re-pointing the box at a different server requires reflashing. Fine for a dedicated gift box; contradicts the open-source "bring your own server" field-editable idea.
  - Resolution: bake defaults at flash, but also expose an optional "advanced" captive-portal page to override server URL + token without reflashing. Supports both the gift flow (WiFi-only) and the BYO-server flow. Not on the MVP critical path.
## OTA / Firmware Updates
- Mental model: **MQTT triggers, HTTP delivers.** MQTT is for small messages, so it carries the "update now, here's where" nudge; the firmware binary itself is pulled over HTTP(S). Don't stream the binary over MQTT.

### Two ESPHome building blocks (verified against docs)
- `ota: platform: http_request` — box downloads a firmware binary from a URL and flashes it. The raw mechanism.
- `update: platform: http_request` — higher-level: box periodically reads a JSON manifest (`source:` URL, default check every 6h) and only updates when the manifest advertises a new version. Manifest is the ESP-Web-Tools format with an `ota` block carrying `md5`, `path`, and version — so **integrity checking (MD5) is built in**. This is the better fit; it also gives version-gating for free. Requires the `ota: http_request` + `http_request` components.
- We can still MQTT-trigger an immediate check/update rather than waiting for the poll interval.

### Requirements to get right
- Host the binaries + manifest on an internet-reachable HTTPS URL (naturally lives on the admin's server next to the broker).
- TLS: same CA/SNTP story as Transport — public-CA cert on the download host makes verification painless. (Note: GitHub release URLs redirect to long URLs that can blow the HTTP Request buffer; use non-redirecting hosting or raise the buffer.)
- Integrity: the manifest's `md5` guards against corrupt/wrong images. Add a version so a box won't re-flash the same build.
- Rollback safety: ESP32 dual-partition OTA auto-rolls back if a new image fails to boot — important protection for a box you can't physically reach (e.g. at the nephew's house).
- Auth: protect the OTA trigger topic with the same per-device MQTT auth. Pointing a box at an arbitrary firmware URL is a higher-value attack than a spurious boop, so the MD5/version checks are the belt-and-suspenders here.