# 24 — Security headers on UI responses

Step 5 (Serving) · Depends on: 23 · Size: S

## Goal

The headers from ui_design.md "Security headers" on `index.html` and assets.

## Changes

- In `app/routes/web.py`, add `Content-Security-Policy`,
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer` to every
  response it produces.
- API responses get `X-Content-Type-Options: nosniff` only; a CSP on JSON adds
  nothing.

## Tests

Headers present on index and asset responses, with the exact CSP string.

## Review focus

The CSP string itself.
