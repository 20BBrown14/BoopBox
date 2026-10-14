# NFC Music Box — Project Notes

## MVP
- On/off switch
- Connects to wifi via onboarding (wifi details not hardcoded in firmware like ESPHome can do)
- Reads tags and communicates with server (local and remote)
- Box streams the music
- Web UI to allow parents access to control available songs per user
- MQTT
  - Control channel is MQTT. The box opens a persistent outbound connection to the admin's broker, publishes boops to `boopbox/<deviceid>/boop`, and subscribes to `boopbox/<deviceid>/play` for server-pushed play commands. Works through home NAT because the box initiates the connection.
  - TLS vs plaintext (admin's choice):
    - Remote: MQTT over TLS on port 8883 (the HTTPS equivalent for MQTT).
    - Local-only: plain MQTT on port 1883 is acceptable if the admin trusts their LAN.
  - Audio stream is separate: the play command carries an `http(s)://` stream URL the box's media player fetches. HTTPS for remote, plain HTTP acceptable for local-only.
- OTA firmware updates
- Auth
  - The box authenticates to the admin's broker/server; this is separate from server→media-source auth. The box is hardware we flash, so provision the secret at flash time.
  - Per-device credentials: each box gets a unique auth token (MQTT username/password or token) baked into its ESPHome `secrets`. The server keeps `deviceId → token` and rejects mismatches. Per-device (not one shared key) means a lost/compromised box can be revoked without reflashing the fleet.
  - TLS (MQTT over 8883) keeps the token off the wire for remote boxes; see the Transport section for the cert strategy.

## Planned Future
- Battery
- Music cache
- stories/games?

## Maybe?


