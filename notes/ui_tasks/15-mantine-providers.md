# 15 — Mantine and app providers

Step 4 (Scaffold) · Depends on: 14 · Size: S

## Goal

The provider stack from ui_design.md "Frontend structure".

## Changes

- `@mantine/core`, `@mantine/hooks`, `@mantine/notifications`,
  `@mantine/modals`, `@mantine/form`, plus the PostCSS setup Mantine's Vite
  guide calls for.
- `src/app/theme.ts` (minimal) and `src/app/Providers.tsx`: `I18nextProvider`,
  `MantineProvider` (`defaultColorScheme="auto"`), `Notifications`,
  `ModalsProvider`, `QueryClientProvider`. The router is added in task 16.
- `renderWithProviders` wraps the same stack.

## Tests

The smoke test renders inside the providers.

## Review focus

**No flash fix yet.** Mantine's `ColorSchemeScript` is an inline script, which
the planned CSP (task 24) blocks, so it is left out. Once the UI runs, check
whether a light/dark flash on load is actually noticeable before fixing it.
Candidate fixes are tracked in deferred.md.
