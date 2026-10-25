# P11 — OTA version-check + push policy

The server-driven OTA **policy**: decide which boxes are stale and push `flash`
to them, via a single stateless version-check path. Depends on P8 (firmware
index + static host) and the P7 OTA protocol additions
(`08a-ota-protocol-additions.md`: `get_version`/`flash` commands + the
`boopbox/<id>/version` reply + its consumer). Added to `../task_list.md` as P11
(`P7 → P11`, `P8 → P11`).

## The single decision path (stateless)

Every update funnels through one path; triggers only initiate it, none flashes
directly:

1. Server publishes `get_version` to a box (or broadcast) — P7 command.
2. Box replies on `boopbox/<id>/version` — P7 consumer parses
   (device, version, chip).
3. **This piece** compares the reported version to the target
   (`ota.manifest_version`); if the box is stale, it looks up the bin for the
   box's chip in P8's firmware index and publishes `flash` with that
   `{url, md5}`.

**Stateless/reactive (MVP):** react to whatever `/version` replies arrive. No
tracking of outstanding queries, no timeouts, no ret/ack bookkeeping. An offline
box simply does not reply and is caught the next time it reports (boop or boot
`/version`). This makes all triggers the same handler.

A box that reports an **outdated version unsolicited** (on boot, or a version
observed via other telemetry) hits the exact same compare-and-maybe-flash
handler. Unifying solicited and unsolicited replies behind one handler is the
whole point of the stateless design.

## Chip resolution

- **Decided:** the box reports its **chip family in the `/version` reply**, so the
  handler reads it directly from the parsed reply and calls `index(chip)`. The
  reply payload therefore carries both the firmware version and the chip (pin the
  chip field + its value convention in P7's reply model — it must match P8's chip
  subfolder keys, e.g. `esp32s3`, so `index(chip)` resolves). A flash to the
  wrong-chip bin bricks the box, so the chip is always taken from the box's own
  report, never inferred server-side. If a reply omits the chip (or it's unknown
  to the index), **no flash** — log and skip.

## Triggers

### A. Admin uploads a new version (configurable)
- [ ] When the admin publishes a new build (drops a bin + bumps
      `ota.manifest_version`), the server broadcasts `get_version` to online boxes
      so the normal path updates the stale ones.
- [ ] **Configurable:** a config knob gates this auto-push-on-new-version (pin the
      key, e.g. `ota.auto_push_on_publish`, default pinned — likely `false` so an
      upload is inert until explicitly enabled). Decide the detection mechanism
      for "a new version was uploaded": config reload observing a changed
      `manifest_version`, an admin action/endpoint, or an explicit rebuild hook.
      Pin it (reusing P8's `rebuild()` seam is natural).

### B. Box reports an outdated version
- [ ] Any `/version` reply (solicited or unsolicited) with a version behind the
      target triggers a `flash` to that box. This is just the shared handler; no
      extra trigger code beyond consuming P7's parsed reply.

### C. Admin endpoint (future UI)
- [ ] `POST`-style endpoint (pin the path, e.g. `POST /ota/update`) that triggers
      the version check for a box or the fleet. **It triggers the `get_version`
      query, not a forced flash** — the normal version-check path decides whether
      an update actually happens. Pin the request shape: optional `device_id`
      (absent = broadcast query, present = that device). Validate an unknown
      device id against the device repo (404). Reach `app.state.mqtt` to publish.
- [ ] **Auth:** this is an admin/fleet action behind the future UI auth. The
      config-file MVP has no auth layer; ship it **unauthenticated** like the rest
      of the MVP admin surface, document that, and mark it for the auth story.
      Keep it off any box-facing path. (See the auth design note for the
      per-device-token vs UI-user-auth split and the ESPHome header constraint.)

## Wiring
- [ ] The policy is a small service on `app.state` (e.g. `app.state.ota_policy`)
      holding references to the firmware index (P8), the target version (config),
      and the publisher (P7 `send_cmd`). P7's `/version` consumer calls into it
      with (device, version, chip).
- [ ] Register the admin endpoint router via the `app/routes/__init__.py`
      re-export pattern.
- [ ] No new background task for MVP: the path is reactive to MQTT replies and the
      admin endpoint. (A periodic "sweep the fleet" is a post-MVP addition, not
      needed given boxes report on boop/boot.)

## Tests
- [ ] **stale → flash:** a `/version` reply behind the target → publishes `flash`
      to `boopbox/<id>/cmd` with the index's `{url, md5}` for the box's chip.
- [ ] **current → no flash:** a reply at the target → no publish.
- [ ] **unknown chip / no bin in index → no flash** (logged), never a wrong-chip
      flash.
- [ ] **endpoint triggers query only:** `POST /ota/update` with no body →
      broadcast `get_version`; with `device_id` → per-device `get_version`; it
      does **not** publish `flash` directly. Unknown device id → 404.
- [ ] **auto-push knob:** with the knob off, a new-version publish broadcasts no
      query; with it on, it broadcasts `get_version`.
- [ ] Use a captured/mocked publisher (as `test_mqtt` does).

## Watch-outs
- **Never flash the wrong chip.** Resolve the box's chip explicitly from the reply
  and only flash the matching index bin. A missing/ambiguous chip → no flash +
  log, not a guess.
- **Triggers initiate, the path decides.** No trigger (admin upload, endpoint,
  unsolicited report) flashes directly; all go through query→compare→maybe-flash.
- **Stateless by choice.** No outstanding-query tracking for MVP; offline boxes
  self-heal on next report. Query tracking / rollout staging is a UI-era
  refinement.
- **url + md5 come from P8's index only.** Never hand-build them here.
- **Endpoint is unauthenticated for MVP** and flagged for the auth story.
