# P10 — Broker config & Compose integration (Mosquitto + ACLs)

Implementation task list for piece **P10** from `../task_list.md`. Depends on P1
(scaffolding) and P7 (MQTT control plane) — both implemented. P1–P9 (plus 08a,
11) are in place.

Delivers deployment glue: a Mosquitto service behind a Compose
`bundled-broker` profile (profile out = no bundled broker), a Mosquitto config +
ACL file implementing the per-device topic pattern plus the broadcast exception,
and the `BOOPBOX_MQTT_*` env wiring so the app points at either the bundled
service or an external broker. ACLs live entirely in the broker, not the app.

## Builds on existing scaffolding

- `server/docker-compose.yml` — currently one `app` service: `build .`, port
  **`9685:9685`**, `env_file: .env`, a `config.yaml` read-only mount, an
  `app-data` volume, and `BOOPBOX_DB_PATH: /data/devices.db`. **P10 adds a
  Mosquitto service under a profile and wires the app to it.** Keep the existing
  app service intact.
- `server/Dockerfile` — app only; the app is **always just an MQTT client**, it
  never starts a broker. P10 adds no broker logic to the app.
- `app/config.py` (P2) — `Settings`:
  `mqtt_host`/`mqtt_port`/`mqtt_username`/`mqtt_password`/`mqtt_tls`/`mqtt_tls_ca`.
  `app/mqtt/service.py` builds the aiomqtt client from these and enables TLS
  (`CERT_REQUIRED`, `ca_certs = mqtt_tls_ca or None`) when `mqtt_tls` is set.
  **P10 sets these env vars to reach the chosen broker; it does not change the
  app.**
- `.env.example` (P2) already lists the `BOOPBOX_MQTT_*` defaults. **P10 documents
  bundled-vs-external in the README** and keeps `.env.example` consistent.

Placement (`server/`) and Python 3.12 are fixed.

## Topic & ACL contract (must match the live app exactly)

The broker ACLs must match the topics the app and boxes actually use
(`app/mqtt/publish.py` + `app/mqtt/service.py`). Do not invent topics:

- **Box publishes:** `boopbox/<id>/boop`, `boopbox/<id>/version`.
- **Box subscribes:** `boopbox/<id>/play`, `boopbox/<id>/error`,
  `boopbox/<id>/cmd` (play/error/cmd/flash all land on these), **and**
  `boopbox/all/cmd` (broadcast, read-only).
- **Server account publishes:** `boopbox/<id>/{play,error,cmd}` for any `<id>`
  and `boopbox/all/cmd`.
- **Server account subscribes:** `boopbox/+/boop`, `boopbox/+/version`
  (the two `SUBSCRIPTIONS`).

ACL rules:

- [ ] **Per-device pattern.** Each box account `%u` is confined to its own subtree
      via Mosquitto's `pattern` with `%u` → `boopbox/%u/#` (a box's username **is**
      its device id). Scope reads/writes so a box cannot publish to or (ideally)
      read another box's subtree. The *publish* restriction is the security
      priority (the design: without ACLs any authed client can inject commands to
      other devices / the cmd channel).
- [ ] **Broadcast exception.** `boopbox/all/cmd` is outside every box's
      `boopbox/<id>/#` subtree, so add an explicit rule: a box may **subscribe
      (read)** `boopbox/all/cmd`; only the **server** account may **publish
      (write)** there. Without this the per-device pattern correctly blocks boxes
      from receiving broadcasts.
- [ ] **Server account.** A single server user with broad read/write across
      `boopbox/#` (it talks to every device and owns the broadcast publish).
- [ ] ACLs live **entirely in the broker config/ACL file** — the app enforces
      nothing. Keep it that way.

## Tasks

### 1. Mosquitto config + ACL files
- [ ] Create a broker config dir under `server/` (e.g.
      `server/mosquitto/mosquitto.conf` + `server/mosquitto/aclfile`). Pin the
      layout and document it.
- [ ] `mosquitto.conf`: listener on **1883** (local/plain). Decide the auth stance
      for MVP — the design default is "no auth, no TLS" for the local
      bundled-broker case, but ACLs require authenticated usernames to key on
      `%u`. Pin one:
  - [ ] **Option A (recommended for the ACL demo):** `password_file` +
        `acl_file`, `allow_anonymous false`, so `%u` is meaningful and the ACL
        rules actually bind. Provide a sample `password_file` generation step
        (`mosquitto_passwd`) for the server account and the seed box account
        (`BOOPBOX_SEED_DEVICE_ID`).
  - [ ] **Option B:** `allow_anonymous true` with no ACL enforcement for the
        simplest local bring-up — but then the ACL acceptance test can't pass.
        If chosen, keep the ACL file present but note it's inert without auth.
  - [ ] Recommend A so P10's ACL acceptance criteria are real; document the
        local-plain default clearly either way.
- [ ] `aclfile`: the per-device `pattern readwrite boopbox/%u/#` (tighten
      publish/subscribe as above), the broadcast exception (`pattern read
      boopbox/all/cmd` for boxes; `user <server> ... write boopbox/all/cmd`), and
      the server account's broad `boopbox/#` access. Use placeholders for the
      server username; no real secrets committed.
- [ ] **TLS note (not full setup):** document the local-vs-TLS ports — 1883 local
      (bundled case), 8883 for TLS/remote — and that TLS/cert provisioning and
      fuller fleet/production deployment are **deferred** (note it, don't build
      it). The app already supports `BOOPBOX_MQTT_TLS` + CA for when an admin
      fronts TLS.

### 2. Compose `bundled-broker` profile
- [ ] Add a `mosquitto` service to `server/docker-compose.yml` under
      `profiles: ["bundled-broker"]` so it only runs when the profile is selected;
      leaving the profile out means no bundled broker (external-broker case).
  - [ ] Image: `eclipse-mosquitto` (pin a tag, not `latest`).
  - [ ] Mount the config + ACL (and password) files read-only into the container's
        expected paths; persist broker data if needed (a small volume) — decide
        and pin.
  - [ ] Expose **1883** (and note 8883 for the deferred TLS case; do not wire TLS
        now).
- [ ] Wire the **app** to the bundled broker when the profile is up: set
      `BOOPBOX_MQTT_HOST` to the mosquitto **service name** (e.g. `mosquitto`) and
      `BOOPBOX_MQTT_PORT=1883`, plus the server account `BOOPBOX_MQTT_USERNAME` /
      `BOOPBOX_MQTT_PASSWORD` if Option A. Decide the mechanism so it applies
      **only** when the profile is active without breaking the external case —
      e.g. app `environment:` overrides in compose, or documented `.env` values.
      Pin it; the external case leaves `BOOPBOX_MQTT_HOST` pointed at the admin's
      broker and the profile unselected.
- [ ] Optional `depends_on: [mosquitto]` for the app **only** under the profile —
      but the app's reconnect loop already tolerates a not-yet-up broker, so
      ordering is a nicety, not a requirement. Note that.

### 3. README — deployment & config (same piece per the documentation rule)
- [ ] Document **bundled vs external broker**: run the bundled Mosquitto with
      `docker compose --profile bundled-broker up`; for an external broker, omit
      the profile and point `BOOPBOX_MQTT_*` at it. Operational steps only.
- [ ] Document the **local-vs-TLS ports** (1883 local, 8883 TLS/remote) and that
      TLS and fuller production/fleet deployment are deferred (note, don't
      detail).
- [ ] Document the broker config/ACL file locations and the account model (server
      account + per-device box accounts keyed by device id), and the
      `mosquitto_passwd` step for Option A. Placeholders only; no real secrets.
- [ ] Confirm the `BOOPBOX_MQTT_*` entries (documented by P7) reflect both the
      bundled values and the external-broker override.

### 4. Acceptance test (broker-backed integration)
This is the broker-backed integration test deferred from P7. Keep it opt-in /
marked (it needs Docker), separate from the unit suite.
- [ ] **Stack up:** `docker compose --profile bundled-broker up` brings up broker
      **and** app; the app connects (log shows "mqtt connected; subscribed").
- [ ] **End-to-end boop→play→stream through the bundled broker:** publish a boop
      to `boopbox/<id>/boop` on the real broker (as the box account) → observe one
      `play` on `boopbox/<id>/play` with a signed URL → fetch `/stream` and get
      bytes (fake source is fine). This exercises the live broker + ACLs + P6 + P7
      together.
- [ ] **ACL denial (publish):** a box account publishing to **another** device's
      topic (e.g. `boopbox/<other>/cmd` or `boopbox/<other>/boop`) is **denied**
      by the broker.
- [ ] **ACL broadcast subscribe:** a box account may **subscribe**
      `boopbox/all/cmd` and receive a server-published broadcast; a box account
      **cannot publish** to `boopbox/all/cmd`.

## Verification / demo (piece acceptance)

- [ ] `docker compose --profile bundled-broker up` → broker + app up, app
      connected.
- [ ] A boop through the real bundled broker yields a played stream end-to-end.
- [ ] A cross-device publish from a box account is denied by the ACL; the
      broadcast subscribe is allowed while a box-side broadcast publish is denied.
- [ ] Omitting the profile runs the app alone against an external broker set via
      `BOOPBOX_MQTT_*` (no bundled broker starts).

## Notes / watch-outs

- **The app is always only a client.** P10 adds zero broker logic to the app; the
  broker is a separate service, and "bundled vs external" is purely a
  compose/env choice (profile in/out + `BOOPBOX_MQTT_HOST`). No app-side detection.
- **ACLs protect the control plane, in the broker.** The per-device publish
  restriction is the security priority — without it a leaked box credential can
  inject commands (incl. `cmd`/`flash`) to other devices. Enforce in Mosquitto,
  never the app.
- **Broadcast is the one exception to the per-device subtree.**
  `boopbox/all/cmd`: boxes read-only, server-only publish. Miss this and either
  broadcasts don't reach boxes or any box can spoof a fleet command.
- **ACLs need authenticated usernames.** `%u` only means something with
  `allow_anonymous false` + a password file. The "no auth" local default and a
  working ACL demo are in tension — Option A (auth on) is recommended so the ACL
  acceptance criteria are real; document whichever is chosen.
- **Match the live topics exactly** (`publish.py`/`service.py`): box pubs
  `boop`/`version`, box subs `play`/`error`/`cmd` + `all/cmd`, server subs
  `+/boop`/`+/version`. Don't drift the ACL from the code.
- **TLS/production deferred.** Document the 1883/8883 split and that the app
  already supports `BOOPBOX_MQTT_TLS`/CA, but do not build TLS cert provisioning
  or fleet/production deployment here — explicitly out of scope per the design.
- **App port is 9685** (not 8000) — keep stream-URL / `public_base_url` and any
  port references consistent with the existing compose/Dockerfile.
