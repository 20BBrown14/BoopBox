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
