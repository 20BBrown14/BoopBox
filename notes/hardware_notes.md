BoopBox — Hardware Notes

## What the chip has to do (drives the board choice)
BoopBox is more demanding than a typical ESP32 project because of three things happening together:
1. Audio playback over I2S — streaming + buffering needs RAM.
2. TLS + MQTT + HTTP OTA concurrently — TLS handshakes/buffers also eat RAM.
3. Free I2S pins for an audio DAC, plus I2C for the PN532 NFC reader.

The audio + TLS combination is the real constraint. **PSRAM is the non-negotiable requirement** for the production board; dual-core helps (one core for WiFi/MQTT/TLS, audio runs without stuttering). "Any cheap ESP32 devkit" is the wrong answer here — no-PSRAM boards run out of heap exactly when audio and TLS run together, and it shows up as mysterious crashes.

## Board recommendation
- **DECIDED — prototyping on ESP32-S3 DevKitC** (with PSRAM). Newer dual-core line, better I2S, native USB, and where Espressif's audio tooling and ESPHome's newer `media_player` work is increasingly focused. Make sure the specific board has PSRAM.
- Alternative considered: ESP32-WROVER DevKit (classic dual-core ESP32 + 8MB PSRAM) — maximum copy-paste examples today. Went with S3 for the audio momentum going forward.
- **Avoid for this use case:**
  - Plain ESP32-WROOM (no PSRAM) — fine for the tag-read loop, bites on audio + TLS.
  - ESP32-C3 — single-core, less RAM, no PSRAM; fights us exactly where BoopBox is demanding.
  - All-in-one audio dev boards (LyraT, S3-Box) — handy for a quick audio sanity-check, but too big/pricey and lock us into their pinout/case, poor fit for a custom 3D-printed enclosure.

## Prototyping with the WROOM-32D (on hand)
- Using an ESP32-WROOM-32D to start. It has **no PSRAM**, so:
  - Good enough to validate the full loop: tag read → MQTT publish → server → play command → basic playback.
  - Likely to get tight on the specific combo of audio streaming + TLS + MQTT at once.
  - If heap/crash trouble appears exactly when TLS is added on top of audio streaming, treat it as the PSRAM ceiling, not a logic bug — move to a PSRAM board for that validation rather than chasing it in code.

## Form factor
- **DECIDED — the whole DevKitC goes in the box**, not a bare module on a custom PCB. Simpler build, no PCB design/fab, easy to flash and debug.
- Tradeoff accepted: the devkit (USB bridge, headers, regulator) is bulkier than a bare module, so the case has to be sized around it. Fine for this project's scope.
- (Bare module on a custom PCB — WROVER-E or S3 MINI-1 — remains the path if a much smaller box ever becomes a priority, but it's not planned.)

## NFC reader: PN532 (not RC522)
- **DECIDED — PN532 over I2C.** Both are NXP 13.56 MHz readers and RC522 is a bit cheaper, but PN532 is the right fit here:
  - **Chip/standards:** RC522 (MFRC522) is built around MIFARE/ISO 14443A and is the budget, narrower reader — it reads UIDs but little more. PN532 is a fuller NFC controller (14443A/B, FeliCa, full NFC Forum tags) that properly supports the NTAG213/215/216 tags we chose, including their user memory.
  - **Interface:** RC522 is SPI-only in practice. PN532 boards have a DIP switch for I2C/SPI/UART, so I2C (what our config uses) is clean and leaves SPI free.
  - **ESPHome support (the clincher):** native, first-class `pn532_i2c`/`pn532_spi` component with the `on_tag` trigger — exactly what the firmware in initial_notes.md is built on. RC522 support exists but is less capable and would mean rewriting the reader half of the config and losing smooth NTAG support.
  - **Range:** comparable (~few cm); not a differentiator, and short range is desirable for tap-and-play anyway.
- RC522 would only be fine if we *only* ever read UIDs and never touch NTAG memory — but even then the ESPHome fit makes PN532 the easier path. Saving ~$1 isn't worth the weaker chip, SPI-only interface, and worse ESPHome ergonomics.

## Audio DAC/amp (pairs with any board choice)
- The ESP32 outputs I2S but has no good built-in DAC for driving a speaker. Pair it with an external I2S DAC/amp.
- **MAX98357A** — I2S DAC + 3W class-D amp in one, cheap, ESPHome-friendly, matches the `i2s_audio` + `media_player` config in initial_notes.md. The standard choice.
- Plus a 4Ω/3W speaker.

## Prototype shopping list
- [ESP32-S3 DevKitC (with PSRAM)](https://www.digikey.com/en/products/detail/adafruit-industries-llc/5477/16583982)
- [PCM5102A DAC](https://www.amazon.com/HiLetgo-Lossless-Digital-Converter-Raspberry/dp/B07Q9K5MT8)
- [Class-D amp](https://www.adafruit.com/product/987)
- [4Ω/3W speaker.](https://www.digikey.com/en/products/detail/pui-audio-inc/AS07104PO-LW152-WR-R/4835137)
- [PN532 NFC reader, DIP switch set to I2C mode.](https://www.amazon.com/HiLetgo-Communication-Arduino-Raspberry-Android/dp/B0H7TL6W1W?crid=3DEH1BS8TXRHD&dib=eyJ2IjoiMSJ9.UZ7hGc1saDgWsDy_9m3URYrP1jRUDgtu-frL27SLL4Il0M8FJ82NSYWpzSseN1zqy5rP59O_tCfNBl-d6AL-s8LIwztGlBF09WLRN3230Rs4P-MsxrCJB1sXvMxhEmtpIAgRRpKuPcrnRZCq4VFClGfjpeaoLY0JERxmGuOsufurwJfqmT8QDPfi5HUgHs6xF7HLxuQeotBbmMo5MBF6SNdPhdNwlpJ8glzWu57H4OuTVZttmEJKZG8LyhokwQnRK7s-lTuSYCAwiqYfGYB4N_A7HvXPoC0My2e35X-t6rA.ZLZeH_6BRpw1K6xrUx115UoA36_i4-eqtNEqu1zA1h0&dib_tag=se&keywords=pn532%2Bnfc%2Breader&qid=1791430985&s=industrial&sprefix=pn532%2Bnfc%2Bread%2Cindustrial%2C132&sr=1-3&th=1)

## To verify before committing to purchases
- Current board SKUs, prices, and availability (not re-checked against today's listings).
- Latest ESPHome ESP32-S3 audio/`media_player` support status if going the S3 route.
