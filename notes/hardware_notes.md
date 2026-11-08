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

## UI: capacitive buttons, LED ring, power switch (2026-11-07)
Direction: capacitive touch buttons (no moving parts, less 3D modelling), an LED ring for visual output, a short click sound as touch feedback, and a physical power switch.

### Status (2026-11-08)
Breadboard touch bring-up is done. All three pads detect touches and drive the player (`firmware/BoopBox_v0.1.0.yaml`, threshold 5000, `setup_mode` off). Tuning is **parked** until there are copper-tape pads on a printed test panel with tidy wiring, because numbers from bare jumper leads don't carry over. **Known issue:** with the current build, pads can latch ON during audio playback (see the finding below) and toggle play or volume on their own.

### Pin plan
| Function | Feather | GPIO | Notes |
|---|---|---|---|
| Vol + (touch) | D5 | 5 | T5 |
| Vol − (touch) | D6 | 6 | T6 |
| Play/Pause (touch) | A4 | 14 | T14 |
| Spare touch | A5 | 8 | T8 |
| LED ring data | A0 | 18 | not a touch pin; through a 74AHCT125 level shifter (3.3V → 5V) |

- Touch-capable pins on the S3 are GPIO1–14. 3/4 (I2C), 7 (I2C power), 9–11 (I2S) and 12 (amp SD) are already taken. 13 is the red LED, so avoid it. 1 and 2 aren't broken out on this Feather.
- Three buttons fit on native touch, so no MPR121 is needed. If more controls are added later, the MPR121 (STEMMA QT) is the fallback.

### Touch wiring and pad design
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

### LED ring
- NeoPixel ring on 5V, with a 1000 µF cap across its power and a 330–470 Ω resistor on the data line.
- Cap brightness in firmware (`max_brightness`): full white can draw about 1 A from a 16-LED ring, and the ring shares USB 5V with the amp. NeoPixels draw about 1 mA per LED even when dark.
- Idea: briefly show the volume level on the ring after vol± presses.

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
- Still need: 510 Ω resistors for the touch pads, if not already in stock.

### Open items
- Touch: recalibrate with real pads behind a printed panel, on USB and on battery, with the PN532 polling and audio playing vs stopped. Then set thresholds and try denoise (see the finding above).
- Touch UX: auto-repeat while vol± is held. Check whether play/pause double-fires (once seen as PLAYING → PAUSED 0.5 s apart). If it does, use `on_click` with min/max length or a longer debounce.
- Power switch design for the battery build (see above).
- LED ring size (12 vs 16) and placement. If it goes around the NFC tap zone, check read range with the ring mounted.
- Touch pad placement: away from the tap zone, at a panel thickness that works. Check NFC read range with pads mounted.
- Click sound clip.
- Other tests: USB current budget (KWS meter: LED cap + amp peaks), reliability of the level-shifted LED data, whether the KWS meter passes USB data, battery fit.

### References
- [Espressif touch sensor design guide](https://github.com/espressif/esp-iot-solution/blob/release/v1.0/documents/touch_pad_solution/touch_sensor_design_en.md)
- [ESP32-S3 hardware design guidelines (touch section)](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/esp-hardware-design-guidelines-en-master-esp32s3.pdf)
- [ESP-IDF touch sensor API (ESP32-S3)](https://docs.espressif.com/projects/esp-idf/en/v5.4.1/esp32s3/api-reference/peripherals/touch_pad.html)
- [ESPHome esp32_touch](https://esphome.io/components/binary_sensor/esp32_touch/)
- [Adafruit Feather ESP32-S3 pinouts](https://learn.adafruit.com/adafruit-esp32-s3-feather/pinouts). This describes the 8 MB/no-PSRAM board, so check it against the table below.
- [Pin → GPIO table for the 4 MB/2 MB board](https://www.espboards.dev/esp32/adafruit-feather-esp32s3/)
