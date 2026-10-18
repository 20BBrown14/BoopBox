# P6 — Stream endpoint (GET /stream, proxy + Range)

Implementation task list for piece **P6** from `../task_list.md`. Depends on P2
(config/data), P4 (token verify), and P5 (source interface + registry) — all
implemented. P1–P5 are in place.

Delivers `GET /stream?sig=<token>`: verify the token (P4), open the bound
source+item via the registry (P5), and proxy bytes honoring `Range`, mapping every
failure to the HTTP error contract (P3).

## Builds on existing scaffolding

- `app/stream_token.py` (P4) — `verify(token, now, *, secret) -> StreamClaims |
  ErrorCode`. **P6 calls this with the real clock and `Settings.stream_secret`.**
  The returned `StreamClaims` has `device`, `source`, `item`, `exp`.
- `app/sources/registry.py` (P5) — `SourceRegistry.get(source_id) -> Source`,
  already built at startup and stored on **`app.state.sources`** (see
  `main.py` lifespan). `Source.open(item, byte_range: Range | None) ->
  StreamResponse` (async context manager) and `Source.duration(...)`.
- `app/types/source.py` (P5) — `Range(start, end)` (inclusive), `StreamResponse`
  (`content_type`, `total_size`, `content_length`, `content_range`,
  `aiter_bytes()`, async-CM), and `SourceError(code, log_detail)`.
- `app/errors.py` (P3) — `ErrorCode`, `http_error(code, message=None) -> (body,
  status)`, `http_status_for`. **P6 renders every failure through these** so the
  body is `{code, message}` with a scrubbed message and the mapped status.
- `app/main.py` (P1/P5) — `create_app()` registers routes; the registry and DB are
  on `app.state`. **P6 registers the `/stream` route here** (or a router included
  here).

P6 introduces no `config.yaml` key, no new `.env` var, no new command. Per the
documentation rule there is **no README change** in this piece.

Placement (`server/`) and Python 3.12 are fixed.

## Contract this piece must expose

- **`GET /stream?sig=<token>`** route — verify → resolve source → proxy bytes with
  `Range`.
- **Proxy/Range behavior** — forward the client `Range` to the source, stream the
  bytes back incrementally (no full-item buffering), and set the correct status
  and headers (200 full / 206 partial, `Content-Range`, `Content-Length`,
  `Accept-Ranges`, `Content-Type`).

## Error → HTTP mapping (the contract)

Every failure returns the P3 JSON body `{code, message}` with the mapped status,
message scrubbed:

| Failure | ErrorCode | Status |
|---|---|---|
| `sig` missing / malformed / unparseable | `unauthorized` | 401 |
| bad HMAC or expired (verify → forbidden) | `forbidden` | 403 |
| source reports missing item (`SourceError`) | `item_unavailable` | 404 |
| source backend down (`SourceError`) | `source_unavailable` | 502 |

`verify` already returns `unauthorized` vs `forbidden` per the 401/403 boundary —
P6 does not re-derive it, just maps the returned `ErrorCode` through
`http_error`/`http_status_for`.

## Tasks

### 1. Route skeleton + settings/registry access
- [ ] Add `GET /stream` in `app/main.py` (or a small `app/routes/stream.py`
      router included by `create_app`). Pick one; keep it consistent with how the
      codebase grows routes.
- [ ] Read `sig` from the query string (`sig: str | None`).
- [ ] Access `Settings` via `get_settings()` and the registry via
      `app.state.sources` (FastAPI `Request` to reach `app.state`, or a dependency
      that pulls it). Do not rebuild the registry per request.

### 2. Verify the token
- [ ] Missing `sig` → `http_error(ErrorCode.unauthorized)` → 401. (verify also
      handles a malformed token, but a wholly-missing param should short-circuit to
      the same 401.)
- [ ] Call `verify(sig, now=int(time.time()), secret=settings.stream_secret)`.
      `now` is the **server clock**, read here (the pure module takes it as an
      argument).
- [ ] If `verify` returns an `ErrorCode`, render it: `http_error(code)` →
      `(body, status)`; return as JSON with that status. (`unauthorized`→401,
      `forbidden`→403 via the existing map.)
- [ ] If it returns `StreamClaims`, continue with `device`, `source`, `item`.

### 3. Parse the client `Range` header → `Range | None`
- [ ] Parse the HTTP `Range` request header into the P5 `Range(start, end)`
      (inclusive) or `None` for a whole-object request.
- [ ] Support the common `bytes=start-end`, `bytes=start-` (open-ended), and
      decide the handling of `bytes=-suffix` (suffix length). Resolve open-ended /
      suffix ranges against the source's `total_size` — which may require asking
      the source for size first, or letting the source resolve it in `open`. Pin
      which. Keeping range resolution in P6 (clamp against `total_size`) keeps the
      source simple; a source that only knows size at `open` time can return the
      satisfied `content_range` and P6 trusts it.
- [ ] Malformed/unsatisfiable `Range`: decide behavior. A malformed `Range` header
      is conventionally ignored (serve 200 full); an unsatisfiable range (start ≥
      size) is `416`. Note that `416` is outside the P3 vocabulary — either add a
      narrow direct `416` response here (documented) or treat a bad range as "serve
      full 200". Pick and document; do not invent a new error code.

### 4. Open the source and proxy bytes
- [ ] `source = app.state.sources.get(claims.source)` — unknown id is a
      programming error (resolver only yields configured ids); let it raise (500),
      it is not a client-facing vocabulary case.
- [ ] `async with await source.open(claims.item, byte_range) as resp:` then stream
      via a FastAPI `StreamingResponse` over `resp.aiter_bytes()`.
- [ ] Set status + headers from `StreamResponse`:
  - [ ] `200` when no range / whole object; `206` when `resp.content_range` is set.
  - [ ] `Content-Type: resp.content_type`.
  - [ ] `Content-Length: resp.content_length`.
  - [ ] `Content-Range: bytes {start}-{end}/{total}` when ranged
        (`resp.content_range`).
  - [ ] `Accept-Ranges: bytes`.
- [ ] Ensure the async CM `__aexit__` runs when the client disconnects mid-stream
      (FastAPI `StreamingResponse` + the `async with` around the iterator must
      release the upstream). Confirm the streaming generator closes the CM on
      GeneratorExit / client disconnect.

### 5. Map source failures (scrubbed)
- [ ] Wrap `open` (and any pre-open `duration`/size call) so a raised
      `SourceError` is caught: render `http_error(err.code)` → 404
      (`item_unavailable`) / 502 (`source_unavailable`). Log `err.log_detail`;
      never put it in the response `message`.
- [ ] No upstream body, URL, item id, or key appears in the response — the client
      sees only the generic P3 message for the code.
- [ ] `device` from the claims is recorded **for provenance only** (log it; a
      later hook could stamp `last_seen`), never used to authorize the requester.

### 6. Tests (`tests/test_stream.py`)
Use the P5 **fake source** via a test registry on `app.state.sources`, and mint
real tokens with `app.stream_token.mint` using the test `stream_secret`.
- [ ] **Happy path:** valid token → 200, body equals the fake's bytes,
      `Content-Type`/`Content-Length` correct, `Accept-Ranges: bytes`.
- [ ] **Range forwarded:** `Range: bytes=start-end` → 206, correct slice,
      `Content-Range` correct.
- [ ] **401 missing/malformed:** no `sig` → 401; a truncated/garbled token → 401,
      body `{code: "unauthorized", ...}`.
- [ ] **403 tampered:** flip a byte in the token → 403 `forbidden`.
- [ ] **403 expired:** mint with a past expiry (or small window + advanced clock) →
      403 `forbidden`.
- [ ] **404 missing item:** fake simulates `item_unavailable` → 404
      `item_unavailable`.
- [ ] **502 source down:** fake simulates `source_unavailable` → 502
      `source_unavailable`.
- [ ] **Scrubbed message:** the 404/502 body contains the generic message, not the
      fake's `log_detail`.
- [ ] **Cleanup:** client disconnect / generator close releases the source CM
      (assert the fake's close path ran).

## Verification / demo (piece acceptance)

- [ ] Mint a token against the fake source, hit `/stream?sig=...`, read the bytes
      back; a ranged request seeks correctly (206 + `Content-Range`).
- [ ] Each error surfaces the right status + code: 401 malformed, 403
      tampered/expired, 404 missing item, 502 source down.
- [ ] A simulated upstream error is scrubbed — the response carries only the
      generic message.

## Notes / watch-outs

- **Reuse the P3/P4/P5 pieces; don't re-derive.** `verify` already decides
  401-vs-403; `http_error` already builds the body + status; the registry already
  resolves ids. P6 is the wiring, not new policy.
- **Stream, don't buffer.** Proxy incrementally via `aiter_bytes()` /
  `StreamingResponse`. The design's local-first bandwidth-through-the-app tradeoff
  assumes streaming, not loading the whole item into memory.
- **Release upstream on disconnect.** The `StreamResponse` is an async CM for a
  reason — if the box pauses/aborts, P6 must close it so the upstream connection
  frees. Verify the close actually runs under client disconnect, not just normal
  completion.
- **`416`/`Range` edge is outside the P3 vocabulary.** Decide in task 3 between a
  narrow documented `416` and "ignore bad range, serve 200" — do not stretch an
  error code to cover it.
- **`device` is provenance only.** Record it; never authorize on it.
- **Unknown source id is a 500, not a vocabulary error.** The resolver only yields
  configured ids; a registry miss is a bug, so let it surface as a server error
  rather than dressing it as `item_unavailable`.
