# P4 — Stream token (pure HMAC mint + verify)

Implementation task list for piece **P4** from `../task_list.md`. Depends on P3
(error vocabulary), which is in place. P1–P3 are all implemented.

Delivers a dependency-free module that mints the opaque `body.mac` stream token
from claims `{device, source, item, exp}` and verifies it in strict order, with
duration-aware expiry and failures mapped to the `unauthorized` / `forbidden`
vocabulary.

## Builds on existing scaffolding

- `app/errors.py` (P3) — `ErrorCode` StrEnum with `unauthorized` and `forbidden`.
  **P4 maps verification failures to these two codes.** Verify fails as
  `unauthorized` (can't parse) vs `forbidden` (parsed, rejected), matching the
  design's 401/403 boundary; P6 later turns the code into an HTTP status via the
  existing `http_status_for`.
- `app/config.py` (P2) — `Settings.stream_secret` (required) is the HMAC key, and
  `Settings.config.streaming.pause_budget_seconds` (default 1800) feeds the TTL.
  **P4's pure functions should not read `Settings` directly** — take the secret
  and budget as parameters so the module stays dependency-free and unit-testable
  without config. The caller (P7) passes them in from `Settings`.
- `app/protocol.py` (P3) — unrelated to the token; the token is not a protocol
  message and carries no `v`.
- Shared types live under `app/types/` in this codebase; put the claims type there
  (e.g. `app/types/token.py`) or keep it local to the token module — see task 1.

P4 introduces no `config.yaml` key, no new `.env` var (the secret already exists
from P2), no new command. Per the documentation rule there is **no README change**
in this piece.

Placement (`server/`) and Python 3.12 are fixed.

## Contract this piece must expose

- **`mint(claims, duration, now) -> token`** — build the opaque token string.
- **`verify(token, now) -> claims | error`** — verify and return the claims, or an
  error signal mapping to `unauthorized` / `forbidden`.

Both are **pure** (no I/O, no config, no clock of their own — `now` and the secret
are passed in). Keep them importable from a stable module (e.g.
`app/stream_token.py`) for P6 (verify on `GET /stream`) and P7 (mint on boop).

## Token format (from the design — must match exactly)

```
claims  = { device, source, item, exp }        # exp is unix seconds (server clock)
body    = base64url(json(claims))               # compact, deterministic encoding
mac     = HMAC-SHA256(stream_secret, body)      # key is Settings.stream_secret
token   = body + "." + base64url(mac)           # the opaque <token> in ?sig=<token>
```

- Use **base64url without padding** consistently for both `body` and `mac`
  (document the exact variant chosen; verify must decode the same variant).
- JSON encoding must be **deterministic** (fixed key order, no spaces) so the same
  claims always produce the same `body` — e.g. `json.dumps(..., sort_keys=True,
  separators=(",", ":"))`.
- `exp` is unix **seconds**, integer, server clock only.

## Verification order (strict — fail at the first failure)

The order matters because the reported code depends on where it fails:

1. **Split on `.`** into `body` and `mac`. Missing `sig`/part, wrong shape, or bad
   base64 → **malformed** → `unauthorized`. Do not look at claims yet.
2. **Recompute** `HMAC-SHA256(secret, body)` and **constant-time compare** to the
   provided `mac`. Mismatch → `forbidden`.
3. Only after the MAC verifies, **decode `body`** and read the claims. If the
   decoded JSON is structurally broken *after* a valid MAC, treat it as malformed →
   `unauthorized` (a valid MAC over garbage shouldn't 403; document the choice).
4. Check `exp` against the passed-in `now` (server clock). Expired → `forbidden`.
5. Return the claims (`device`, `source`, `item`, `exp`). `device` is provenance
   only — P6 records it, does not enforce it.

## Duration-aware expiry (from the design)

`mint` computes `exp` from the passed-in `now` and item duration:

```
exp = now + item_duration + pause_budget          # when duration is known
```

Fallbacks when the source can't report a duration:

```
exp = now + pause_budget                           # no duration, budget known
exp = now + 300                                     # neither (5 min final fallback)
```

- `pause_budget` is `streaming.pause_budget_seconds` (default 1800), passed in by
  the caller.
- One clock only: `now` is supplied by the caller (server clock) for both mint and
  verify. The token carries no box-supplied time; nothing in verify consults a
  clock other than the `now` argument.

## Tasks

### 1. Module + claims type
- [ ] Create `app/stream_token.py` (stdlib only: `hmac`, `hashlib`, `base64`,
      `json`, `time` not needed inside — `now` is passed in).
- [ ] Define the claims shape. Options: a small frozen dataclass /
      `TypedDict` / pydantic model under `app/types/` (matching the codebase's
      `app/types/` convention), or a plain dict with documented keys. Pick one and
      keep `verify`'s return type consistent with it.
- [ ] Decide the error signal `verify` returns on failure. Since P4 is pure and
      must not raise HTTP concerns, return either an `ErrorCode`
      (`unauthorized`/`forbidden`) or a small result union (claims | ErrorCode).
      P6 turns the code into an HTTP response. Document the chosen return type.

### 2. `mint(claims, duration, now, *, secret, pause_budget) -> str`
- [ ] Compute `exp` per the duration-aware rules (known duration / no duration /
      final 5-min fallback). Accept `duration: int | None`.
- [ ] Assemble `claims = {device, source, item, exp}`, encode `body` with the
      deterministic JSON + base64url (no padding), compute the HMAC, base64url the
      mac, join with `.`.
- [ ] Return the opaque token string. No I/O, no global clock read.

### 3. `verify(token, now, *, secret) -> claims | ErrorCode`
- [ ] Implement the five-step order above exactly.
- [ ] Step 1 split/shape/base64 failures → `unauthorized`.
- [ ] Step 2 HMAC compare with **`hmac.compare_digest`** (constant time) →
      mismatch `forbidden`.
- [ ] Step 3 post-MAC decode failure → `unauthorized` (documented).
- [ ] Step 4 `exp <= now` → `forbidden`.
- [ ] Step 5 return claims.
- [ ] Never leak *why* beyond the code (the code is the contract; no detail
      strings needed from this pure layer — P6 builds the HTTP body via P3's
      `http_error`).

### 4. Tests (`tests/test_stream_token.py`)
- [ ] **Round-trip:** mint then verify with a `now` inside the window → returns the
      original claims (device/source/item/exp).
- [ ] **Tampered body:** flip a byte in `body` → `forbidden` (MAC mismatch).
- [ ] **Tampered mac:** flip a byte in `mac` → `forbidden`.
- [ ] **Truncated / malformed:** missing `.`, empty, non-base64, one-part token →
      `unauthorized` (a truncated token is malformed → 401, not 403).
- [ ] **Expired:** mint with a small window, verify with `now` past `exp` →
      `forbidden`.
- [ ] **Constant-time compare:** assert the implementation uses
      `hmac.compare_digest` (or test behaviorally that a wrong mac is rejected;
      the code-path assertion is the practical check).
- [ ] **Duration + fallbacks:** known duration → `exp == now + duration +
      budget`; `duration=None` with budget → `exp == now + budget`; neither
      (budget falsy/omitted path if representable) → `exp == now + 300`. Assert the
      exact `exp`.
- [ ] **Server-clock-only:** the same token verifies or expires purely by the
      `now` argument; there is no other time source (no field in the token can
      shift expiry — covered by tampered-body → forbidden).

## Verification / demo (piece acceptance)

- [ ] Mint a token for a 20-minute (1200s) item with the default 1800s budget and
      show `exp ≈ now + 3000` (~50 min).
- [ ] `verify` accepts that token within the window and returns the claims.
- [ ] A tampered variant → `forbidden`; an expired variant → `forbidden`; a
      truncated/malformed variant → `unauthorized`.
- [ ] No config or clock is read inside the functions — secret, budget, and `now`
      are all arguments.

## Notes / watch-outs

- **Purity is the point.** `mint`/`verify` take the secret, budget, and `now` as
  arguments and do no I/O. This keeps the module trivially unit-testable and keeps
  the single-server-clock rule honest (one `now`, passed in). The caller (P7/P6)
  sources them from `Settings` and the real clock.
- **Constant-time compare is required** — `hmac.compare_digest`, never `==` on the
  mac bytes.
- **401 vs 403 boundary** maps to the verify order: parse/shape failure (step 1,
  and the post-MAC decode in step 3) → `unauthorized`; a *verification* failure
  (bad MAC step 2, or expired step 4) → `forbidden`. Stop at the first failure.
- **`device` is provenance, not access control.** `verify` returns it; P6 records
  it and does not use it to authorize the requester.
- **No `v` in the token.** It is not a protocol message; `protocol.py` doesn't
  apply.
- **base64url + deterministic JSON** must be identical between mint and verify;
  pin the exact variant (padding or not, separators) and test the round-trip so a
  future encoding tweak can't silently break existing tokens mid-flight.
