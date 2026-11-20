# 64 — Reconcile the design notes

Step 10 (Docs) · Depends on: 63 · Size: S

## Goal

The planning notes match what was built.

## Changes

- ui_design.md:
  - `/ota/update` is now `/api/ota/update` (task 02). Keep `/ota` in the
    reserved-prefix list.
  - Remove the "Open questions" entry from the table of contents if that
    section is still gone.
  - Record decisions made during review (for example tasks 15, 37, 48).
- deferred.md: drop anything that shipped; add anything that was cut.
- server_design.md and data_design.md: fix any route or behavior references
  that changed.

## Tests

None (docs only).
