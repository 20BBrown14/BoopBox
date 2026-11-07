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
Schematic: `hardware/boopbox-proto` (KiCad). Firmware pins are substitutions in `firmware/BoopBox_v0.1.0.yaml`.

| MAX98357A | Feather | Notes |
|---|---|---|
| BCLK | D9 / GPIO9 | |
| LRC | D10 / GPIO10 | |
| DIN | D11 / GPIO11 | |
| VIN | USB (5V) | 1000uF across VIN/GND right at the amp |
| GND | GND | |
| GAIN | GND | GND = 12 dB (floating = 9 dB was too quiet) |
| SD | — | floating = (L+R)/2 mono; GPIO12 reserved for mute/sleep later |

- Power: 5V gives ~2.5W clean into 4Ω (speaker is rated 3W); 3.3V is only ~1.3W. USB pin is dead on battery, so the battery build moves VIN to BAT (3.7–4.2V is in range).
- Speaker outputs are bridge-tied: never connect SPK+ or SPK- to GND (including a scope ground clip).
- Don't drive SD high from a GPIO: a solid 3.3V selects LEFT only. Mute = pull low, play = release (open-drain).
- Volume is capped in firmware (`volume_max`) on top of the hardware gain.

## Status ring (NeoPixel Ring 12, WS2812B)

12-LED addressable ring used as a status indicator. Firmware: `esp32_rmt_led_strip`
light on `${ring_pin}`. Single ring, so DOUT is left unconnected (it only exists
to daisy-chain a second ring/strip).

| Ring | Feather | Notes |
|---|---|---|
| 5V / VCC | USB (5V) | Same rail as the amp. WS2812B needs 5V logic/power. |
| GND | GND | Common ground with the Feather. |
| DIN | A0 / GPIO18 | ~330–470Ω in series on the data line; ~1000µF across 5V/GND. |
| DOUT | — | Unused for one ring; chains to the next ring's DIN if expanded. |

- A0 (GPIO18) drives DIN. Pin is a firmware substitution (`ring_pin`).
- The ESP32-S3 drives 3.3V data into a 5V part. It usually works over short
  leads, but a level shifter (or the series resistor above) is the robust fix.

### Power budget (amp + ring on USB)
Both the amp and the ring hang off the 5V rail, so size the supply for the sum:

| Load | Worst case @5V | Typical |
|---|---|---|
| MAX98357A amp | ~0.5A at full output | well under, music peaks are brief |
| Ring (12× WS2812B) | ~0.72A (all white, full brightness) | ~0.05–0.15A at status brightness |
| Feather + WiFi | ~0.1–0.25A (TX bursts) | — |

- Worst case (full-white ring + loud + WiFi burst) is ~1.4–1.5A. A 500mA
  USB 2.0 port will brown out / reset under that; use a **2A+ supply** (charger
  or powered hub) for amp + ring together. The 1000µF bulk cap at the amp helps
  ride out spikes.
- Firmware caps ring current indirectly: status states run at low brightness and
  the volume readout is momentary. Full white only occurs if the ring is driven
  manually at 100%.

### Battery build (open)
WS2812B wants 5V, but the battery build runs off BAT (3.7–4.2V) with the USB pin
dead. The ring (and ideally the amp) then needs a **5V boost converter** sized for
the combined current above. This is an unresolved power-path decision, not a
firmware one — flagged here so it isn't lost.

### Bring-up status (2026-10-17)
- First sound confirmed: Feather + MAX98357A + 4Ω speaker on USB power, streaming over Wi-Fi from a local HTTP server. The start of playback isn't clipped (a 3-beep test file plays all three beeps).
- Plays: WAV (mono and stereo) and stereo MP3.
- **Known issue: mono MP3 doesn't play** on ESPHome 2026.6.5. The decoder reads the header, then the pipeline goes back to idle without starting the speaker, and nothing is logged as an error. Matters for audiobooks/podcasts. Workarounds: transcode to stereo on the server, or fix upstream.
- When test-serving from a dev machine, its host firewall must allow the box in (k2so drops inbound by default).

## UI: capacitive buttons, LED ring, power switch (planning, 2026-11-07)
Direction: capacitive touch buttons (no moving parts, less 3D modelling), an LED ring for visual output, a short click sound as touch feedback, and a physical power switch.

### Pin plan
| Function | Feather | GPIO | Notes |
|---|---|---|---|
| Vol − (touch) | D5 | 5 | T5 |
| Play/Pause (touch) | D6 | 6 | T6 |
| Vol + (touch) | A4 | 14 | T14 |
| Spare touch | A5 | 8 | T8 |
| LED ring data | A0 | 18 | not a touch pin; through a 74AHCT125 level shifter (3.3V → 5V) |

- Touch-capable pins on the S3 are GPIO1–14. 3/4 (I2C), 9–11 (I2S) and 12 (amp SD) are already taken. 13 is the red LED, so avoid it. 1 and 2 aren't broken out on this Feather.
- Three buttons fit on native touch, so no MPR121 is needed. If more controls are added later, the MPR121 (STEMMA QT) is the fallback.

### Touch wiring
- Pad (copper tape for prototyping) → short wire → **510 Ω series resistor next to the GPIO** → touch pin. No pull-ups, and don't connect the pad to ground.
- Espressif guidance (touch sensor design note): round pads 8–15 mm (12 mm typical; bigger for thicker overlays). More than 5 mm between buttons. Plastic overlay ≤ 3 mm with no air gap between pad and overlay. Nothing conductive or metal-flake. Leads as short as possible (< 300 mm). Keep away from I2C/I2S/PWM, the LED data line (≥ 4 mm) and RF (the NFC antenna).
- ESPHome `esp32_touch`: on the S3, values go **up** when touched. Use `setup_mode: true` to log raw values and set each threshold between the idle and touched readings. For S2/S3 the docs use `measurement_duration: 0.25ms` and `sleep_duration: 0.5ms`.

### LED ring
- NeoPixel ring on 5V, with a 1000 µF cap across its power and a 330–470 Ω resistor on the data line.
- Cap brightness in firmware: full white can draw about 1 A from a 16-LED ring, and the ring shares USB 5V with the amp. NeoPixels draw about 1 mA per LED even when dark.

### Power switch
- **EN only kills the 3.3V regulator.** The amp (VIN from USB/BAT) and the LED ring stay powered. That's fine for the prototype. The battery build needs the switch to cut the battery, or to drive a load switch that also cuts the amp and ring.

### Parts ordered (2026-11-07)
- Digi-Key: NeoPixel ring, 74AHCT125, 1000 µF caps, 330–470 Ω resistors, SPDT slide switches, Adafruit 2011 LiPo (3.7 V 2 Ah, JST-PH), bypass caps.
- Amazon: copper foil tape (conductive adhesive), KWS-2303C USB-C power meter.
- Skipped: the STEMMA QT cable (the PN532 is wired directly).
- Still need: 510 Ω resistors for the touch pads, if not already in stock.

### Open items
- Power switch design for the battery build (see above).
- LED ring size and placement. If it goes around the NFC tap zone, check read range with the ring mounted.
- Touch pad placement: away from the tap zone, at a panel thickness that works.
- Click sound: an embedded WAV in flash, played over the music (announcement pipeline, ducking).
- Tests: touch calibration on USB vs battery, with the PN532 polling and audio playing. NFC range with pads and ring mounted. USB current (KWS meter). Reliability of the level-shifted LED data. Whether the KWS meter passes USB data. Battery fit in the enclosure.

### References
- [Espressif touch sensor design guide](https://github.com/espressif/esp-iot-solution/blob/release/v1.0/documents/touch_pad_solution/touch_sensor_design_en.md)
- [ESP32-S3 hardware design guidelines (touch section)](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/esp-hardware-design-guidelines-en-master-esp32s3.pdf)
- [ESP-IDF touch sensor API (ESP32-S3)](https://docs.espressif.com/projects/esp-idf/en/v5.0.7/esp32s3/api-reference/peripherals/touch_pad.html)
- [ESPHome esp32_touch](https://esphome.io/components/binary_sensor/esp32_touch/)
- [Adafruit Feather ESP32-S3 pinouts](https://learn.adafruit.com/adafruit-esp32-s3-feather/pinouts)

## UI plan (2026-11-07)
- **Inputs:** 3 capacitive touch buttons, using the ESP32-S3's native touch peripheral (no MPR121 needed for 3 buttons). Chosen for no moving parts and less 3D modelling.
- **Feedback:** short click sound on each press, stored in flash and played via the media player's announcement pipeline so it ducks over music instead of stopping it. Plus an LED ring for visual output (e.g. show the volume level briefly after vol± presses).
- **Power:** physical power switch.

### Pin plan
| Function | Feather | GPIO | Notes |
|---|---|---|---|
| Touch: vol+ | D5 | GPIO5 | touch ch 5 |
| Touch: vol− | D6 | GPIO6 | touch ch 6 |
| Touch: play/pause | A4 | GPIO14 | touch ch 14 |
| Touch: spare | A5 | GPIO8 | touch ch 8 |
| LED ring data | A0 | GPIO18 | not a touch pin; via 74AHCT125 to 5V |

Avoid GPIO13 (red LED on it). GPIO3/4 (I2C), 7 (I2C power) and 9–12 (I2S + amp SD) are already taken.

### Parts ordered (2026-11-07)
- NeoPixel ring, 74AHCT125 level shifter, 1000 µF cap + 330–470 Ω series resistor for the ring
- SPDT slide switches (power)
- Adafruit 2011 LiPo, 3.7 V 2000 mAh (JST-PH). Check that it fits the enclosure. The Feather charges it slowly.
- KWS-2303C USB-C inline power meter (Amazon). Reads whole-box draw on USB only; too coarse for sleep current. Data passthrough unverified.
- Copper foil tape with conductive adhesive (Amazon) for prototype pads
- Skipped the STEMMA QT → female-socket cable; PN532 stays hand-wired.

### Capacitive touch design rules
From the Espressif touch sensor design note (written for the original ESP32, but the electrode/layout rules apply to the S3 too):
- **Electrode:** round is best, 8–15 mm (12 mm typical); bigger for thicker overlays. More than 5 mm between buttons.
- **Overlay:** at most 3 mm of plastic, no air gap between pad and overlay (stick the tape directly to the wall). Dielectric 2–8 is fine (acrylic ≈2.8, PC ≈3). No metallic paints or metal/carbon-filled filament.
- **Trace:** keep it short (at most 300 mm absolute; shorter is better). Put a 510 Ω series resistor (range 470 Ω–2 kΩ) within ~1 mm of the touch pin.
- **Ground:** use hatched ground (not solid) around pads, at least 1 mm away from them; keep solid ground at least 10 mm away.
- **Neighbours:** keep LED lines at least 4 mm from touch traces. Cross I2C/SPI at right angles. Keep traces away from RF antennas (Wi-Fi and the PN532 antenna).
- **Noise:** Wi-Fi TX adds noise, so calibrate thresholds with Wi-Fi up. Targets: sensitivity above 3%, SNR above 5:1. Water and drool cause false triggers: debounce, and consider ESPHome's `waterproof_guard_ring` option.

### ESPHome touch config (S3)
On S2/S3 the raw value **rises** on touch. The default 8 ms measurement is too long for the S3.

**`threshold` is a delta, not an absolute value** (ESPHome 2026.10, checked in `esp32_touch.cpp`). On S2/S3 a touch is detected in hardware when `smooth − benchmark > threshold`. The hardware's `benchmark` tracks the untouched baseline on its own, from boot and through drift, so baseline calibration is already handled. `threshold` is only written to the hardware when the channel is created. Calling `set_threshold()` at runtime has no effect without recreating the channel. Pick it from the `difference=` values that `setup_mode` logs, at roughly 50–70% of the touched difference.
```yaml
esp32_touch:
  setup_mode: true            # log raw values to pick thresholds; set false after
  measurement_duration: 0.25ms
  sleep_duration: 0.5ms
binary_sensor:
  - platform: esp32_touch
    name: "Play/Pause"
    pin: GPIO14
    threshold: 1000           # placeholder delta: ~50-70% of the touched `difference` from setup_mode
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
With threshold 5000, play/pause latched ON while music played with no finger on it. When the music stopped, play/pause dropped to OFF and vol down latched ON. So the amp or speaker is shifting the untouched readings by more than 5000. The baseline adapts while the music plays, and stopping it is a step change. The pad's baseline stops updating while it reads as touched, so a shift past the threshold stays latched.
Suspects: supply ripple or ground bounce from the class-D amp on the shared USB 5V (the Espressif note says to power the ESP from a regulator not shared with high-current loads), or the amp's switching outputs and speaker wires coupling into the bare touch leads.
Mitigations to try: route touch leads away from the amp and speaker wires; twist the speaker pair; make sure the 1000 µF cap is at the amp VIN; enable the S3 hardware denoise channel (`denoise_grade` / `denoise_cap_level`), which is designed to reject supply noise; raise the threshold (a touch on bare metal is 150k+).

### Open items / to test
- Power switch design: the EN pin only cuts 3.3 V; the amp and ring stay on USB/BAT. The battery build needs a switch in the battery line or a load switch.
- Ring size (12 vs 16) and placement. If it goes around the tap zone, check NFC read range with it mounted.
- Pad placement away from the NFC tap zone; check read range with pads mounted.
- Touch calibration on USB vs battery, with the PN532 polling and audio playing.
- USB current budget: LED brightness cap (`max_brightness`) plus amp peaks.
- Click-sound clip size vs 4 MB flash.

### References
- Espressif touch sensor design note: https://github.com/espressif/esp-iot-solution/blob/release/v1.0/documents/touch_pad_solution/touch_sensor_design_en.md
- ESP-IDF touch sensor API (ESP32-S3): https://docs.espressif.com/projects/esp-idf/en/v5.4.1/esp32s3/api-reference/peripherals/touch_pad.html
- ESPHome esp32_touch: https://esphome.io/components/binary_sensor/esp32_touch/
- Adafruit ESP32-S3 Feather guide: https://learn.adafruit.com/adafruit-esp32-s3-feather (its pinouts page describes the 8 MB/no-PSRAM board; check its mapping against the table below)
- Pin → GPIO table for the 4 MB/2 MB board: https://www.espboards.dev/esp32/adafruit-feather-esp32s3/
