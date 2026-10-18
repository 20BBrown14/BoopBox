# P5 — Media source interface + fake source

Implementation task list for piece **P5** from `../task_list.md`. Depends on P1
(scaffolding); uses the P3 error vocabulary for unavailable conditions. P1–P4 are
all implemented.

Delivers the source protocol (open a ranged byte stream for an opaque `item`,
report duration where available), a fake in-memory source for downstream tests,
and a registry that resolves a configured source by id.

## Builds on existing scaffolding

- `app/types/config.py` (P2) — `SourceConfig` has `id`, `type`, `base_url`,
  optional `user_id`. **The registry keys off `SourceConfig.id`**; `type` selects
  which `Source` implementation builds the instance (P9 registers `jellyfin`).
- `app/errors.py` (P3) — `ErrorCode.item_unavailable` and
  `ErrorCode.source_unavailable`. **The source surfaces unavailable conditions as
  these two codes** (not HTTP, not raw upstream errors). P6 turns the code into an
  HTTP status.
- `app/types/` is the codebase convention for shared types (e.g. `StreamClaims` in
  `app/types/token.py`). Put the `Source` protocol / result types here.
- The resolver (`app/resolver.py`) returns `(source_id, item)`; P6 hands
  `source_id` to the registry and `item` to the resolved source. P5 never sees the
  slug — slug→(source,item) already happened.

P5 introduces no `config.yaml` key beyond the existing `sources`/`type` (already
documented by P2), no new `.env` var, no new command. Per the documentation rule
there is **no README change** in this piece. (P9 documents the Jellyfin block and
its API-key env when the real source lands.)

Placement (`server/`) and Python 3.12 are fixed.

## Contract this piece must expose

- **`Source` protocol** — given an opaque `item` id:
  - open an upstream byte stream honoring a `Range` request, and
  - report item metadata/duration where available.
- **Source registry** — build/hold sources keyed by `SourceConfig.id`; look one up
  by id. Unknown id is a caller error (the resolver only ever yields a configured
  id, but guard it).
- **Fake in-memory source** — fixed bytes, Range support, able to simulate
  `item_unavailable` / `source_unavailable`, reports a duration. For P6/P7/P9
  tests before (and alongside) the real Jellyfin source.

Keep these importable from a stable module so P6 (stream proxy) and P9 (Jellyfin
impl) build on them.

## Design decisions to pin (do these first)

These shape every signature below; decide and document before coding.

### 1. Streaming return shape (async + Range)
The app is single-loop async and proxies bytes with `Range`. The `Source.open`
call should return something the HTTP layer (P6) can stream incrementally without
buffering the whole item.
- [ ] Define the **range request** input: a byte range `(start, end)` or `None`
      for the whole object. Map from the HTTP `Range` header in P6, not here —
      P5's protocol takes a parsed range, keeping the source transport-agnostic.
- [ ] Define the **stream result**: an async iterator / async byte generator plus
      the response facts P6 needs to build a `206`/`200` — at minimum
      `content_length` (or total size), the `content_range`/satisfied range, and
      `content_type`. A small result dataclass under `app/types/` (e.g.
      `app/types/source.py`: `StreamResponse`) holding an `aiter_bytes()` and those
      fields reads cleanly. Pin the exact shape.
- [ ] Decide how an open stream is **closed** (async context manager, or the
      result exposes an `aclose()`). P6 must be able to release the upstream
      connection when the box disconnects mid-stream. Favor an async context
      manager so cleanup is structural.

### 2. Duration reporting
- [ ] Add a way to report item duration: either part of the stream result, or a
      separate `Source.duration(item) -> int | None` the caller (P7) uses when
      minting the token. P7 needs duration **at mint time, before** the stream is
      opened (the token expiry depends on it), so a standalone
      `duration(item) -> int | None` that doesn't require opening the stream is the
      cleaner fit. Pin whether duration is a separate call or rides along, and make
      the P7-at-mint path work.
- [ ] `None` duration is valid (triggers P4's no-duration fallback); model it
      explicitly.

### 3. Unavailable-condition mapping
- [ ] Decide how the source signals unavailable: raise a small typed exception
      carrying an `ErrorCode` (`item_unavailable` / `source_unavailable`), or
      return a result union. A typed exception (e.g. `SourceError(code,
      log_detail)`) tends to read best through an async streaming call. Pin it.
- [ ] The signal carries the `ErrorCode` for the contract and an optional
      **log-only** detail; it must never put upstream specifics into anything the
      client sees — P6/P3 build the scrubbed client `message`. Keep the leak
      boundary here from day one so P9 inherits it.

## Tasks

### 4. `Source` protocol
- [ ] In `app/types/source.py` (or `app/sources/base.py` — pick one, keep stable):
      a `typing.Protocol` (or ABC) `Source` with:
  - [ ] `open(item: str, byte_range: Range | None) -> StreamResponse` (async;
        context-managed per decision 1) — opens the ranged byte stream.
  - [ ] `duration(item: str) -> int | None` (async) per decision 2 — reports
        duration without requiring a stream open.
- [ ] Document that `item` is opaque and source-internal; the source never sees
      the slug.

### 5. Source registry
- [ ] A registry that, given the configured `sources` (list of `SourceConfig`),
      builds one `Source` per entry keyed by `id`, selecting the implementation by
      `type`.
- [ ] A `type`→builder mapping so P9 can register `jellyfin` without touching P5.
      For P5 the only registered type may be the fake (for tests) or an empty
      real-type set; the fake can also be injected directly in tests. Pin how
      types register (a module-level dict, a decorator, or explicit registration at
      app startup).
- [ ] `get(source_id) -> Source` lookup; unknown id raises (programming error — the
      resolver only yields configured ids). Document.
- [ ] Decide where the registry is constructed and held: built at startup from
      `Settings.config.sources` and stashed on app state (the P1 `lifespan` is the
      natural home, alongside the DB init). Note it here; P6 reads it off app
      state. Per-source secrets (API keys) come from `Settings` via
      `source_api_key_env` — the fake needs none.

### 6. Fake in-memory source
- [ ] A `Source` implementation over fixed in-memory bytes:
  - [ ] Serves the full object and honors a byte `Range` (returns the correct
        slice + range facts).
  - [ ] Reports a configurable duration, including a `None`-duration mode.
  - [ ] Can be configured to simulate `item_unavailable` (known source, missing
        item) and `source_unavailable` (backend down) via the decision-3 signal.
  - [ ] A fixed `content_type` (e.g. `audio/mpeg`) is fine.
- [ ] Keep it dependency-free and deterministic so downstream tests are stable.

### 7. Tests (`tests/test_sources.py` / `tests/test_fake_source.py`)
- [ ] Fake streams the **full** object: read all bytes → equals the fixture bytes;
      reported `content_length`/size correct.
- [ ] Fake honors a **ranged** read: `(start, end)` returns the right slice and the
      correct range facts (content-range/satisfied length).
- [ ] Fake **reports duration**, and the `None`-duration mode returns `None`.
- [ ] Fake surfaces **`item_unavailable`** and **`source_unavailable`** via the
      decision-3 signal, carrying the right `ErrorCode`; the client-facing path has
      no upstream detail (log-only detail stays out of the contract surface).
- [ ] **Registry** resolves a configured source by id; unknown id raises.
- [ ] Stream **cleanup** runs (context manager exit / `aclose` releases) — assert
      the close path is exercised.

## Verification / demo (piece acceptance)

- [ ] Open a stream from the fake source and read a byte range back correctly.
- [ ] Read the fake source's reported duration (and show the `None`-duration case).
- [ ] Trigger `item_unavailable` and `source_unavailable` and see the right
      `ErrorCode` with no upstream specifics in the client-facing signal.
- [ ] Resolve the fake by id through the registry.

## Notes / watch-outs

- **The source never sees the slug.** Resolution (slug→source+item) already
  happened in the resolver; P5 takes the opaque `item` id only.
- **Duration before stream open.** P7 mints the token *before* opening the stream
  and needs the duration for expiry — so duration must be obtainable without
  opening the byte stream. Decision 2 must make that path real, not an
  afterthought.
- **Scrub at the source boundary.** The unavailable signal carries an `ErrorCode`
  plus optional log-only detail; upstream URLs, item ids, keys, and bodies never
  reach the client. P6/P3 produce the generic client `message`. Establishing this
  in P5's fake means P9's real Jellyfin source inherits the discipline.
- **Async + cleanup.** Everything that touches the (future real) network is async
  and single-loop; the open stream must be releasable mid-flight when a box
  disconnects. Favor an async context manager.
- **Registry keys off `SourceConfig.id`; `type` selects the impl.** Keep the
  `type`→builder registration open so P9 adds `jellyfin` without editing P5.
- **No README change** — `sources`/`type` are already documented by P2; P9
  documents the Jellyfin specifics.
