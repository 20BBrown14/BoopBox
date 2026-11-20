# 13 — Vitest, React Testing Library and MSW

Step 4 (Scaffold) · Depends on: 12 · Size: S

## Goal

Test infrastructure every later frontend task uses.

## Changes

- Vitest with jsdom, `@testing-library/react`, `@testing-library/user-event`,
  `@testing-library/jest-dom`, MSW (node).
- `src/test/setup.ts`: jest-dom matchers; MSW server start/reset/close with
  `onUnhandledRequest: "error"`; `matchMedia` and `ResizeObserver` stubs (Mantine
  needs both in jsdom).
- `src/test/server.ts` (MSW server) and `src/test/handlers/` (empty for now).
- `src/test/render.tsx`: `renderWithProviders()`, extended as providers are added.
- `test` script; `check` runs it.

## Tests

One smoke test that renders `App`.

## Review focus

Unhandled requests fail the test, so a missing mock can't pass silently.
