# Battery Life Test

> **DRAFT: not yet run, not yet reviewed.** This is a proposed test design. The
> open questions at the bottom need answers before the first run, and the
> scripts it describes don't exist yet.

## Goal

Measure **hours of continuous playback** on the Adafruit 2011 LiPo (3.7 V, 2 Ah),
from a full charge down to a cutoff, at fixed volume and ring settings. Log
battery voltage and fuel-gauge percentage over the whole run.

A rough estimate is about 250–350 mA average while playing, so expect about 6–8
hours. That's a guess, not a measurement. Measuring it is the point of this test.

## Hardware state under test

The wiring as of 2026-11-11 (see "Battery build" in `hardware_notes.md`):

- Amp (MAX98357A) VIN on **BAT**
- PN532 VCC on **3V**
- LED ring VCC on **BAT** (no boost converter, no MOSFET switch yet)
- Fuel gauge: MAX17048 at I2C 0x36, shown in the web UI as **Battery** (%)
  and **Battery Voltage**, updated every 60 s (`BoopBox_v0.1.0.yaml`)

Record anything that differs on the day of the run.

## Setup

1. Charge fully on USB until the Feather's charge LED goes out.
2. Fix the test conditions and record them:
   - Volume (for example 50%)
   - Ring: off, or a fixed color at the capped brightness
   - Wi-Fi on, PN532 polling as normal (500 ms)
   - Firmware version and build
3. Unplug USB. That's the start of the run.

## Playback load

- Play through the real path (MQTT → server → Jellyfin stream), not a local
  file, so the Wi-Fi load is realistic.
- Keep it playing: whenever the player is idle, the test script sets **Simulate
  Slug** to `boop/all-day` (12 tracks, random pick) and presses **Simulate Tag
  Read**. That's the same publish path as a real tap.
- The BoopBox server must be running for the whole test (see the README; export
  `app-data/.env` so the Jellyfin key loads).

## Logging

The battery sensors are **not** on MQTT (`topic_prefix: null`), so the test
script polls the box's web API from k2so once a minute:

- `GET http://<box>/sensor/Battery`
- `GET http://<box>/sensor/Battery%20Voltage`
- The media player state (playing or idle). Confirm the endpoint before the run.

Each sample goes into a CSV:

```
timestamp,voltage_v,percent,player_state,reboosted
```

`reboosted` marks samples where the script had to restart playback.

## Gotchas

1. **The box reboots every 15 min with no API client.** `api:` uses the
   default `reboot_timeout`. Run `esphome logs` against the box for the whole
   test, which counts as a client and also captures logs for debugging. The
   other option is `api: reboot_timeout: 0s`, which is a firmware change.
2. **Cutoff.** The cell's protection board hard-cuts at about 2.5–3.0 V. Going
   that deep every time wears the cell. Proposed: **stop at 3.3 V**, which loses
   only a few percent of capacity, and record that as the runtime.
3. **Fuel gauge accuracy.** The MAX17048 percentage is unreliable for the first
   few cycles. Treat the **voltage curve as the primary data** and the percentage
   as secondary. This run also helps the gauge learn the cell.
4. **Unattended run.** Keep the box somewhere safe, away from flammables, while
   it runs for hours. Check that the cell doesn't get warm.

## Output

- A CSV of the run.
- A results entry in `hardware_notes.md`:
  - runtime to cutoff
  - voltage at 25/50/75% of runtime
  - the conditions from Setup
  - any reboots or playback gaps
- Optional: a voltage-over-time chart.

## Open questions

- [ ] Test volume, and ring setting (off, or which color and brightness)?
- [ ] Stop at 3.3 V, or run until the protection board cuts out?
- [ ] Keep the test script in the repo (`scripts/battery_test.sh` or `.py`), or
      only in a scratch directory?
- [ ] Repeat runs: once now, then again after the MOSFET switch and
      low-battery shutdown are built?
