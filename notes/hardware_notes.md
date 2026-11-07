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
| GAIN | — | floating = 9 dB |
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
