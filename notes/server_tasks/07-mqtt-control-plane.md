# P7 — MQTT control plane (aiomqtt loop)

Implementation task list for piece **P7** from `../task_list.md`. Depends on P2
(config/data), P3 (error vocabulary + models), and P4 (token mint) — all
implemented. P1–P6 are in place.

Delivers the aiomqtt client on the app's single loop (started/stopped by the P1
lifecycle): subscribe `boopbox/+/boop`, and per boop version-check → resolve slug
→ pick an entry (collection-aware) → mint a token → build the stream URL →
publish exactly one `play` or `error`. Also publishes `cmd` (incl. check-now) to
per-device and broadcast topics, and stamps `last_seen_at` off-loop.

## Builds on existing scaffolding

- `app/main.py` lifespan — already builds the DB (`app.state.db`,
  `app.state.devices`) and registry (`app.state.sources`); the startup block
  reserves "P7 starts the MQTT loop here" and shutdown "P7 stops the MQTT loop
  here". **P7 wires the client's start/stop into these exact points.**
- `app/models.py` (P3) — `Boop` (wire `v`, `id`, `slug`, `uid`, `ts`), `Play`,
  `Error`, `Cmd`, `CmdName.check_update`, `BoopRef` (optional fields). Outbound
  models default `v` to `PROTOCOL_VERSION`.
- `app/protocol.py` (P3) — `is_supported(v)`; `PROTOCOL_VERSION`.
- `app/errors.py` (P3) — `ErrorCode`, `mqtt_error(code, boop, message=None) ->
  Error`, `default_message`. **P7 publishes `Error` via `mqtt_error`.**
- `app/resolver.py` (P2) — `resolve(settings, slug) -> list[MappingEntry] | None`.
  **Returns a list** (see collection handling below); `None` → `unknown_tag`.
- `app/types/config.py` (P2/P5) — `MappingEntry(source, item, kind)` with
  `MappingKind.item` / `MappingKind.collection`.
- `app/sources/registry.py` (P5) — `app.state.sources.get(source_id) -> Source`;
  `Source.duration(item) -> int | None` (needed at mint time) and `Source.open`.
  `SourceError(code, log_detail)` for unavailable conditions.
- `app/stream_token.py` (P4) — `mint(claims, duration, now, *, secret,
  pause_budget) -> str` with `claims` a `StreamClaims(device, source, item, exp)`
  (`app/types/token.py`).
- `app/db/devices.py` (P2) — `DeviceRepository.update_last_seen(device_id,
  firmware_version=None)` (async, off-loop via aiosqlite).
- `app/config.py` (P2) — `Settings`: `stream_secret`, `public_base_url`,
  `mqtt_host/port/username/password/tls/tls_ca`,
  `config.streaming.pause_budget_seconds`.

Placement (`server/`) and Python 3.12 are fixed.

## Documentation (this piece changes an admin knob)

P7 is the first piece to **use** the `BOOPBOX_MQTT_*` connection vars at runtime
(P2 defined them; P10 wires the broker). Per the documentation rule, **update the
README config reference** so the MQTT connection vars and their defaults are
documented as live runtime requirements: `BOOPBOX_MQTT_HOST` (default
`localhost`), `BOOPBOX_MQTT_PORT` (1883), `BOOPBOX_MQTT_USERNAME`/`PASSWORD`
(empty), `BOOPBOX_MQTT_TLS` (false), `BOOPBOX_MQTT_TLS_CA` (empty), and note
`BOOPBOX_PUBLIC_BASE_URL` is now consumed to build stream URLs.

## Contract this piece must expose

- **MQTT service** — `start()` / `stop()` (or an async task owned by the lifespan)
  running the aiomqtt client on the app's single loop.
- **Publish helpers** — publish `play` / `error` to `boopbox/<id>/{play,error}`,
  and `cmd` to `boopbox/<id>/cmd` and `boopbox/all/cmd`.

## Collection-aware entry selection (NEW vs original design)

The config model has evolved past the original design doc: a slug maps to a
**list** of `MappingEntry`, and each entry has a `kind` of `item` or
`collection`. The resolver returns the whole list. P7 must turn that list into one
concrete `(source, item)` to mint against. Pin this behavior:

- [ ] **Pick one entry from the list.** The design intent is "the server picks one
      entry to play." For MVP, pick **at random** across the list (uniform over the
      entries). Document the selection rule; keep it in one helper so it is easy to
      change (e.g. weighting) later.
- [ ] **Resolve a `collection` entry to a concrete item.** An entry with
      `kind == collection` names a collection id in `item`, not a playable item.
      Expanding a collection to its member items is a **source** capability — the
      member list lives in the backend (Jellyfin). Decide the interface:
  - [ ] Preferred: extend the `Source` protocol (P5) with a members/expand call
        (e.g. `members(collection_item) -> list[str]` or a `resolve_item(item,
        kind) -> str`), implemented by the fake (for tests) and by Jellyfin in P9.
        P7 calls it to turn a collection entry into a concrete item, then picks one
        member (random, same helper).
  - [ ] This touches P5's `Source` contract and P9's Jellyfin impl — note the
        cross-piece change explicitly. If the expand call is added, the fake source
        and `test_sources` must cover it, and P9 implements it against Jellyfin.
  - [ ] A `collection` with no members, or expansion failing, surfaces as a
        `SourceError` → `item_unavailable` (published as an `error`, see below).
- [ ] **`kind == item`** entries use `item` directly; no expansion.
- [ ] Order: pick the entry first, then expand if it is a collection — or expand
      all and pick a member. Pin one; picking-then-expanding avoids expanding
      collections that won't be played.

## Boop → response flow (exactly one response per boop)

Per boop on `boopbox/<id>/boop`:

1. [ ] **Parse + version-check.** Decode the payload; read `v`. If
       `not is_supported(v)` → publish `error` `unsupported_version` to
       `boopbox/<id>/error` with a **best-effort** `BoopRef` (only fields parseable
       before the unknown `v`; may be partial/None). One response, done.
2. [ ] **Parse the `Boop`** model (`id`, `slug`, `uid`, `ts`). A structurally
       invalid boop at a supported `v`: decide — treat as `unsupported_version` or
       drop with a log. (Pin; leaning toward a logged drop since there is no valid
       `boop.id` to correlate, but if `id`/`slug` parsed, an error echoing them is
       friendlier.)
3. [ ] **Resolve slug.** `resolve(settings, slug)`:
   - `None` → publish `error` `unknown_tag` to `boopbox/<id>/error` with the
     `BoopRef {id, slug}`. One response, done.
   - a list → collection-aware selection above → one concrete `(source, item)`.
4. [ ] **Duration + mint.** `duration = await source.duration(item)` (off-loop
       within the source; `None` is valid → P4 fallback). Mint:
       `mint(StreamClaims(device=<id>, source=<source>, item=<item>, exp=0), duration,
       now=int(time.time()), secret=settings.stream_secret,
       pause_budget=settings.config.streaming.pause_budget_seconds)`. A
       `SourceError` during `duration` → publish `error` with its `code`
       (`item_unavailable` / `source_unavailable`), scrubbed message.
5. [ ] **Build the URL.** `f"{settings.public_base_url}/stream?sig={token}"`.
       Use `public_base_url` verbatim (admin-supplied); do not derive host from the
       socket. URL-encode the token safely into the query.
6. [ ] **Publish `play`.** `Play(boop=BoopRef(id=boop.id, slug=boop.slug),
       url=url, title=..., duration=duration, album=..., artist=...)` to
       `boopbox/<id>/play`. Metadata may come from the source if available; absent
       is fine (optional fields). One response, done.
7. [ ] **Stamp last_seen off-loop.** `await
       app.state.devices.update_last_seen(device_id)` (aiosqlite already runs
       off-loop). Do this without blocking the boop response path (await is fine;
       it is off the event loop thread).

**Exactly one response per boop** — every path above ends in exactly one `play` or
one `error`, never both, never zero. Make the dispatch structurally enforce this
(e.g. a single function returning the one message to publish).

## Tasks

### 1. aiomqtt client lifecycle
- [ ] `app/mqtt.py` (or `app/mqtt/` package): an MQTT service holding the aiomqtt
      `Client`, configured from `Settings` (host/port/username/password/tls/tls_ca).
- [ ] Start it from the lifespan **startup** (the reserved spot) as a background
      task on the same loop; subscribe `boopbox/+/boop`. Stop/cancel it cleanly in
      **shutdown** (the reserved spot), before the DB connection closes.
- [ ] Reconnect/resilience: aiomqtt's connection context + a reconnect loop so a
      broker blip does not kill the task permanently. Keep it simple for MVP but do
      not let one dropped connection silently end message handling.
- [ ] Extract the device id from the topic (`boopbox/<id>/boop`) — it is the
      authoritative device id, paired with the per-boop `id`.

### 2. Boop handler (the flow above)
- [ ] Implement steps 1–7 as a handler. Version-check, parse, resolve,
      collection-aware select, duration+mint, URL, publish, last_seen.
- [ ] Single-response guarantee: structure so each boop yields one publish.

### 3. Collection-aware selection helper
- [ ] The entry-pick + collection-expand logic in one place (see the section
      above). Random pick for MVP; the `Source` expand call for collections.
- [ ] Coordinate the `Source` protocol extension with P5/P9 (fake + Jellyfin).

### 4. Publish helpers + cmd
- [ ] `publish_play(device_id, play)`, `publish_error(device_id, error)` to
      `boopbox/<id>/{play,error}` (JSON from the pydantic models).
- [ ] `publish_cmd(target, cmd)` where target is a device id (→
      `boopbox/<id>/cmd`) or the broadcast (→ `boopbox/all/cmd`). Support
      `Cmd(cmd=CmdName.check_update)` (the check-now nudge; P8/ops trigger it).
- [ ] Decide how cmd is triggered for MVP (an internal method callable by P8's
      manifest flow or an admin hook). Pin the entrypoint; the wire format is the
      `Cmd` model.

### 5. README config reference update
- [ ] Document the `BOOPBOX_MQTT_*` vars + defaults as live runtime config, and
      note `BOOPBOX_PUBLIC_BASE_URL` is consumed to build stream URLs. Secrets vs
      structured marking per the existing section. No rationale — operational
      reference only.

### 6. Tests (`tests/test_mqtt.py`) — broker fixture or mocked client
Prefer a mocked aiomqtt client (publish capture) so tests do not need a real
broker; an optional broker-backed integration test can live in P10.
- [ ] **Happy path:** a boop with a known `item` slug → exactly one `play` on
      `boopbox/<id>/play`; `boop` correlation (`id`+`slug`) matches; `url` uses
      `public_base_url` and carries a token that `verify` accepts; `duration` set.
- [ ] **Collection slug:** a slug whose selected entry is a `collection` →
      expansion picks a member → `play` for a concrete item. Cover an empty/failed
      collection → `error item_unavailable`.
- [ ] **Multi-entry pick:** a slug with several entries → one is chosen; with a
      seeded RNG, assert the selection is deterministic in test.
- [ ] **Unknown slug:** resolver `None` → one `error unknown_tag` with the
      `BoopRef {id, slug}`, on `boopbox/<id>/error`.
- [ ] **Unknown version:** boop with unsupported `v` → one `error
      unsupported_version` (boop block may be partial/None).
- [ ] **Exactly one response:** every path publishes exactly one message (assert
      no double-publish, no silent drop on the handled paths).
- [ ] **last_seen off-loop:** the device's `last_seen_at` is updated after a boop,
      via the repo (off-loop).
- [ ] **cmd:** `publish_cmd` emits a valid `Cmd` JSON to the per-device and
      broadcast topics.

## Verification / demo (piece acceptance)

- [ ] Publish a boop to a local broker; observe one `play` with a working signed
      URL (served by P6 → playable bytes from the fake source).
- [ ] Publish an unknown slug; observe one `error unknown_tag`.
- [ ] Publish a collection-backed slug; observe a `play` for a concrete member.
- [ ] Publish an unsupported `v`; observe one `error unsupported_version`.
- [ ] After a boop, the device's `last_seen_at` is updated.

## Notes / watch-outs

- **Single loop, single response.** The MQTT client runs on the app's one asyncio
  loop (same loop as HTTP). Every boop yields exactly one `play` or `error` —
  enforce it structurally, not by convention.
- **Collection handling is a cross-piece change.** Expanding a collection to
  members is a `Source` capability: it extends P5's protocol and P9's Jellyfin
  impl, and the fake source + `test_sources` must cover the new call. Flag it when
  touching P5/P9 so the contract stays consistent.
- **Duration before mint.** Fetch `source.duration(item)` before minting — the
  token expiry depends on it; `None` is valid and triggers P4's fallback.
- **`public_base_url` verbatim.** Build the stream URL from the admin-supplied
  base URL, never from the app's own socket/host.
- **Scrub source errors.** A `SourceError` during duration/expand publishes an
  `error` with its `code` and the generic message; `log_detail` goes to logs only.
- **last_seen off the loop.** `update_last_seen` is aiosqlite-backed (off-loop);
  `await` it, do not fire a blocking DB call on the loop thread.
- **Best-effort `boop` block for `unsupported_version`** only; every other error
  carries the full `BoopRef {id, slug}`.
