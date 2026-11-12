# BoopBox — Breadboard Connections: Mono Amp (MAX98357A)

Feather ESP32-S3 + MAX98357A I2S amp + 4Ω/3W speaker, powered from USB.
Source of truth: schematic `hardware/boopbox-proto/audio_max98357a.kicad_sch` and pin
substitutions in `firmware/BoopBox_v0.1.0.yaml`. See also `hardware_notes.md`.

## Wiring

| # | From (Feather ESP32-S3) | To (MAX98357A) | Signal | Notes |
|---|---|---|---|---|
| 1 | D9 / GPIO9 | BCLK | I2S bit clock | `i2s_bclk_pin` |
| 2 | D10 / GPIO10 | LRC | I2S word select (LR clock) | `i2s_lrclk_pin` |
| 3 | D11 / GPIO11 | DIN | I2S data | `i2s_dout_pin` |
| 4 | BAT (3.7–4.2V) | VIN | Power | Was USB 5V (~2.5W into 4Ω); BAT since 2026-11-10 so it runs on battery. 3.3V only ~1.3W |
| 5 | GND | GND | Ground | Share a common ground rail |
| 6 | GND | GAIN | Gain select | GND = 12 dB (floating 9 dB was too quiet) |
| 7 | — (leave floating) | SD | Shutdown / channel select | Floating = (L+R)/2 mono. GPIO12 reserved for mute later |

## Other parts

| # | Part | Connection | Notes |
|---|---|---|---|
| 8 | 1000µF 10V electrolytic | + to amp VIN, − to amp GND | Place right at the amp pins. Mind polarity |
| 9 | Speaker 4Ω 3W (+) | amp SPK+ (`+` screw terminal) | |
| 10 | Speaker 4Ω 3W (−) | amp SPK− (`−` screw terminal) | |

## Gotchas

- **Speaker outputs are bridge-tied.** Never connect SPK+ or SPK− to GND, including a
  scope ground clip.
- **Don't drive SD high from a GPIO.** A solid 3.3V selects LEFT channel only. For mute,
  pull it low; to play, release it (open-drain).
- **USB pin is dead on battery.** For battery operation move VIN to BAT (3.7–4.2V is in
  range).
- Firmware sends mono as the same sample in both I2S slots, so the amp's L+R mix plays it
  at full level.
