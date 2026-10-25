# OTA / device auth — design note (not a build piece)

Rationale and options for authenticating the OTA + device surface. Captures a
verified ESPHome constraint and the eventual auth split. No code is built from
this yet; the MVP ships the OTA admin surface **unauthenticated** (documented as
such). This note exists so the later auth story is grounded.

## Two principals, two mechanisms

- **Device auth** — boxes fetching firmware bins / streaming / reporting. Plan:
  a static bearer-style token per device, provisioned at flashing time, stored
  server-side as a hash. A leaked token is handled by **revoke** (server-side
  kill switch; `Device.revoked` already exists) and/or physical reprovision
  (rotates the token). Revoke must invalidate immediately without touching the
  box; reprovision rotates.
- **Human / UI auth** — admin actions (OTA trigger endpoint, config, device
  management). Per-user auth lands with the UI. A device token must never
  authorize an admin action, nor vice versa. The OTA trigger endpoint (P9) is a
  human action and belongs behind UI auth, not device tokens.

## Verified ESPHome constraint (decides the device-auth mechanism)

Checked against ESPHome docs (2024.6+ HTTP OTA components):

- The managed **`update: http_request`** poller (the manifest poller) exposes
  **no auth knob** — only `source`, `update_interval` (default 6h), generic
  update options. It cannot send credentials or headers on the manifest fetch.
  *Content rephrased from ESPHome docs for compliance.*
- The **`ota: http_request.flash`** action **does** support **HTTP Basic auth**
  (`username`/`password`, URL-encoded) on the bin fetch. It also takes `url` +
  (`md5` or `md5_url`).
- The underlying **`http_request`** component supports arbitrary headers
  (a `Header{name,value}` vector), so a *custom automation* could send
  `Authorization: Bearer …` — but the managed `update:`/`ota:` platforms don't
  plumb a bearer header through.

Implication, and why the **push model helps**: the dead-end was the stock poller
being unable to authenticate the manifest fetch. The BoopBox OTA design drops the
poller (server-driven push; see `08-…` and `09-…`), so the box only fetches a bin
on command via the flash action. That removes the un-authable poll entirely and
makes device auth on the bin fetch viable.

### Options for authenticating the bin fetch
1. **HTTP Basic** (per-device user/pass) on the flash action — stock-supported,
   simplest. Only the bin fetch; no manifest fetch exists under push, so that gap
   is moot.
2. **URL-embedded token** (like `/stream`'s `?sig=`) — fits the stock components
   and the existing codebase pattern; token rides in the `flash` command's `url`.
   Must stay under the ~512-byte URL buffer; token appears in logs.
3. **Custom flash automation** with a templated `Authorization: Bearer` header —
   true bearer, but you own the flash automation instead of the stock action.

A static bearer **header** is the weakest fit for the firmware fetch specifically
(the stock action prefers Basic / url). A bearer header is fine for the **API**
surface (the admin OTA endpoint, future UI). For the bin fetch, option 1 (Basic)
or 2 (url token) matches ESPHome + the existing `/stream` design best. Pin the
choice when device auth is actually built.

## OTA transport integrity (separate, worth tracking)

md5 in the flash command protects against corruption, not a motivated attacker:
md5 is not collision-resistant, and nothing authenticates the **server** to the
box. If the box's HTTP fetch can be MITM'd, OTA is a code-exec path onto the
device. Mitigations for later (not MVP): HTTPS to the server, or mTLS (client
certs per device) which also authenticates the server and closes the MITM gap.
mTLS is the stronger device-auth upgrade path if OTA integrity becomes a
priority; bearer/Basic is the MVP.

## MVP stance

- OTA endpoints and the `/firmware` host ship **unauthenticated**, consistent
  with the rest of the config-file MVP admin surface. Documented as such and
  flagged for the auth story when the UI lands.
- Forward-compatibility: endpoints should be structured so an auth dependency can
  attach later (FastAPI dependency seam) without reworking them — but per the
  current decision, **do not add the seam yet**; keep MVP exactly as specced and
  let this note drive the later work.
