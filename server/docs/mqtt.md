# BoopBox MQTT API

The box ↔ server contract runs entirely over MQTT. HTTP is only used for the
signed media stream and the OTA bin host; everything that drives a box — tap
responses, OTA commands, version telemetry — is MQTT. This document is the
reference for that message contract.

The server connects to the broker at startup, subscribes to the box-published
topics, and answers each message. It never polls.

## Conventions

- **Broker:** any MQTT 3.1.1 broker. The bundled deployment uses Mosquitto; see
  the README for bundled-vs-external setup.
- **Topic namespace:** every topic is under `boopbox/`.
- **Device id (`<id>`):** the box's stable identifier. It is also the box's MQTT
  username (the ACLs key on it) and the authoritative device id for a message —
  the server trusts the id in the topic, never a device id inside a payload.
- **Payloads:** UTF-8 JSON. Field names and shapes below are exact.
- **Protocol version (`v`):** every message carries an integer `v`. See
  [Protocol versioning](#protocol-versioning).
- **QoS / retain:** messages are published at the broker default QoS; no topic
  is retained. A box that is offline when a command is sent simply misses it and
  is caught on its next report (see [OTA](#ota-version-check-and-flash)).

## Topic map

| Topic | Publisher | Subscriber | Purpose |
|-------|-----------|------------|---------|
| `boopbox/<id>/boop` | box | server | A tag was tapped. |
| `boopbox/<id>/play` | server | box | Play this stream (answer to a boop). |
| `boopbox/<id>/error` | server | box | A boop could not be answered. |
| `boopbox/<id>/cmd` | server | box | A command for one box (`get_version`, `flash`, `write_tag`). |
| `boopbox/all/cmd` | server | all boxes | A broadcast command (`get_version`). |
| `boopbox/<id>/version` | box | server | Firmware/chip report (reply to `get_version`, or unsolicited). |

The server subscribes to `boopbox/+/boop` and `boopbox/+/version`. A box
subscribes to its own `boopbox/<id>/{play,error,cmd}` and (read-only)
`boopbox/all/cmd`.

## Messages

### `boop` — box → `boopbox/<id>/boop`

Published when a tag is tapped.

```json
{
  "v": 1,
  "id": "a1b2c3",
  "slug": "boop/zelda",
  "uid": "04:A2:2B:...",
  "ts": 1793328000
}
```

| Field | Type | Notes |
|-------|------|-------|
| `v` | int | Protocol version. No default on the wire; the server version-checks it. |
| `id` | string | Boop correlation id, echoed back in `play`/`error`. |
| `slug` | string | The tag's payload; resolved to a source + item server-side. |
| `uid` | string | NFC UID, informational. |
| `ts` | int | Box clock (unix seconds), informational only. |

The server answers **exactly one** message per boop: a `play` on success or an
`error` otherwise. Never both, never zero.

### `play` — server → `boopbox/<id>/play`

The box should stream `url`.

```json
{
  "v": 1,
  "boop": { "id": "a1b2c3", "slug": "boop/zelda" },
  "url": "http://server:9685/stream?sig=...",
  "title": null,
  "duration": 1234,
  "album": null,
  "artist": null
}
```

| Field | Type | Notes |
|-------|------|-------|
| `v` | int | Protocol version (server-stamped). |
| `boop` | object \| null | Correlation block `{id, slug}` from the causing boop. Absent for a future server-initiated play. |
| `url` | string | Signed, time-limited stream URL. Built from the server's `public_base_url`; the `sig` token expires. |
| `title`,`album`,`artist` | string \| null | Optional metadata; the box may ignore them. |
| `duration` | int \| null | Whole seconds, when known. |

The `url` carries an HMAC-signed token bound to the device, source, and item,
with a duration-aware expiry. It is single-purpose: it authorizes only this
stream fetch.

### `error` — server → `boopbox/<id>/error`

A boop could not be answered.

```json
{
  "v": 1,
  "boop": { "id": "a1b2c3", "slug": "boop/zelda" },
  "code": "unknown_tag",
  "message": "no mapping for the booped tag"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `v` | int | Protocol version (server-stamped). |
| `boop` | object \| null | Correlation block. May be partial or null only for `unsupported_version`, where the payload was not fully parseable. |
| `code` | string | Machine-readable error code; see [Error codes](#error-codes). |
| `message` | string | Generic, inert display text. Never leaks source internals. |

Branch on `code`, not `message`. `message` is a scrubbed default and is not
guaranteed stable wording.

### `cmd` — server → `boopbox/<id>/cmd` or `boopbox/all/cmd`

Two command shapes share the `cmd` topic; route on the `cmd` field.

**Thin command** (`get_version`), per-device or broadcast:

```json
{ "v": 1, "cmd": "get_version" }
```

**Flash command** (`flash`), per-device only — never broadcast:

```json
{
  "v": 1,
  "cmd": "flash",
  "url": "/firmware/esp32s3/boopbox-0.2.0.bin",
  "md5": "d41d8cd98f00b204e9800998ecf8427e"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `v` | int | Protocol version (server-stamped). |
| `cmd` | string | `get_version` or `flash`. |
| `url` | string | (`flash` only) Absolute served path of the bin for the box's chip. |
| `md5` | string | (`flash` only) Expected md5 of the bin, computed from the bytes on disk. |

The bin fetch at `url` is **authenticated** (per-device HTTP Basic); see the
README OTA section. A `flash` is only ever sent to a single device, with the bin
matching that box's own reported chip.

Box side: `url` is a path, so the box prefixes its configured server base URL.
The box ignores a `flash` whose `url` does not start with `/firmware/` or whose
`md5` is not 32 characters. A box acts on `get_version` from either topic but on
`flash` and `write_tag` only from its own `boopbox/<id>/cmd`.

**Write-tag command** (`write_tag`), per-device only — never broadcast. Puts the
box's tag reader into write mode so the next tag tapped is written with `slug`:

```json
{ "v": 1, "cmd": "write_tag", "slug": "boop/zelda" }
```

| Field | Type | Notes |
|-------|------|-------|
| `v` | int | Protocol version (server-stamped). |
| `cmd` | string | `write_tag`. |
| `slug` | string | The payload to write, 1–128 bytes. Stored as a single NDEF text record, which is what a later `boop` reports as `slug`. |

Box side:

- Write mode lasts **30 seconds**. The first tag tapped in that window is
  written; if none is, the box cancels write mode and returns to reading.
- Tapping a tag in write mode writes it and does **not** produce a `boop`. The
  tag has to be lifted and tapped again to boop.
- A second `write_tag` while one is pending replaces the pending slug and
  restarts the 30 seconds.
- The ring shows a slow purple pulse while waiting, then solid green for 1.5s
  once the write is done (a single red pulse if the tag could not be formatted).
- A command with a missing, empty, or over-128-byte `slug` is ignored.
- The box sends **no reply**: there is no result message in protocol v1, so the
  server cannot tell whether a write succeeded or timed out. Writes are for
  NTAG21x / Ultralight tags. The reader reports that a write was attempted, not
  that it verified.

### `version` — box → `boopbox/<id>/version`

The box's firmware/chip report. Sent in reply to `get_version`, and may also be
sent unsolicited (e.g. on boot).

```json
{ "v": 1, "firmware": "0.1.0", "chip": "esp32s3" }
```

| Field | Type | Notes |
|-------|------|-------|
| `v` | int | Protocol version. No default on the wire; version-checked. |
| `firmware` | string | Running firmware version. |
| `chip` | string | Chip family; must match a server firmware chip key (e.g. `esp32s3`). |

A `version` reply produces **no** response message. It is telemetry that feeds
the OTA policy and updates the device's last-seen firmware.

## Flows

### Tap → play

1. Box publishes `boop` to `boopbox/<id>/boop`.
2. Server version-checks `v`, resolves `slug` → (source, item), mints a signed
   stream URL, and publishes a single `play` to `boopbox/<id>/play` — or an
   `error` to `boopbox/<id>/error` if any step fails.
3. Box streams the `url`.

### Tag write

1. Server publishes `write_tag` with the `slug` to `boopbox/<id>/cmd`.
2. Box enters write mode for 30 seconds and writes the slug to the next tag
   tapped.
3. Nothing is published back. A later tap of that tag produces the usual `boop`
   carrying the written `slug`.

### OTA: version-check and flash

OTA is **server-driven push**, not a box-side poll. One stateless path:

1. Server publishes `get_version` (to one box via `boopbox/<id>/cmd`, or to the
   fleet via `boopbox/all/cmd`).
2. Box replies with `version` on `boopbox/<id>/version`. A box may also send this
   unsolicited.
3. Server compares the reported firmware to the target version. If the box is
   **stale**, it looks up the bin for the box's reported `chip` and publishes a
   per-device `flash` with that `{url, md5}`. A box already at the target, or a
   chip with no matching bin, gets no flash (the latter is logged, never
   guessed — a wrong-chip flash bricks the box).

No outstanding-query tracking or timeouts: an offline box simply does not reply
and is caught on its next report.

## Protocol versioning

A single integer `v` spans every message type. The server speaks exactly one
version (currently `1`); a bump is a breaking change to the whole contract.

- A **boop** with a missing or unsupported `v` is answered with an `error` coded
  `unsupported_version` (with a best-effort `boop` block — only the fields
  parseable before the unknown version).
- A **version** reply with a missing or unsupported `v` is dropped (logged, no
  side effect).
- A consumer receiving a higher `v` than it speaks should ignore the message.

## Error codes

Carried in the `error` message `code` field.

| Code | Meaning |
|------|---------|
| `unknown_tag` | The booped `slug` has no mapping. |
| `item_unavailable` | The resolved item could not be opened upstream. |
| `source_unavailable` | The media source is unreachable. |
| `unsupported_version` | The boop's protocol version is missing or unsupported. |

(`unauthorized` / `forbidden` exist in the shared vocabulary but surface on the
HTTP stream/OTA paths, not in MQTT `error` messages.)

## Authentication and ACLs

Broker authentication and per-device isolation live **entirely in the broker**,
not the app. The bundled Mosquitto config disables anonymous access; every
connection authenticates with a username.

- **Server account:** one account (the `BOOPBOX_MQTT_USERNAME`) with read/write
  across `boopbox/#`. It talks to every device and owns the broadcast publish.
- **Box accounts:** one per box, whose **username is its device id**. A box is
  confined to its own subtree and split by direction:
  - publish: `boopbox/<id>/boop`, `boopbox/<id>/version`
  - subscribe: `boopbox/<id>/play`, `boopbox/<id>/error`, `boopbox/<id>/cmd`
  - subscribe (read-only): `boopbox/all/cmd`

The publish restriction is the security priority: a leaked box credential cannot
inject commands to other devices or publish to the broadcast channel. Only the
server account may publish to `boopbox/all/cmd`.

See `server/mosquitto/aclfile` for the enforced rules and the README for account
provisioning (`mosquitto_passwd`).
