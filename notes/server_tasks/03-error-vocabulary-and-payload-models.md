# P3 — Error vocabulary, protocol versioning & payload models

Implementation task list for piece **P3** from `../task_list.md`. Depends on P1
(scaffolding), which is in place under `server/`. P1 and P2 are both implemented.

Delivers the shared error-code vocabulary with HTTP status mapping, the protocol
version constant with unknown-version handling, the Pydantic payload models
(boop, play, error, cmd), and a scrubbed error-response builder that never leaks
source internals.

## Builds on existing scaffolding

- `app/config.py` (P2) already uses `enum.StrEnum` (see `StreamingMode`) and
  pydantic v2 `BaseModel`. **Match those patterns**: `StrEnum` for the error code
  and protocol constant's home, pydantic v2 models.
- P3 is a pure vocabulary/model piece. It depends only on P1 and must **not**
  import from P2 (`config.py`, `db.py`, `resolver.py`). P2's resolver returns
  `None` on a miss; P7 — not P3 — is where that `None` becomes the `unknown_tag`
  code. P3 only defines the code so P7 can reach for it later.
- No new runtime dependency (pydantic is already pinned). No README
  config/`.env`/command changes — this piece introduces no admin-relevant knob, so
  per the documentation rule there is nothing to add to the README.

Placement (`server/`) and Python 3.12 are fixed.

## Contract this piece must expose

- **Error-code enum** — the vocabulary: `unknown_tag`, `item_unavailable`,
  `source_unavailable`, `unsupported_version`, `unauthorized`, `forbidden`. A
  `StrEnum` so values serialize as their string names.
- **HTTP-status map** — code → status: `unauthorized` 401, `forbidden` 403,
  `item_unavailable` 404, `source_unavailable` 502. (`unknown_tag`,
  `unsupported_version` are MQTT-only; see note in task 2.)
- **Protocol version constant `v`** — the single global integer protocol version,
  plus an unknown-version helper (consumer sees a higher `v` than it speaks →
  fail safe).
- **Payload models** — pydantic models for `boop`, `play`, `error`, `cmd`, each
  carrying `v`, and the `boop` correlation block where applicable.
- **Error builder** — a helper that produces error responses (HTTP body and the
  MQTT error payload) with a generic, inert `message` that never carries upstream
  internals.

Keep these importable from a stable module so P6 (HTTP errors), P7 (MQTT
play/error/cmd), and P9 (source-failure mapping) build on them.

## Target layout after P3

```
server/
  app/
    protocol.py      # PROTOCOL_VERSION constant + unknown-version helper
    errors.py        # ErrorCode StrEnum, HTTP status map, error builder
    models.py        # Boop, Play, Error, Cmd, BoopRef pydantic models
  tests/
    test_protocol.py
    test_errors.py
    test_models.py
```

Module split is a suggestion — one `protocol.py` plus `errors.py` plus `models.py`
keeps concerns separated, but a single `protocol.py` holding all three is
acceptable if preferred. Keep import names stable regardless.

## Tasks

### 1. Protocol version (`v`) + unknown-version handling
- [ ] `app/protocol.py`: `PROTOCOL_VERSION: int = 1` — the single global protocol
      version (one integer across every message type, not per-type).
- [ ] An unknown-version helper usable by both consumers:
  - [ ] A predicate like `is_supported(v: int) -> bool` (equal to the server's
        `PROTOCOL_VERSION`; a plain integer compare, no semver).
  - [ ] Document the two fail-safe behaviors this enables (the helper itself is
        just the check; the acting-on-it lives in P6/P7):
        - Server receives a `boop` with an unknown `v` → P7 rejects and publishes
          an `error` with code `unsupported_version`.
        - A consumer receiving a higher `v` than it speaks ignores the message.
- [ ] Keep it dependency-free (stdlib only).

### 2. Error-code vocabulary + HTTP status map
- [ ] `app/errors.py`: `ErrorCode(StrEnum)` with exactly the six codes:
      `unknown_tag`, `item_unavailable`, `source_unavailable`,
      `unsupported_version`, `unauthorized`, `forbidden`. Use `StrEnum` so each
      serializes to its own lowercase name (matches the design's JSON).
- [ ] HTTP status map (a dict or function) for the HTTP-surfaced codes:
      `unauthorized` → 401, `forbidden` → 403, `item_unavailable` → 404,
      `source_unavailable` → 502.
- [ ] Decide how the map treats MQTT-only codes (`unknown_tag`,
      `unsupported_version`): they have no HTTP status. Prefer the map simply not
      containing them (a lookup for an MQTT-only code is a programming error, not a
      silent default). Document this so P6 never maps an MQTT-only code to HTTP.

### 3. Payload models
`app/models.py`, pydantic v2 `BaseModel`, matching the design doc JSON exactly.
Every model carries `v`.

- [ ] **`BoopRef`** — the correlation block `{ id, slug }` echoed in play/error.
- [ ] **`Boop`** — inbound boop: `v`, `id`, `slug`, `uid`, `ts`.
  - [ ] `v` typed as int; `ts` unix seconds (int); `uid` string.
  - [ ] Note: the server also records its own receive time elsewhere (P2/P7); the
        model just carries the wire fields.
- [ ] **`Play`** — `v`, optional `boop` (`BoopRef`), `url`, `title`, `duration`
      (whole seconds, int), `album`, `artist`.
  - [ ] `boop` is **optional** — present only when a boop caused the play; a future
        server-initiated play omits it. Model it as `BoopRef | None = None`.
  - [ ] Metadata fields (`title`, `album`, `artist`, `duration`) — decide which are
        optional; the design shows them populated but the box may ignore them, so
        allow sensible optionality without breaking the documented happy-path shape.
- [ ] **`Error`** — `v`, `boop` (`BoopRef`), `code` (`ErrorCode`), `message`.
  - [ ] The `boop` block is normally present (an error always stems from a boop),
        **except** `unsupported_version`, which may carry a **partial** `BoopRef`
        (only fields parseable before hitting the unknown `v`) or none. Model this
        so a partial/absent `boop` is representable for that code — e.g. `boop`
        optional and/or `BoopRef` fields individually optional. Document the
        best-effort nature for `unsupported_version`.
  - [ ] `code` serializes as the `ErrorCode` string; `message` is free text.
- [ ] **`Cmd`** — `v`, `cmd` (e.g. `check_update`). Published to
      `boopbox/<id>/cmd` and `boopbox/all/cmd` (P7/P8). Keep `cmd` a string (or a
      small enum if preferred) — the design shows `check_update`.
- [ ] Default `v` on outbound models (`Play`, `Error`, `Cmd`) to
      `PROTOCOL_VERSION` from `protocol.py` so the server stamps the current
      version without every call site setting it. Inbound `Boop` takes `v` from the
      wire (no default — the server reads and version-checks it).

### 4. Error builder (generic, inert messages)
- [ ] A helper in `app/errors.py` that builds error responses with a **generic**
      `message` that never leaks source internals (no upstream bodies, URLs, item
      ids, API keys, or stack traces).
- [ ] Two shapes from one vocabulary:
  - [ ] HTTP error body: `{ "code": <ErrorCode>, "message": <generic> }` plus the
        mapped status (from task 2). A small helper returning both the body and the
        status, or a FastAPI-ready response — keep it so P6 can raise/return it
        directly.
  - [ ] MQTT error payload: an `Error` model instance (task 3) with the `boop`
        correlation block, `code`, generic `message`, and `v`. P7 publishes it.
- [ ] The builder takes the `code` and a caller-supplied **safe** message (or
      derives a default generic message per code). It must make it easy to do the
      right thing: the ergonomic path produces a scrubbed message. If a caller has
      upstream detail, that goes to **logs**, never into `message`.
- [ ] Treat `message` as inert display text: the builder does not interpolate
      untrusted input into HTML/shell/SQL/log-injection-prone sinks. Echoing a
      booped slug into a message (as in the `unknown_tag` example) is allowed as
      plain text, but the builder shouldn't format it into any executable context.

### 5. Tests
- [ ] `test_protocol.py`: `PROTOCOL_VERSION` is the expected int; `is_supported`
      true for the current version, false for a higher/unknown one.
- [ ] `test_models.py`:
  - [ ] Each model round-trips the documented JSON (serialize → matches the design
        doc shape; parse a sample payload → fields populate).
  - [ ] `Play` with and without the `boop` block.
  - [ ] `Error` with a full `boop` block, and with a partial/absent `boop` for
        `unsupported_version`.
  - [ ] Outbound models default `v` to `PROTOCOL_VERSION`.
  - [ ] `code` serializes to the lowercase string value.
- [ ] `test_errors.py`:
  - [ ] Status mapping correct for all four HTTP codes; MQTT-only codes behave as
        decided in task 2 (absent / explicit error, not a wrong status).
  - [ ] The error builder produces a generic `message` — assert it does **not**
        contain a supplied "upstream" detail string (simulate a leaky upstream
        error and confirm it's scrubbed).
  - [ ] HTTP builder returns the right `{code, message}` + status; MQTT builder
        returns a valid `Error` model with the correlation block.

## Verification / demo (piece acceptance)

- [ ] Serialize a sample `boop`, `play`, and `error` to JSON matching the design
      doc shapes.
- [ ] Show an `error` object whose `message` is scrubbed (a simulated upstream
      Jellyfin 401/404 maps to `source_unavailable`/`item_unavailable` with a
      generic message, not the upstream body).
- [ ] Status mapping returns the documented code for each HTTP error.
- [ ] Unknown-`v` helper returns the fail-safe result for a version the server
      doesn't speak.

## Notes / watch-outs

- **No P2 imports.** P3 is pure vocabulary + models; it depends only on P1. The
  resolver's `None` miss is mapped to `unknown_tag` by P7, not here. P3 just makes
  the code exist.
- **`code` is the contract, `message` is diagnostic.** Consumers branch on `code`
  only. The builder must make the scrubbed-message path the easy one; upstream
  detail goes to logs. Never pass raw upstream error text, URLs, item ids, or keys
  into `message`.
- **`unsupported_version` is the one partial-`boop` case.** Every other error
  carries a full `boop` block; model `Error` so a partial/absent block is valid
  specifically for this code without loosening the others into meaninglessness.
- **MQTT-only vs HTTP codes.** `unknown_tag` and `unsupported_version` never get an
  HTTP status; keep them out of the status map so a mislookup surfaces as an error
  rather than a silent wrong status.
- **Match P2's style.** `StrEnum` for the error code (as `StreamingMode` does),
  pydantic v2 models with explicit types, module-level constants. Keep import
  names stable for P6/P7/P9.
