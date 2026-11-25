# BoopBox — Wiring

Bench checklist for building or rewiring a box: Feather ESP32-S3 + MAX98357A amp,
PN532 NFC, three touch pads, a NeoPixel Ring 12 and a LiPo. Battery build.

**Which source wins:**
- **GPIO numbers:** the `substitutions:` in `firmware/BoopBox_v0.3.3.yaml`. If
  anything disagrees with them, they win; fix the others.
- **Drawing:** the KiCad schematic in `hardware/boopbox-proto/`.
- **This doc:** the hands-on checklist, plus the gotchas.

Why things are wired this way (the I2S move, BAT instead of USB, touch tuning) is in
[hardware_notes.md](hardware_notes.md).

## Power rails

| Rail | Comes from | Feeds | Notes |
|---|---|---|---|
| BAT (3.7–4.2V) | LiPo on the JST jack (Adafruit 2011, 2 Ah) | Amp VIN, ring VCC | The battery node itself. Live on battery and on USB. |
| 3V (3.3V) | Feather regulator, 500 mA peak | PN532 VCC | Also powers the ESP32-S3 itself, so the budget is shared. |
| USB (5V) | USB-C | Nothing | Dead on battery. Don't hang loads on it. |
| GND | Common | Everything | One common ground rail. |

- Keep a battery connected, even on USB. With no cell, BAT is only fed by the
  charger, so the amp and ring have no proper supply. (Inferred from Adafruit's
  description of BAT. Not tested on the bench.)
- On USB, loads on BAT draw through the battery, and the charger tops it up.
  Loud playback slows charging.

## Amp (MAX98357A)

| Feather | MAX98357A | Signal | Firmware |
|---|---|---|---|
| RX / GPIO38 | BCLK | I2S bit clock | `i2s_bclk_pin` |
| TX / GPIO39 | LRC | I2S word select | `i2s_lrclk_pin` |
| MI / GPIO37 | DIN | I2S data | `i2s_dout_pin` |
| BAT | VIN | Power | |
| GND | GND | Ground | |
| GND | GAIN | Gain = 12 dB | Floating (9 dB) was too quiet. |
| — | SD | Floating = (L+R)/2 mono | GPIO12 is reserved for mute later. |

| Part | Connection | Notes |
|---|---|---|
| C1, 1000µF 10V electrolytic | + to amp VIN, − to amp GND | Right at the amp pins. Mind the polarity. |
| Speaker 4Ω 3W (+) | Amp SPK+ (`+` screw terminal) | |
| Speaker 4Ω 3W (−) | Amp SPK− (`−` screw terminal) | |

## NFC (PN532)

| Feather | PN532 | Firmware |
|---|---|---|
| 3V | VCC | |
| GND | GND | |
| SDA / GPIO3 | SDA | `i2c_sda_pin` |
| SCL / GPIO4 | SCL | `i2c_scl_pin` |

- Set the PN532's DIP switch to **I2C** before powering up.
- The Feather has its own pull-ups on SDA/SCL. They're powered from GPIO7, which the
  firmware drives high at boot. The PN532 board's pull-ups in parallel are fine.

## Touch pads

| Pad | Feather | Firmware |
|---|---|---|
| Vol + | D5 / GPIO5 | `touch_vol_up_pin` |
| Vol − | D6 / GPIO6 | `touch_vol_down_pin` |
| Play/Pause | A4 / GPIO14 | `touch_play_pin` |

- No series resistors in the current build.
- Route the pad leads away from the amp, its I2S lines and the speaker wiring.
  Re-tune with [touch_tuning.md](touch_tuning.md) after any pad or wiring change.

## LED ring (NeoPixel Ring 12)

| Feather / rail | Ring | Notes |
|---|---|---|
| BAT | VCC | Not USB. |
| GND | GND | |
| A0 / GPIO18 | DIN | Through a 330–470Ω series resistor. `led_ring_pin` |
| — | DOUT | Unused (only chains a second ring). |

| Part | Connection | Notes |
|---|---|---|
| C2, 1000µF 10V electrolytic | + to ring VCC, − to ring GND | Right at the ring. |

- No level shifter is needed while VCC is on BAT. It's only needed if the ring moves to 5V.

## Pins: reserved, avoid, spare

| Pin | Status |
|---|---|
| GPIO7 | Powers the I2C pull-ups / STEMMA QT port (and the MAX17048 fuel gauge at 0x36). Don't use. |
| GPIO12 (D12) | Reserved for amp SD (mute/sleep). Not wired yet. |
| GPIO13 (D13) | Red LED on the Feather. Avoid. |
| GPIO21, GPIO33 | The Feather's own NeoPixel and its power. Avoid. |
| GPIO8 (A5) | Spare touch-capable pin. |
| GPIO9–11 (D9–D11) | Free since the I2S move. Touch-capable, but sit next to D5/D6. |

## Planned, not built

- A high-side MOSFET switch for ring VCC: AO3401 + 2N7000, GPIO not chosen yet.
  See "Battery build" in [hardware_notes.md](hardware_notes.md).
- GPIO12 → amp SD for mute/sleep.

## Gotchas

- **Speaker outputs are bridge-tied.** Never connect SPK+ or SPK− to GND, including a
  scope ground clip.
- **Don't drive SD high from a GPIO.** A solid 3.3V selects the LEFT channel only. For
  mute, pull it low; to play, release it (open-drain).
- Firmware sends mono as the same sample in both I2S slots, so the amp's L+R mix plays it
  at full level.
