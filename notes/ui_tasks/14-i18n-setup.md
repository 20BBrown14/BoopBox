# 14 — i18n setup

Step 4 (Scaffold) · Depends on: 13 · Size: M

## Goal

Every UI string goes through `t()` from the first screen. See ui_design.md
"Translation (i18n)".

## Changes

- `i18next`, `react-i18next`, `i18next-browser-languagedetector`,
  `i18next-resources-to-backend`.
- `src/i18n/index.ts`: init with English bundled, other languages loaded by
  dynamic `import()`, `fallbackLng: "en"`, `escapeValue: false` (React
  escapes). Detection order:
  `localStorage` (key `boopbox.language`), then `navigator`.
- On `languageChanged`, set `document.documentElement.lang`.
- `src/locales/en/`: `common.json`, `auth.json`, `errors.json` (one entry per
  `ErrorCode`). Later features add their own namespace.
- `src/i18n/i18next.d.ts`: typed resources from the English files, so unknown
  keys fail `tsc`.
- `src/i18n/languages.ts`: the list of shipped languages (English only).
- ESLint `i18next/no-literal-string` on `src/`, with test files exempt. Mode
  `jsx-only`, checking JSX text and only the `label`, `description`,
  `placeholder`, `title`, `error`, `alt` and `aria-label` props.

## Tests

- Key parity: every non-English locale's keys are a subset of English. Written
  generically, so it starts covering a language as soon as one is added.
- Changing the language updates `<html lang>`.

## Review focus

The lint rule's options. Too strict flags class names and test ids; too loose
lets text through.
