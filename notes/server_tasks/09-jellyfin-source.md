# P9 — Jellyfin source implementation

Implementation task list for piece **P9** from `../task_list.md`. Depends on P5
(source interface + fake + registry) and P6 (stream endpoint) — both implemented.
P1–P8 (plus 08a, 11) are in place.

Delivers a real `Source` for Jellyfin: open an item's audio byte stream honoring
`Range`, report duration from item metadata, and expand a collection to its
member item ids — mapping every upstream failure to `item_unavailable` /
`source_unavailable` with generic, scrubbed messages. No change to P6.

## Builds on existing scaffolding (the contract P9 must satisfy)

- `app/types/source.py` (P5, extended by 08a/P7) — the `Source` protocol now has
  **three** methods P9 must implement:
  - `open(item, byte_range: Range | None) -> StreamResponse` — ranged byte stream.
  - `duration(item) -> int | None` — without opening the stream (P7 needs it at
    mint time).
  - `members(collection) -> list[str]` — expand a collection to member item ids
    (added for P7's collection-aware selection). Empty/failed expansion raises
    `SourceError`.
  - `StreamResponse` is an **async context manager** exposing `content_type`,
    `total_size`, `content_length`, `content_range`, and `aiter_bytes()`.
    `__aexit__` must release the upstream connection (P6 relies on this when the
    box disconnects mid-stream).
  - `SourceError(code, log_detail)` — `code` is `item_unavailable` /
    `source_unavailable`; `log_detail` is **log-only** and never reaches the
    client.
- `app/sources/fake.py` (P5) — the reference implementation of all three methods
  and the stream shape. **Match its `_FakeStream` shape** (content_range math,
  chunked `aiter_bytes`, `closed` on exit) so Jellyfin behaves identically to the
  fake from P6/P7's perspective. P9's tests mirror `test_sources`/`test_fake`.
- `app/sources/registry.py` + `app/sources/__init__.py` (P5) —
  `register_source_type("fake", _build_fake)` is the pattern. **P9 registers
  `register_source_type("jellyfin", _build_jellyfin)`** in `app/sources/__init__.py`
  (or an import with a side-effect registration), builder signature
  `(SourceConfig, Settings) -> Source`. The registry keys built sources by
  `SourceConfig.id`; `type == "jellyfin"` selects this builder.
- `app/types/config.py` (P2) — `SourceConfig(id, type, base_url, user_id)`.
  `base_url` is the Jellyfin server URL; `user_id` is optional.
- `app/config.py` (P2) — the API key is read from `.env` by source id:
  `source_api_key_env(source_id)` gives the env var name
  (`BOOPBOX_SOURCE_<ID>_API_KEY`), and `Settings.config.api_key_for(source_id)`
  returns the value (empty if unset). **The builder pulls the key via this, keyed
  by the source's id.**
- `httpx==0.28.1` is already pinned (P1) — use an async `httpx.AsyncClient`.

Placement (`server/`) and Python 3.12 are fixed. No change to P6 (the endpoint is
source-agnostic; swapping the fake for Jellyfin in config is the only wiring).

## Contract this piece must expose

- A `JellyfinSource` implementing the full `Source` protocol (`open`, `duration`,
  `members`), registered under `type == "jellyfin"`.
- A builder `_build_jellyfin(config, settings) -> JellyfinSource` wired into the
  registry, reading `base_url`/`user_id` from `config` and the API key from
  `.env` by source id.

## Jellyfin specifics to pin (do first)

The design names Jellyfin but not the exact endpoints. Pin these against the
Jellyfin API before coding; keep every URL/credential server-side.

- [ ] **Auth.** How the API key rides the request — the `X-Emby-Token` /
      `X-MediaBrowser-Token` header, or the `api_key` query param. Pin one; header
      is cleaner. The key comes from `config.api_key_for(source.id)`; if empty,
      decide behavior (treat as `source_unavailable` with a log, since an
      unconfigured source can't serve).
- [ ] **Stream endpoint.** The audio stream URL for an item id (e.g.
      `/Audio/<itemId>/stream` / `/Audio/<itemId>/universal` or the `/Items/.../
      Download`-style path). Pin the one that returns raw audio bytes and honors
      `Range`. Forward the client `Range` header upstream and relay the upstream
      `Content-Range`/`Content-Length`/`Content-Type`/`Accept-Ranges` back through
      `StreamResponse`.
- [ ] **Metadata / duration.** The item metadata endpoint (e.g.
      `/Users/<userId>/Items/<itemId>` or `/Items/<itemId>`) and the field for
      duration. Jellyfin reports `RunTimeTicks` in **100-nanosecond ticks** —
      convert to **whole seconds** (`ticks // 10_000_000`). Missing/zero → `None`
      (P4 fallback). Pin whether `user_id` is required for the metadata call.
- [ ] **Collection members.** The endpoint listing a collection/playlist's items
      (e.g. `/Items?ParentId=<collectionId>` or the playlist items endpoint).
      Return the member **item ids** (strings). Pin which container types a
      `collection` entry may point at (BoxSet/Playlist/MusicAlbum, etc.) if it
      matters.

## Tasks

### 1. `JellyfinSource` skeleton + client
- [ ] `app/sources/jellyfin.py`: a `JellyfinSource` holding `base_url`, optional
      `user_id`, the API key, and an `httpx.AsyncClient` (async, single-loop).
- [ ] Decide client lifecycle: a client per source instance created at build time
      (closed on app shutdown) vs per-request. A long-lived `AsyncClient` with
      connection pooling is the right call for a proxy; pin how/when it closes
      (the registry/source may need an `aclose`; P6's per-stream CM is separate
      from the client lifetime). If a close hook is needed, note the seam (the
      lifespan builds the registry; closing clients at shutdown is a small
      addition — flag it, do not leak connections).
- [ ] Centralize auth + URL building in one place so no call site hand-builds a
      credentialed URL.

### 2. `duration(item)`
- [ ] GET the item metadata; parse duration from `RunTimeTicks` → whole seconds.
- [ ] Missing/zero duration → return `None` (valid; triggers P4's fallback).
- [ ] Map failures (see task 5) to `SourceError`; never return a wrong number.

### 3. `open(item, byte_range)`
- [ ] Open the audio stream with `httpx` streaming (`client.stream(...)`), passing
      the upstream a `Range` header derived from `byte_range` (inclusive
      `bytes=start-end`) when set.
- [ ] Return a `StreamResponse` (a real class mirroring `_FakeStream`'s fields):
  - [ ] `content_type` from the upstream response.
  - [ ] `total_size` from upstream `Content-Range` total (ranged) or
        `Content-Length` (full).
  - [ ] `content_length` = bytes in this response.
  - [ ] `content_range` = `(start, end, total)` when the upstream returned 206,
        else `None`.
  - [ ] `aiter_bytes()` streams the upstream body incrementally
        (`response.aiter_bytes()`), no full buffering.
  - [ ] `__aexit__` closes the upstream response/stream so the connection is
        released on P6 client disconnect.
- [ ] If the upstream ignores `Range` and returns 200 for a ranged ask, decide:
      relay as full (P6 set no 206) or slice client-side. Pin — relaying
      upstream's actual status is simplest and correct; P6 already handles 200 vs
      206 from `content_range`.

### 4. `members(collection)`
- [ ] GET the collection's items; return the list of member **item id** strings.
- [ ] Empty collection → `SourceError(item_unavailable)` (matches the fake's
      behavior and P7's expectation).
- [ ] Failures → `SourceError` per task 5.

### 5. Error mapping + scrubbing (the security-sensitive core)
- [ ] Wrap every upstream call so these map to `SourceError` with a **generic**
      message and the real detail in `log_detail` only:
  - [ ] Jellyfin **404** (item/collection not found) → `item_unavailable`.
  - [ ] Jellyfin **401/403** (bad/missing key) → `source_unavailable` (the source
        can't serve; per the design example, an auth failure is a source problem,
        not an item problem — pin and document this mapping).
  - [ ] Jellyfin **5xx** → `source_unavailable`.
  - [ ] `httpx` **connection errors / timeouts** → `source_unavailable`.
  - [ ] Empty collection (task 4) → `item_unavailable`.
- [ ] **Never leak upstream internals** to the client: no Jellyfin URL, item id,
      API key, or response body in anything that becomes the client `message`. All
      of that goes to `log_detail` (logs only). P6/P3 render the generic message
      from the code.
- [ ] Set sane timeouts on the `httpx` client so a hung Jellyfin becomes a
      `source_unavailable` rather than a stuck stream/boop.

### 6. Register the type
- [ ] Add `_build_jellyfin(config, settings)` building a `JellyfinSource` from
      `config.base_url`, `config.user_id`, and
      `settings.config.api_key_for(config.id)`.
- [ ] `register_source_type("jellyfin", _build_jellyfin)` in
      `app/sources/__init__.py` next to the fake registration.

### 7. README — config reference (same piece per the documentation rule)
- [ ] Document the Jellyfin source config block in `config.yaml`
      (`sources[].type: jellyfin`, `base_url`, optional `user_id`), with a
      placeholder example.
- [ ] Document the API-key env var naming: `BOOPBOX_SOURCE_<ID>_API_KEY` (the
      `<ID>` normalization from `source_api_key_env`), marked a **secret** in the
      `.env` reference. Show a placeholder, never a real key.
- [ ] No rationale — operational reference only.

### 8. Tests (`tests/test_jellyfin.py`) — mocked Jellyfin via httpx transport
Use `httpx.MockTransport` (or a respx-style mock) so no real Jellyfin is needed;
keep deterministic like `test_fake`.
- [ ] **stream full:** `open(item, None)` → full bytes relayed; `content_type` /
      `content_length` / `total_size` from the mocked upstream; `content_range`
      None; status path yields P6's 200.
- [ ] **stream ranged:** `open(item, Range(start,end))` forwards
      `Range: bytes=start-end` upstream, relays the 206 slice and
      `content_range = (start,end,total)`.
- [ ] **duration:** `RunTimeTicks` → whole seconds; missing/zero → `None`.
- [ ] **members:** collection items → list of ids; empty collection →
      `item_unavailable`.
- [ ] **error mapping:** mocked 404 → `item_unavailable`; 401/403 → 
      `source_unavailable`; 5xx → `source_unavailable`; connection error/timeout →
      `source_unavailable`.
- [ ] **scrubbing:** the raised `SourceError` carries the upstream detail only in
      `log_detail`; assert the client-facing message (via P3 `default_message`/
      `http_error`) contains **no** URL, item id, key, or upstream body.
- [ ] **stream cleanup:** the `StreamResponse.__aexit__` closes the upstream
      response (assert via the mock/transport that the stream was closed).
- [ ] **registry:** a `type: jellyfin` config entry builds a `JellyfinSource` via
      the registry; the API key is read from the right env var by source id.

## Verification / demo (piece acceptance)

- [ ] Swap the fake for Jellyfin in `config.yaml` (set `type: jellyfin`,
      `base_url`, and the per-source API key in `.env`) and stream a real item
      end-to-end through `/stream` (P6), including a seek (ranged request).
- [ ] A missing item → 404 `item_unavailable`; Jellyfin offline/auth-failing →
      502 `source_unavailable`; the client sees only generic messages (no Jellyfin
      internals), while logs carry the detail.
- [ ] `duration` returns the item's seconds (feeding P7's token expiry); a
      collection-backed slug expands to a member and plays (P7 + P9 `members`).

## Notes / watch-outs

- **No P6 change.** The endpoint is source-agnostic; P9 is a drop-in `Source`.
  Resist adding Jellyfin specifics to P6.
- **Scrub at the boundary — this is the security-critical part.** Upstream 401s,
  URLs, item ids, keys, and bodies **never** reach the client. `code` + generic
  message is the contract; detail is `log_detail`/logs only. The fake already
  models this discipline; Jellyfin must not regress it.
- **Auth failure is `source_unavailable`, not `item_unavailable`** (per the design
  example) — a bad/missing key means the source can't serve, not that the item is
  gone. Pin this so the box's LED/behavior is consistent.
- **Ticks → seconds.** Jellyfin `RunTimeTicks` are 100-ns ticks;
  `// 10_000_000`. Zero/missing → `None`, not `0` (P4's fallback vs a bogus
  short-lived token).
- **Stream incrementally and release on disconnect.** Mirror the fake: chunked
  `aiter_bytes`, async-CM close. A hung upstream must time out into
  `source_unavailable`, not wedge the single loop.
- **Long-lived `httpx.AsyncClient`** per source (pooling) — but make sure it is
  closed at shutdown; flag the lifespan seam rather than leaking connections.
- **`members` must match P7's expectation:** returns member item ids; empty/failed
  → `SourceError(item_unavailable)`, which P7 turns into a published `error`.
- **Keys/URLs stay server-side.** Jellyfin credentials and URLs never appear in a
  `play` command, a stream URL (the box gets the signed `/stream` proxy URL, not
  Jellyfin), or any client-visible field.
