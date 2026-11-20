# Touch pad tuning

A repeatable way to measure the capacitive pads and set their thresholds.
Background and past results are in [hardware_notes.md](hardware_notes.md)
("UI: capacitive buttons").

## How detection works (short version)
- On the ESP32-S3 the raw reading **rises** when a finger is near the pad.
- The hardware keeps a **benchmark**, which is the untouched baseline, and
  follows slow drift on its own.
- `difference = value − benchmark`. A pad reads touched when
  `difference > threshold`. So the threshold is a **delta**, not an absolute
  reading.
- The benchmark **freezes while a pad reads touched**. Any step change bigger
  than the threshold (a pad swap, the amp starting or stopping) latches the
  pad ON until the reading drops back.
- Thresholds are set in the YAML (`threshold:` on each `esp32_touch` sensor) and
  need a reflash. Changing them at runtime has no effect.

## Before you start
- **Reboot after any pad, wire or resistor change.** A pad changed on a
  running box latches.
- **Route the touch leads** away from the amp, the speaker pair, BAT wiring and
  the PN532. Cross other wires at right angles. Keep the LED ring data line at
  least 4 mm away.
- **Write down the setup**, so results can be compared:
  - Board (MAC)
  - Pins
  - Pad type and size
  - Panel material and thickness
  - Series resistor
  - Power (USB or battery)
  - Firmware version

## 1. Turn on setup mode
Web UI → **Device** → **Touch Setup Mode** → on. The box then logs every pad
about 4 times a second:

```
Touch Pad 'Touch Vol Up' (Ch5): value=212333, benchmark=212344, difference=-11
```

The switch is off after every boot. Turn it off when you're done, because it
costs CPU.

## 2. Start the capture
From `firmware/`, with the board on USB:

```bash
esphome -s mqtt_broker 192.168.68.64 -s mqtt_port 1883 \
  -s server_base_url http://192.168.68.72:9685 \
  logs BoopBox_v0.3.3.yaml --device /dev/ttyACM0 \
  | python3 tools/touch_summary.py capture_raw.log
```

- [`tools/touch_summary.py`](../firmware/tools/touch_summary.py) prints one
  line a second with each pad's min..max `difference`, plus every press and
  player state change.
- The raw log goes to `capture_raw.log`.
- Stop the capture with Ctrl-C.

## 3. Run the routine
Each touch is a single, steady fingertip press on the panel. Don't re-tap
if nothing seems to happen. The Vol Up and Vol Down presses show the volume
on the ring.

**Run A: no music.** Start with the player **idle (stopped), not paused**. From
paused, the Play/Pause touch resumes the music. A reboot leaves the player idle.

| Step | Action |
|---|---|
| 1 | Wait 5 s |
| 2 | Touch **Vol Down** for 3 s |
| 3 | Wait 5 s |
| 4 | Touch **Vol Up** for 3 s |
| 5 | Wait 5 s |
| 6 | Touch **Play/Pause** for 3 s |
| 7 | Wait 5 s |

**Run B: music playing.** Boop a tag, wait 5 s, then do Run A's routine. The
Play/Pause touch pauses the music, and the last 5 s wait checks for false
presses after the pause.

## 4. Read the results
For each pad, take these from the summary:

| Measure | Where to read it | What's good |
|---|---|---|
| **Idle noise** | Run A, untouched seconds | Within about ±500 |
| **Touch delta** | Run A, lowest held value during the 3 s touch | At least 3% of the raw value, and at least 5× the idle noise |
| **Playback shift** | Run B: untouched level after PLAYING, compared with Run A | Close to 0. A positive shift moves the pad toward the threshold. A negative shift turns into a jump up at pause. |
| **False presses** | `EVENT` lines with no touch | None |

**Choosing a threshold:**
- Start at **about 55% of the lowest held touch**.
- It must stay well above **idle noise + the size of any playback shift**. If
  the shift is close to the touch delta, no threshold will work: fix the
  wiring or the pin first.

Then:
1. Put the thresholds in `firmware/BoopBox_v0.3.3.yaml`.
2. Reflash.
3. Run A and Run B again to confirm.
4. Turn the setup mode switch off.

## 5. Record it
Add a dated entry to `hardware_notes.md` with this template:

```markdown
### Touch tuning run (YYYY-MM-DD)
Setup: board <MAC>, pins <…>, pads <type/size>, panel <material, thickness>,
resistor <Ω>, power <USB/battery>, firmware <version>.

| Pad (GPIO) | Raw | Idle noise | Touch delta (held, Run A / Run B) | Playback shift | False presses | Threshold |
|---|---|---|---|---|---|---|
| Vol Down (6) | | | | | | |
| Vol Up (5) | | | | | | |
| Play/Pause (14) | | | | | | |

Notes:
```
