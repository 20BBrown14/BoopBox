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

**Flash fix.** Mantine's `ColorSchemeScript` is an inline script, which the
planned CSP (task 24) blocks. A Vite plugin (`tools/colorSchemePlugin.ts`)
renders that component at build time and serves its script as
`/color-scheme.js`, loaded from the `<head>` of `index.html`. CSP stays
`script-src 'self'`, and Mantine upgrades are picked up automatically. In dev
only, the plugin also links Mantine's stylesheet in the `<head>`, because Vite
otherwise injects CSS from JS after the first paint.
