# BoopBox — Hardware Notes

## Prototype shopping list
- [Adafruit Feather ESP32-S3, 4MB flash / 2MB PSRAM](https://www.digikey.com/en/products/detail/adafruit-industries-llc/5477/16583982)
  - [Datasheet](https://cdn-shop.adafruit.com/product-files/5426/esp32-s3_datasheet_en.pdf)
- [MAX98357A I2S Class-D mono amp](https://www.adafruit.com/product/3006) (replaces the PCM5102A DAC + MAX98306 amp pair)
  - [Guide, pinouts and downloads](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp)
- [4Ω/3W speaker.](https://www.digikey.com/en/products/detail/pui-audio-inc/AS07104PO-LW152-WR-R/4835137)
  - [Datasheet](https://puiaudio.com/file/specs-AS07104PO-LW152-WR-R.pdf)
- [PN532 NFC reader](https://www.amazon.com/HiLetgo-Communication-Arduino-Raspberry-Android/dp/B0H7TL6W1W?crid=3DEH1BS8TXRHD&dib=eyJ2IjoiMSJ9.UZ7hGc1saDgWsDy_9m3URYrP1jRUDgtu-frL27SLL4Il0M8FJ82NSYWpzSseN1zqy5rP59O_tCfNBl-d6AL-s8LIwztGlBF09WLRN3230Rs4P-MsxrCJB1sXvMxhEmtpIAgRRpKuPcrnRZCq4VFClGfjpeaoLY0JERxmGuOsufurwJfqmT8QDPfi5HUgHs6xF7HLxuQeotBbmMo5MBF6SNdPhdNwlpJ8glzWu57H4OuTVZttmEJKZG8LyhokwQnRK7s-lTuSYCAwiqYfGYB4N_A7HvXPoC0My2e35X-t6rA.ZLZeH_6BRpw1K6xrUx115UoA36_i4-eqtNEqu1zA1h0&dib_tag=se&keywords=pn532%2Bnfc%2Breader&qid=1791430985&s=industrial&sprefix=pn532%2Bnfc%2Bread%2Cindustrial%2C132&sr=1-3&th=1) (DIP switch set to I2C mode.)
  - [Datasheet/Details](https://www.elechouse.com/elechouse/images/product/PN532_module_V3/PN532_%20Manual_V3.pdf)

## Audio (MAX98357A)
Schematic: `hardware/boopbox-proto` (KiCad). Firmware pins are substitutions in `firmware/BoopBox_v0.3.3.yaml`.

| MAX98357A | Feather | Notes |
|---|---|---|
| BCLK | RX / GPIO38 | Moved from D9 on 2026-11-14 (see "Finding: amp I2S next to D5/D6") |
| LRC | TX / GPIO39 | Was D10 |
| DIN | MI / GPIO37 | Was D11 |
| VIN | BAT (3.7–4.2V) | 1000uF across VIN/GND right at the amp. Was USB 5V; moved to BAT 2026-11-10 for battery operation |
| GND | GND | |
| GAIN | GND | GND = 12 dB (floating = 9 dB was too quiet) |
| SD | — | floating = (L+R)/2 mono; GPIO12 reserved for mute/sleep later |

- Power: 5V gives ~2.5W clean into 4Ω (speaker is rated 3W); 3.3V is only ~1.3W. USB pin is dead on battery, so the battery build moves VIN to BAT (3.7–4.2V is in range).
- Speaker outputs are bridge-tied: never connect SPK+ or SPK- to GND (including a scope ground clip).
- Don't drive SD high from a GPIO: a solid 3.3V selects LEFT only. Mute = pull low, play = release (open-drain).
- Volume is capped in firmware (`volume_max`) on top of the hardware gain.

## Status ring (NeoPixel Ring 12, WS2812B)

12-LED addressable ring used as a status indicator. Firmware: `esp32_rmt_led_strip`
light on `${led_ring_pin}`. Single ring, so DOUT is left unconnected (it only exists
to daisy-chain a second ring/strip).

> **The ring must be powered from BAT, not USB.** The Feather's USB pin is dead
> on battery, so a ring on USB goes dark as soon as USB-C is unplugged. See
> "Battery build" below for why BAT direct was chosen over a boost converter.

| Ring | Feather | Notes |
|---|---|---|
| VCC | **BAT** (3.7–4.2V) | Not USB. Same rail as the amp. ~1000µF across VCC/GND at the ring. A P-channel MOSFET high-side switch is planned (see "Battery build"). |
| GND | GND | Common ground with the Feather. |
| DIN | A0 / GPIO18 | ~330–470Ω in series on the data line. No level shifter needed on BAT. |
| DOUT | — | Unused for one ring; chains to the next ring's DIN if expanded. |

- A0 (GPIO18) drives DIN. Pin is a firmware substitution (`led_ring_pin`).
- With VCC at 3.7–4.2V, the 3.3V data line meets the WS2812B logic-high level
  (0.7 × VDD ≤ 2.94V), so no level shifter is needed. A level shifter (74AHCT125)
  is only needed if the ring is ever moved to a 5V rail.
- WS2812B is specified for 3.5–5.3V, so BAT is slightly out of spec at the low
  end: colors dim and shift toward about 3.5V. Cap brightness in firmware.

### Power budget (amp + ring on BAT)
The amp and the ring both hang off BAT. On battery they draw from the cell
(rated about 2 A continuous). On USB they draw through the cell and the Feather's
charger. Size for the sum:

| Load | Worst case | Typical |
|---|---|---|
| MAX98357A amp | ~0.5A at full output | well under, music peaks are brief |
| Ring (12× WS2812B) | ~0.72A (all white, full brightness) | ~0.05–0.15A at status brightness |
| Feather + WiFi | ~0.1–0.25A (TX bursts) | — |

- Worst case (full-white ring + loud + WiFi burst) is ~1.4–1.5A, inside the
  cell's ~2 A rating. With the ring brightness capped (about 0.22 A at 30%), it's
  well under. The 1000µF bulk cap at the amp helps ride out spikes.
- On USB, the charger supplies part of the BAT load and the cell covers peaks,
  so loud playback slows charging. Use a 2A+ USB supply.
- Firmware caps ring current indirectly: status states run at low brightness and
  the volume readout is momentary. Full white only occurs if the ring is driven
  manually at 100%.

### Battery build (open)
WS2812B wants 5V, but the battery build runs off BAT (3.7–4.2V) with the USB pin
dead. This is a power-path decision, not a firmware one.

**First unplug test (2026-11-10):**
- With music playing, USB-C was unplugged and the box ran on the Adafruit 2011 LiPo.
- The ESP32 stayed up, and the player still reported playing.
- There was **no sound**: amp VIN is on USB.
- The **PN532's LED went out** and tag reads failed in the log. Its VCC was on USB too.
- The ring is on USB as well, so it loses power the same way.

**Battery test after rewiring (2026-11-10): passed.**
- Amp VIN moved to **BAT** and PN532 VCC moved to **3V**.
- On battery alone, a full NFC read and music playback both worked.
- Still open: the ring (boost converter) and how much quieter the amp is on BAT.

**Plan:**

| Part | Battery power | New parts |
|---|---|---|
| Amp (MAX98357A) | VIN from USB → **BAT** (done). It runs on 2.5–5.5V, at about 1.5–2 W instead of 2.5 W at 5V. | None |
| PN532 | VCC → Feather **3V** (done). The module takes 3.3V or 5V. | None |
| LED ring | VCC → **BAT** (done; works well enough on 2026-11-11), switched by a P-channel MOSFET (planned, see below) | AO3401, 2N7000, resistors |
- With USB plugged in, the amp on BAT draws through the cell and the Feather's charger. That's fine for the prototype, but loud playback slows charging.

**Protection:**
- The Adafruit 2011 cell (3.7 V, 2 Ah, JST-PH) has a built-in protection circuit for over-discharge, overcurrent and short circuit.
- Its connector polarity matches the Feather, so no extra protection is needed.
- It's rated for about 1C (2 A continuous). The amp (about 0.7 A peak) plus a ring at capped brightness fits under that.
- The Feather charger stops at 4.2V. Don't add a second charger.
- Optional firmware low-battery shutdown: the MAX17048 fuel gauge is now in `BoopBox_v0.3.3.yaml`. Stopping audio and going to deep sleep below about 3.4V or 5% is gentler on the cell than the protection circuit's hard cutoff.

**LED ring power: BAT direct + MOSFET switch (decision 2026-11-11):**
- The ring runs straight off BAT, with no boost converter. On 2026-11-11 it worked well enough for now.
- Brightness will be capped in firmware (full white is far too bright anyway). At a 30% cap, 12 LEDs draw about 0.22 A worst case, compared with about 0.72 A at full.
- **Downsides of BAT direct:**
  - WS2812B is specified for 3.5–5.3V. Toward about 3.5V, blue and white dim and colors shift. Below that, LEDs can glitch. The low-battery shutdown at about 3.4V keeps the box mostly out of that range.
  - It's out of spec. It works on this ring, but another batch may behave differently.
  - Unswitched, the ring draws about 1 mA per LED when dark (about 12 mA). That empties the 2 Ah cell in about a week while idle, and it would keep draining the cell to the protection cutoff after a low-battery deep sleep. The MOSFET switch fixes this.
- **Data line:** with VCC at 3.7–4.2V, the 3.3V data line meets the WS2812B logic-high level (0.7 × VDD ≤ 2.94V), so the 74AHCT125 level shifter isn't needed in this setup.

**High-side switch:**
- BAT → AO3401 (P-channel MOSFET) source. The MOSFET's drain → ring VCC, with the 1000 µF cap on the ring side.
- Gate → 100 kΩ pull-up to BAT, so the ring is **off** by default.
- Gate → 2N7000 drain (or a small NPN collector). Its source → GND. Its gate ← GPIO (to be chosen), optionally through 10 kΩ, with a pull-down so it stays off during boot.
- GPIO high: the 2N7000 pulls the gate low and the ring is on. GPIO low: the gate sits at BAT and the ring is off.
- **Don't drive the gate straight from a GPIO.** The source sits at up to 4.2V and a GPIO set high only reaches 3.3V, which leaves V_GS at about −0.9V. That's near the AO3401 threshold, so it may not turn fully off.
- Pick a P-channel MOSFET rated to turn fully on at a gate voltage of 2.5V or lower (the AO3401 qualifies), so it stays fully on as the cell drains.
- Parts cost about $0.50.

**Expected losses:**

| | 30% cap (0.22 A) | 100% (0.72 A) |
|---|---|---|
| MOSFET drop (about 60 mΩ) | about 13 mV | about 43 mV |
| Power lost | about 3 mW (about 0.3%) | about 31 mW (about 1%) |
| Pull-up while on | about 40 µA | about 40 µA |
| Off | µA leakage | µA leakage |

- For comparison, a boost converter would lose about 10–15% of the ring's power, roughly 100–150 mW at a 30% cap.

**Fallback: 5V boost converter** (if BAT direct proves too dim or glitchy):
- Use it for the ring only. Keep the amp off it, because amp plus ring through the boost would draw more than 2 A from the cell at low charge.
- **Wants:** fixed 5V at 0.5 A or more (enough at capped brightness), works down to about 3.0V, an EN pin with true load disconnect, and low quiescent current.
- **Avoid:** MT3608 and other adjustable modules, and boards that charge the battery (the Feather already charges it).
- **Candidates:**
  - Adafruit PowerBoost 1000 Basic (#2030, about $15). It's based on the TPS61030. EN is pulled up to VBAT, so drive it through an N-channel MOSFET, never straight from a GPIO.
  - A generic Amazon 5V boost board (about $0.80 each in a 10-pack). It has no off switch, so pair it with the high-side switch above.

### Bring-up status (2026-10-17)
- First sound confirmed: Feather + MAX98357A + 4Ω speaker on USB power, streaming over Wi-Fi from a local HTTP server. The start of playback isn't clipped (a 3-beep test file plays all three beeps).
- Plays: WAV (mono and stereo) and stereo MP3.
- **Known issue: mono MP3 doesn't play** on ESPHome 2026.6.5. The decoder reads the header, then the pipeline goes back to idle without starting the speaker, and nothing is logged as an error. Matters for audiobooks/podcasts. Workarounds: transcode to stereo on the server, or fix upstream.
- When test-serving from a dev machine, its host firewall must allow the box in (k2so drops inbound by default).

## UI: capacitive buttons, LED ring, power switch (2026-11-07)
Direction: capacitive touch buttons (no moving parts, less 3D modelling), an LED ring for visual output, a short click sound as touch feedback, and a physical power switch.

### Status (2026-11-14)
- **Tuning is parked** until the pads and leads have a proper layout. The spare breadboard is too small: the 470 Ω resistors had to go right next to the amp, and playback still shifts the D5/D6 readings (see "New breadboard" below).
- All three pads detect touches and drive the player (`firmware/BoopBox_v0.3.3.yaml`). Thresholds since 2026-11-14: Vol Down 4000, Vol Up 2000, Play/Pause 2000, with `delayed_off: 150ms`.
- The amp's I2S moved to RX/TX/MI (GPIO38/39/37). Every box must be rewired to match.
- **Touch Setup Mode** is now a web UI switch (Device group), so tuning doesn't need a reflash. The procedure is in [touch_tuning.md](touch_tuning.md).
- Touch Vol± presses now show the volume on the LED ring (`show_volume`), which shows whether a press registered.
- **Known issue:** with the amp playing, pads can still latch ON or sit near the threshold. Fix the lead routing before setting thresholds.

### Pin plan
| Function | Feather | GPIO | Notes |
|---|---|---|---|
| Vol + (touch) | D5 | 5 | T5 |
| Vol − (touch) | D6 | 6 | T6 |
| Play/Pause (touch) | A4 | 14 | T14 |
| Spare touch | A5 | 8 | T8. Clean during playback in the 2026-11-11 test. |
| LED ring data | A0 | 18 | not a touch pin. Ring VCC is on BAT, so no level shifter is needed. |
| Amp BCLK / LRC / DIN | RX / TX / MI | 38 / 39 / 37 | not touch pins. Moved off D9–D11 on 2026-11-14. |

- Touch-capable pins on the S3 are GPIO1–14. 3/4 (I2C), 7 (I2C power) and 12 (amp SD) are already taken. 9–11 are free since the I2S move. 13 is the red LED, so avoid it. 1 and 2 aren't broken out on this Feather.
- Three buttons fit on native touch, so no MPR121 is needed. If more controls are added later, the MPR121 (STEMMA QT) is the fallback.

### Touch wiring and pad design
- **Decision (2026-11-10):**
  - Pads are **round copper tape, about 2 cm in diameter**.
  - Each pad is bonded directly behind a **1 mm thick section** of the PETG wall. The rest of the enclosure can be thicker, with the wall thinned to 1 mm only at the buttons.
  - Basis: 1 mm gave about 15–18% sensitivity, far above Espressif's 3% minimum. 5 mm sat at about 3.5%, right at the limit (see the panel test below).
  - Shape: the circle beat the square, which agrees with Espressif's "round is best", but that comparison wasn't controlled.
- Pad (copper tape for prototyping) → short wire → **510 Ω series resistor within ~1 mm of the GPIO** (470 Ω–2 kΩ range) → touch pin. No pull-ups, and don't connect the pad to ground.
- Rules from the Espressif touch sensor design note (written for the original ESP32, but the electrode and layout rules apply to the S3 too):
  - **Electrode:** round is best, 8–15 mm (12 mm typical), bigger for thicker overlays. More than 5 mm between buttons.
  - **Overlay:** at most 3 mm of plastic, with no air gap between pad and overlay (stick the tape directly to the wall). A dielectric constant of 2–8 is fine (acrylic ≈2.8, PC ≈3). No metallic paints and no metal- or carbon-filled filament.
  - **Trace:** as short as possible (300 mm absolute max).
  - **Ground:** hatched, not solid, at least 1 mm from pads. Keep solid ground at least 10 mm away.
  - **Neighbours:** keep the LED data line at least 4 mm away. Cross I2C/SPI at right angles. Keep clear of RF: Wi-Fi and the PN532 antenna (this also protects NFC read range).
  - **Noise:** Wi-Fi TX adds noise, so calibrate with Wi-Fi up. Targets: sensitivity above 3%, SNR above 5:1. Water and drool cause false triggers, so debounce and consider ESPHome's `waterproof_guard_ring`.

### ESPHome touch config (S3)
- On S2/S3 the raw value **rises** on touch. The default 8 ms measurement is too long for the S3: use `measurement_duration: 0.25ms` and `sleep_duration: 0.5ms`.
- **`threshold` is a delta, not an absolute value** (ESPHome 2026.10, checked in `esp32_touch.cpp`):
  - On S2/S3, a touch is detected in hardware when `smooth − benchmark > threshold`.
  - The hardware's `benchmark` tracks the untouched baseline by itself, from boot and through drift, so there's no need for boot calibration.
  - The benchmark **freezes while a pad reads as touched**.
  - `threshold` is only written when the channel is created, so a runtime `set_threshold()` has no effect.
- Calibrate with `setup_mode: true`: it logs `difference=` for each pad about 4×/s. Set each threshold to about 50–70% of the touched difference, then turn setup mode off.
- To condense the logs, pipe `esphome logs` through a one-line-per-second summary of the max `difference` per pad. (The script used on 2026-11-07 was a throwaway; recreate it if needed.)

```yaml
esp32_touch:
  setup_mode: true            # log differences to pick thresholds; set false after
  measurement_duration: 0.25ms
  sleep_duration: 0.5ms
binary_sensor:
  - platform: esp32_touch
    name: "Touch Play Pause"  # no "/" in names: ESPHome reserves it (error from 2027.7)
    pin: GPIO14
    threshold: 5000           # delta: ~50-70% of the touched `difference`
```

### Breadboard calibration (2026-11-07)
Bare metal jumper tips, USB power, Wi-Fi up, `setup_mode` differences:
| Pad | Idle | Hover / nearby hand | Direct touch |
|---|---|---|---|
| Vol Up (GPIO5) | about ±180 | 800–1900 (sustained) | 148k–221k |
| Vol Down (GPIO6) | about ±160 | — | 365k–418k |
| Play Pause (GPIO14) | about ±180 | — | 320k–402k |

- Threshold set to 5000 on all three: well above idle and hover, far below a touch.
- Skin on bare metal is a near-direct contact, so these deltas are roughly 100× what a touch through a 2–3 mm wall will give. **Recalibrate behind the real panel.**
- Vol Up picked up 800–1000 while play/pause was being touched, from the hand or lead being nearby. Keep leads apart.
- After a long press, `difference` can swing negative on release (the benchmark lags). This is harmless for detection.

### Finding: audio playback shifts the touch readings (2026-11-07)
- **What happened:** with threshold 5000, play/pause latched ON while music played, with no finger on it. When the music stopped, play/pause dropped to OFF and vol down latched ON.
- **What that means:**
  - The amp/speaker shifts the untouched readings by more than 5000.
  - The baseline adapts while music plays, so stopping the music is a step change.
  - The benchmark freezes once a pad reads as touched, so any shift past the threshold stays latched.
- **Suspects:**
  - Supply ripple or ground bounce from the class-D amp on the shared USB 5V. The Espressif note says to power the ESP from a regulator not shared with high-current loads.
  - The amp's switching outputs and speaker wires coupling into the bare touch leads.
  - The PN532's I2C wires and antenna near the leads are a lesser concern. They would show up as brief spikes every 500 ms (the poll interval), not a lasting shift.
- **Mitigations to try:**
  - Route touch leads away from the amp, speaker and PN532, crossing other wires at right angles.
  - Twist the speaker pair. It's bridge-tied: never ground either wire.
  - Confirm the 1000 µF cap is right at the amp VIN.
  - Enable the S3 hardware denoise channel (`denoise_grade` / `denoise_cap_level`), which is built to reject shared supply noise.
  - Raise the threshold.
- **Next measurement:** with real pads, run `setup_mode` untouched with music playing vs stopped to size the shift.

### Panel test: copper pad behind 1 mm PETG (2026-11-10)
**Setup:**
- Feather still on the breadboard. A 12 cm lead goes from the breadboard to a 2 cm square of copper tape stuck to the back of a 1 mm PETG sample.
- Firmware: `BoopBox_v0.1.0.yaml` with `setup_mode: true` and threshold 5000.
- No audio playback appeared in the log.

**Method:** capture 45 s of `setup_mode` logs. Wait about 10 s, then finger on for about 5 s, off for 10 s, and on for 5 s. Summarize the max and min `difference` per second.

**Play Pause (GPIO14):**

| State | `difference` |
|---|---|
| Idle | mostly within ±150, with occasional spikes up to about 630 |
| Touch 1 (about 5 s) | held at 11k–13k (3k–11k during the first second) |
| Touch 2 (about 5 s) | held at 11k–15k |
| Release | swings negative briefly (down to −5.3k), then back to idle within about 1 s |

**Observations:**
- Through 1 mm PETG, a touch is about 3% of the raw value (about 120k), compared with 150k–400k on bare jumper tips. This matches the earlier note that a touch through the panel gives a much smaller difference.
- The benchmark froze during both touches. Corrected later: a frozen benchmark does **not** prove detection, because Vol Up's benchmark also froze on a 4.5k touch, below the 5000 threshold. The binary sensor's ON/OFF changes don't appear in the serial log, so check the web UI to confirm detection.
- Between touches the idle baseline drifted on its own from about 118k to 120k. The benchmark followed it without a false trigger.
- Suggested threshold: about 7000, which is about 55% of the held touch and more than 10× the largest idle spike.

**Vol Down (GPIO6):**
- Same setup, except the pad is a 2 cm diameter circle of copper tape.

| State | `difference` |
|---|---|
| Idle | within about ±150 |
| Touch 1 (about 5 s) | held at 17k–18k |
| Touch 2 (about 5 s) | held at about 21k |
| Release | dipped once to −3.5k, then back to idle immediately |

- The circle read about 40–75% higher than the square pad on Play Pause, with less idle noise, even though the circle has about 20% less area. Threshold 7000 is under half of a touch.
- Caveat: this comparison wasn't controlled. The two pads were on different pins (GPIO14 and GPIO6) with different leads, the finger pressure varied, and each got only one run. Shape alone isn't proven.
- During this run, Vol Up (GPIO5), with nothing touching it, showed a slow idle wobble of about ±400. That is more than the other two pads, but still far below the threshold.

**Vol Up (GPIO5), behind 5 mm PETG:**
- A 2 cm diameter circle of copper tape behind a **solid 5 mm thick** PETG sample. Otherwise the same setup.

| State | `difference` |
|---|---|
| Idle | about −670 to +570, the noisiest of the three pins |
| Touch 1 (about 6 s) | held at 4.3k–5.4k |
| Touch 2 (about 5 s) | held at 3.5k–4.1k |
| Release | back to idle immediately, with no negative swing |

- 5 mm gives about a quarter of the 1 mm touch (about 4k against 17k–21k with the same pad shape). Most of the touch sits **below the 5000 threshold**, so it would mostly not trigger.
- Making 5 mm work would need a threshold of about 2000–2500. That is only about 4× the idle noise on this pin, which is a thin margin. This matches the Espressif guidance of at most 3 mm of overlay.

**Finding: Vol Up latched ON after the pad was swapped.**
- The web UI showed Vol Up stuck ON before this run. The first log line showed value = 114.7k but benchmark = 89.9k, a difference of 24.7k.
- Likely cause: attaching the new pad and lead while the box was running added about 25k of capacitance as a step change. That is past the threshold, so the benchmark froze at the old, lower value and the pad stayed latched.
- **Rule:** swapping or attaching pads on a running box latches them. Reboot after any pad change.
- In this run the latch was cleared by an unplanned reboot (see the next finding).

**Finding: the box reboots after 15 minutes with no API client.**
- The log shows `[api] No clients; rebooting`. `api:` has the default `reboot_timeout` of 15 min.
- Nothing connects through the native API (no Home Assistant), and the web UI doesn't count as a client.
- Unless that changes, the box reboots every 15 min. Consider setting `api: reboot_timeout: 0s`, or dropping `api:` if MQTT and the web UI cover everything.

### Panel test: Vol Up on top-panel-v1 (2026-11-10)
**Setup:**
- First test on a printed enclosure part: **top-panel-v1**, with the Vol Up pad (GPIO5) mounted in it.
- Firmware: `BoopBox_v0.1.0.yaml` with `setup_mode: true` and threshold 5000, flashed for the run and then switched back to `setup_mode: false`.
- Pad size and shape, and the wall thickness at the pad, weren't recorded for this run.

**Method:** about 75 s of `setup_mode` logs. Finger on for about 5 s, off for about 7 s, then on again for about 5 s. Summarize the max and min `difference` per second.

| State | `difference` |
|---|---|
| Idle | about −2.3k to +400 |
| Touch 1 (about 5 s) | held at 9k–13k |
| Off (about 6 s) | about −1.6k to +400 |
| Touch 2 (about 4 s) | held at 12k–23k |
| After (about 50 s) | about −3k to +500 |

- The binary sensor went ON and OFF once for each touch, so threshold 5000 detects both. Each touch is about 2–4× the threshold.
- Idle dips reach about −3k, compared with ±400–670 for Vol Up on the loose samples. A negative swing can't cause a false press, but it's new on this pin.
- Touch 2 read about twice as high as touch 1, probably because of finger pressure.
- Suggested threshold: about 6000–7000, which stays under the 9k low end of touch 1.

**Still to do:**
- Repeat Vol Up behind 1 mm (or 2–3 mm) PETG, for a like-for-like comparison and to find the thickness limit.
- Run an untouched capture with music playing, to check that the audio shift stays well below the threshold.

### Panel test v2: wire-coil pads (2026-11-11)
**Setup:**
- Top panel v2: each button is a small coil of wire, on D5 (Vol Up), D6 (Vol Down) and A4 (Play/Pause). A reference photo from 2026-11-11 is in Harold's photo library.
- Bare wire to the pin, with no series resistor.
- Original board (MAC `…a3:4c`), amp still on D9–D11.
- `BoopBox_v0.1.0.yaml` with `setup_mode: true` and threshold 5000.
- Panel material and thickness: TODO.

**No music:**

| Pad | Raw | Idle | Held touch (about 5 s) |
|---|---|---|---|
| Vol Up (D5) | about 128.5k | −221 to +180 | 6.2k–7.0k |
| Vol Down (D6) | about 131.4k | −137 to +127 | 10.1k–11.9k |
| Play/Pause (A4) | about 136.1k | −131 to +145 | 5.5k–5.9k |

- Each pad fired once, with no crosstalk. A touch is 4–9% of the raw value and SNR is about 25–50:1.
- The held touch is very steady (Play/Pause stayed within about 300), but it's about half of what copper tape gave.
- Threshold 5000 is too close for Play/Pause. Suggested thresholds were about 3400 (Vol Up), 5500 (Vol Down) and 3000 (Play/Pause).

### Finding: amp I2S next to D5/D6 (2026-11-11)
**Music run, same setup.** This reproduced the 2026-11-07 latch.
- At PLAYING, raw readings stepped **down**: D5 by 5.5k and D6 by 9.0k. A4 didn't move.
- At PAUSED they stepped back up. Both Vol Up and Vol Down fired about 1 s later and stayed latched until playback resumed. This happened twice.
- The shift followed the player state, not the audio. Idle noise during playback was lower than without music, and the shift was full size even at low volume.

**D6 moved to A5 (GPIO8):**

| Pad | Shift at PLAYING | Jump at pause | Touch while playing |
|---|---|---|---|
| Vol Down on A5 | −0.85k (was −9.0k on D6) | +0.9k | 14.5k–15.0k |
| Vol Up on D5 | −2.8k (was −5.5k) | +3.2k, under the threshold | 10.0k–11.3k |
| Play/Pause on A4 | none | none | 4.6k–5.2k |

- Likely cause: on the Feather's long header, D6 and D5 sit next to D9 (I2S BCLK), and the I2S clocks start with playback. The header order was taken from memory and wasn't checked against the board.
- Response: move the amp's I2S to RX/TX/MI (GPIO38/39/37), away from all the touch pins. A0–A3 aren't touch-capable, so moving the touch pins wasn't an option.

### New breadboard: amp on RX/TX/MI, 470 Ω resistors (2026-11-14)
**Setup:**
- Spare Feather (MAC `…f2:80`, 192.168.68.175) on a small breadboard, with coil pads on D5, D6 and A4.
- 470 Ω series resistors (no 510 Ω in stock), placed right next to the amp for lack of space.
- Amp on RX/TX/MI. Battery on JST. EN-to-GND power switch.
- The only cap is the 1000 µF at the amp, and there's no resistor on the ring DIN line.

**Idle, no music:**
- Raw readings changed a lot with the new wiring: D5 about 214k, D6 about 199.7k, A4 about 101.7k.
- D6 and A4 were clean (within ±230).
- **D5 has a sawtooth:** it dips to −3.5k to −4.4k about every 5 s and recovers over 2–3 s. The cause is unknown; possibly the ring or a loose resistor contact.

**Music run:**
- At PLAYING, D5 and D6 both stepped **up** by about 3.5k and held there. The benchmark didn't follow over the next minute. A4 didn't move.
- A positive shift sits next to the threshold, so a 1.5k touch is enough to fire. Touches while playing peaked at 6.2k–7.0k.
- Several repeat presses in this run were deliberate re-taps, because there was no press indicator at the time.
- Moving the amp didn't remove the shift; it reversed it. On this board the D5/D6 leads run past the amp and resistors, so the routing is the main suspect.
- Next: a proper layout with leads away from the amp, then run [touch_tuning.md](touch_tuning.md) Runs A and B.

### Touch tuning run (2026-11-14)
Setup: board `…f2:80`; pins D6 (Vol Down), D5 (Vol Up), A4 (Play/Pause); v2 wire-coil pads; panel TODO; **no series resistor** (the 470 Ω parts were removed, because there was only room for them next to the amp); USB with battery; firmware 0.3.3 with the amp on RX/TX/MI. Followed [touch_tuning.md](touch_tuning.md).

| Pad (GPIO) | Raw | Idle noise | Touch delta (held, Run A / Run B) | Playback shift | False presses | Threshold |
|---|---|---|---|---|---|---|
| Vol Down (6) | about 120.0k | −182 to +109 | 7.2k–7.5k / 7.1k–8.2k | −1.4k, followed at pause | none | 4000 |
| Vol Up (5) | about 126.9k | −314 to +150 | 3.6k–4.0k / 4.9k–5.2k | −0.4k | none | 2000 |
| Play/Pause (14) | about 125.6k | −213 to +169 | 3.4k–3.9k / 4.7k–6.7k | none | none | 2000 |

Notes:
- With the old thresholds of 5000, Vol Up and Play didn't fire in Run A, and Vol Up didn't fire in Run B.
- Run A before the coils were reconnected: one 3 s Play/Pause hold fired 9 times, about every 500 ms, with the touch at 4.4k–6.4k against threshold 5000. Short dips on a 500 ms cycle (the PN532 poll or the ring tick) ended each press. Fixed with the lower threshold and `delayed_off: 150ms`, which also covers the "play/pause double-fires" open item. Not yet re-tested.
- The D5 sawtooth (every ~5 s) disappeared once the resistors were out.
- Crosstalk: touching Vol Down raised Vol Up's raw reading by about 1.5k. The baseline followed, so there was no false press.
- Touch strength varies by up to 80% with finger pressure, so the thresholds come from Run A's weaker readings.
- Run A has to start with the player idle. From paused, the Play/Pause touch resumes the music.
- The PN532 failed at boot with `SCL is held LOW` again (after the coils were reconnected), so Run B used a simulated boop.

### LED ring
- NeoPixel ring with VCC on **BAT** (not USB 5V), a 1000 µF cap across its power and a 330–470 Ω resistor on the data line.
- Cap brightness in firmware. Full white draws about 0.72 A from the 12-LED ring, and the ring shares BAT with the amp. NeoPixels draw about 1 mA per LED even when dark.
- Touch vol± presses show the volume on the ring (`show_volume`, added 2026-11-14).

### Feedback sound
- A short WAV embedded in flash (no network latency), played through the media player's announcement pipeline so it ducks over the music instead of stopping it. Keep it tiny: flash is 4 MB.

### Power switch
- **EN only kills the 3.3V regulator.** The amp (VIN from USB/BAT) and the LED ring stay powered. That's fine for the prototype. The battery build needs the switch to cut the battery, or to drive a load switch that also cuts the amp and ring.

### Parts ordered (2026-11-07)
- Digi-Key:
  - NeoPixel ring, 74AHCT125, 1000 µF caps, 330–470 Ω resistors, SPDT slide switches, bypass caps.
  - Adafruit 2011 LiPo (3.7 V 2 Ah, JST-PH). Check that it fits the enclosure. The Feather charges it slowly.
- Amazon:
  - Copper foil tape (conductive adhesive).
  - KWS-2303C USB-C power meter. It reads the whole box's draw on USB only, is too coarse for sleep current, and data passthrough is unverified.
- Skipped: the STEMMA QT cable (the PN532 is wired directly).
- Touch pad resistors: 470 Ω used (no 510 Ω in stock). Anything from 470 Ω to 2 kΩ is fine.

### Open items
- Touch: lay out the pads and leads properly, away from the amp, speaker and BAT. Then run [touch_tuning.md](touch_tuning.md) Runs A and B, on USB and on battery, set per-pad thresholds and try denoise.
- Touch: find the cause of the ~5 s sawtooth on D5 on the new breadboard.
- Rewire Branden's box: amp I2S to RX/TX/MI.
- Touch UX: auto-repeat while vol± is held. Check whether play/pause double-fires (once seen as PLAYING → PAUSED 0.5 s apart). If it does, use `on_click` with min/max length or a longer debounce.
- Power switch design for the battery build (see above).
- LED ring size (12 vs 16) and placement. If it goes around the NFC tap zone, check read range with the ring mounted.
- Touch pad placement: away from the tap zone. The pads go behind 1 mm sections of the wall (decided 2026-11-10). Check NFC read range with pads mounted.
- Click sound clip.
- Other tests: USB current budget (KWS meter: LED cap + amp peaks), reliability of the level-shifted LED data, whether the KWS meter passes USB data, battery fit.

### References
- [Espressif touch sensor design guide](https://github.com/espressif/esp-iot-solution/blob/release/v1.0/documents/touch_pad_solution/touch_sensor_design_en.md)
- [ESP32-S3 hardware design guidelines (touch section)](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/esp-hardware-design-guidelines-en-master-esp32s3.pdf)
- [ESP-IDF touch sensor API (ESP32-S3)](https://docs.espressif.com/projects/esp-idf/en/v5.4.1/esp32s3/api-reference/peripherals/touch_pad.html)
- [ESPHome esp32_touch](https://esphome.io/components/binary_sensor/esp32_touch/)
- [Adafruit Feather ESP32-S3 pinouts](https://learn.adafruit.com/adafruit-esp32-s3-feather/pinouts). This describes the 8 MB/no-PSRAM board, so check it against the table below.
- [Pin → GPIO table for the 4 MB/2 MB board](https://www.espboards.dev/esp32/adafruit-feather-esp32s3/)
