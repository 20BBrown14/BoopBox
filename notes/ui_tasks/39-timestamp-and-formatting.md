# 39 — `Timestamp` and formatting helpers

Step 6 (Users and invites) · Depends on: 15 · Size: S

## Goal

Every stored UTC time shown the same way.

## Changes

- `src/lib/format.ts`: `formatDateTime(iso, lang)` with `Intl.DateTimeFormat`;
  `formatRelative(iso, now, lang)` with `Intl.RelativeTimeFormat`, choosing the
  unit by size (seconds through years).
- `src/components/Timestamp.tsx`: the relative text, with a `Tooltip` showing the
  local full time and the UTC value. `null` renders a translated "never".

## Tests

Fixed clock: relative unit boundaries; tooltip content; a non-English language
changes the output.
