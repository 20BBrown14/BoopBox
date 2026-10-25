# P7 amendment — OTA protocol additions (get_version / flash / version reply)

Amends **P7 (MQTT control plane)** for the server-driven push OTA model (see
`08-ota-static-host-and-manifest.md` for the model, `11-ota-version-policy-and-push.md`
for the policy that uses these). P7 is implemented; this adds a server→box
query/response round-trip and a richer command, without touching the existing
boop→play/error flow.

This is **protocol** work: new message types on the wire and the consumer that
reads the reply. It does not include the push *policy* (when/whom to flash) —
that is P11.

## Why P7 and not P8

The current contract (P3/P7) is boop→play/error (box-initiated) plus a
fire-and-forget `cmd` (server→box, no reply). The OTA model needs a
**request/response**: the server asks a box its firmware version and acts on the
answer. That is a new shape in the MQTT contract, so it belongs with the control
plane, not the static host.

## Current state these additions build on

- `app/models.py` — `Cmd(BaseModel)` is `{ v, cmd: CmdName }`; `CmdName` is a
  `StrEnum` with a single member `check_update`. Outbound models default `v` to
  `PROTOCOL_VERSION`.
- `app/mqtt/publish.py` — `publish_cmd(client, target, cmd)` publishes a `Cmd` to
  `boopbox/<id>/cmd` or `boopbox/all/cmd` (`BROADCAST = "all"`). Topic builders
  are centralized here.
- `app/mqtt/service.py` — `MqttService` subscribes `boopbox/+/boop` only, and
  dispatches each boop through `build_response`. `send_cmd(target, cmd)` publishes
  a `Cmd` via the live client (raises if disconnected). `self.client` is the
  connected client while up.
- `app/db/devices.py` — `update_last_seen(device_id, firmware_version=None)`
  already accepts a firmware version, but **nothing currently passes one**: the
  `Boop` model (`{v, id, slug, uid, ts}`) carries no firmware field, so
  `devices.firmware_version` is never populated today. This gap is why the OTA
  model queries the box rather than trusting a stored version.

## Additions

### 1. Commands: `get_version` and `flash`

- [ ] Extend `CmdName` with `get_version` and `flash` (keep `check_update` or
      retire it — pin which; `get_version` is the new explicit query).
- [ ] `get_version` uses the existing thin `Cmd` shape (`{v, cmd}`): it asks the
      box to publish its current firmware version on its `/version` topic.
- [ ] `flash` is a **fat** command carrying what ESPHome's
      `ota: http_request.flash` action needs: the bin **url** and its **md5**,
      inline. **Decided:** model it as a **separate `FlashCmd` model**, distinct
      from `Cmd`, so the thin `{v, cmd}` shape stays untouched for `get_version`
      and other thin commands. Shape:

      ```json
      { "v": 1, "cmd": "flash", "url": "/firmware/esp32s3/boopbox-0.2.0.bin", "md5": "<hex>" }
      ```

      - `FlashCmd` defaults `v` to `PROTOCOL_VERSION` and fixes `cmd` to
        `flash` (so the wire payload is self-describing and a consumer can route
        on `cmd` regardless of which model produced it).
      - `url` is the absolute served path from P8's firmware index (leading `/`,
        non-redirecting; mind the ~512-byte buffer).
      - `md5` is the index's md5 (computed from disk bytes).
- [ ] Add a `publish_flash(client, device_id, flash_cmd)` helper (or a generalized
      publisher) in `publish.py` and a matching `MqttService` method, parallel to
      `publish_cmd` / `send_cmd`. `FlashCmd` is per-device only — flashing is
      never broadcast (each box gets the bin for *its* chip), so there is no
      broadcast flash. Keep topic building centralized (`cmd_topic`).

### 2. Box→server version reply (`boopbox/<id>/version`)

- [ ] Define the reply topic: **`boopbox/<id>/version`** (confirmed with the box
      side). The box publishes its running firmware version here, both in reply
      to `get_version` and optionally unsolicited (e.g. on boot).
- [ ] Add a payload model for the reply, carrying `v` (protocol), the firmware
      version string, and the **chip family**. Pin the field names (e.g.
      `firmware` for the version and `chip` for the chip, avoiding collision with
      the protocol `v`). The `chip` value must match P8's chip subfolder keys
      (e.g. `esp32s3`) so P11 can call `index(chip)` directly — a flash targets
      the box's own reported chip, never a server-inferred one. Validate like
      other inbound models; malformed/unsupported-`v` replies are dropped with a
      log (no response).
- [ ] Subscribe the MQTT service to `boopbox/+/version` alongside the boop
      subscription, and route it to a new reply handler (distinct from
      `build_response`, which is boop-only and returns exactly one play/error —
      do not overload it).
- [ ] On a valid reply, stamp `devices.update_last_seen(id, firmware_version=...)`
      off-loop so the DB reflects the last-known version (cache/telemetry; not the
      decision input, but useful for a future UI).
- [ ] The **decision** (compare to target, maybe publish `flash`) is P11. P7
      exposes the parsed reply (device id + version + chip) to that policy; it
      does not itself decide to flash. Pin the seam: either the reply handler
      calls a P11 callback/service on `app.state`, or P11 registers a handler.
      Keep the publish of `flash` behind P11's policy, reusing P7's publish
      helper.

### 3. Topic/subscription bookkeeping

- [ ] The service now subscribes two patterns (`boopbox/+/boop`,
      `boopbox/+/version`). Keep dispatch keyed by topic suffix; reuse the
      existing topic-regex approach (`device_id_from_topic`) generalized to the
      new suffix, or add a sibling matcher. Pin the routing so an unexpected
      suffix is logged and ignored (as boop dispatch already does).
- [ ] Reconnect/subscribe logic must resubscribe both patterns after a broker
      blip (the existing reconnect loop).

## Tests (extend `tests/test_mqtt.py` or a sibling)

- [ ] **flash command shape:** publishing a `flash` emits
      `boopbox/<id>/cmd` with `{cmd: flash, url, md5}`; a thin `get_version` emits
      `{cmd: get_version}` with no url/md5 (per the pinned model rules).
- [ ] **version reply parse + route:** a message on `boopbox/<id>/version` is
      parsed to (device, version, chip) and routed to the reply handler, **not**
      `build_response`; an unsupported-`v` or malformed reply is dropped (no
      publish, logged).
- [ ] **last_seen firmware stamp:** a valid reply stamps
      `devices.firmware_version` off-loop.
- [ ] **no cross-talk:** a `/version` message never produces a play/error; a
      `/boop` never produces a flash.

## Watch-outs

- **Request/response, not fire-and-forget.** `get_version` expects a reply; the
  flash decision is driven by that reply arriving, asynchronously. Keep it
  stateless (P11): react to whatever `/version` messages arrive; do not track
  outstanding queries or timeouts for MVP.
- **Do not overload `build_response`.** It is the boop→one-response contract.
  Version replies get their own handler.
- **Fat command stays under the URL buffer.** `url` + `md5` inline is small, but
  keep `url` an absolute server path (not a long external/redirecting URL).
- **md5 and url come from P8's index**, never hand-built in P7 or P11.
