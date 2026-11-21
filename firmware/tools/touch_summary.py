#!/usr/bin/env python3
"""Condense esp32_touch setup-mode logs to one line per second.

Reads `esphome logs` output on stdin. For each second it prints every pad's
min..max `difference` and its last raw value, plus any `touch:` press events
and media player state changes. See notes/touch_tuning.md.

Usage:
    esphome ... logs BoopBox_v0.3.3.yaml --device /dev/ttyACM0 \
        | python3 tools/touch_summary.py [raw_log_path]

If raw_log_path is given, every input line is also appended there.
"""
import re
import sys

PAD = re.compile(
    r"\[(\d\d:\d\d:\d\d)\.\d+\].*Touch Pad '([^']+)' \(Ch(\d+)\): "
    r"value=(\d+), benchmark=\d+, difference=(-?\d+)"
)
# Log lines worth echoing as events: press handlers and player state changes.
EVENT = re.compile(r"touch: |State changed to")

raw = open(sys.argv[1], "a") if len(sys.argv) > 1 else None
cur_sec = None
stats = {}  # pad label -> (min diff, max diff, last value)


def flush():
    if cur_sec is None or not stats:
        return
    parts = [f"{label} {lo:>7}..{hi:<7} v={val}" for label, (lo, hi, val) in sorted(stats.items())]
    print(f"{cur_sec}  " + " | ".join(parts), flush=True)


for line in sys.stdin:
    if raw:
        raw.write(line)
        raw.flush()
    m = PAD.search(line)
    if not m:
        if EVENT.search(line):
            print("    EVENT " + line.strip(), flush=True)
        continue
    sec, name, ch, val, diff = m.group(1), m.group(2), m.group(3), int(m.group(4)), int(m.group(5))
    label = f"{name.removeprefix('Touch ')}(GPIO{ch})"
    if sec != cur_sec:
        flush()
        cur_sec, stats = sec, {}
    lo, hi, _ = stats.get(label, (diff, diff, val))
    stats[label] = (min(lo, diff), max(hi, diff), val)
flush()
