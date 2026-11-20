# 12 — Vite + React + TypeScript skeleton

Step 4 (Scaffold) · Depends on: — · Size: M

## Goal

An empty but buildable `server/web/` project with lint, format and type
checking.

## Changes

- `server/web/` with `package.json`, `package-lock.json`, `tsconfig*.json`,
  `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx` (a placeholder).
- Look up current stable versions at implementation time. Specify them with `^`
  (TypeScript with `~`). React must be 19.2+ for Mantine 9.
- Node: 26 (Lithium, the current LTS), recorded in `.nvmrc` and `engines`.
- `vite.config.ts`: dev server proxy `/api` → `http://127.0.0.1:9685`.
- ESLint flat config: typescript-eslint, react-hooks,
  `@eslint-react/dom-no-dangerously-set-innerhtml` as an error
  (`eslint-plugin-react` doesn't support ESLint 10). TypeScript 6, because
  typescript-eslint doesn't support 7 yet. Prettier config.
- Scripts: `dev`, `build` (`tsc -b && vite build`), `typecheck`
  (`tsc --noEmit`), `lint`, `format`, `check` (typecheck + lint; later tasks add
  test and `check:api`).
- Root `.gitignore`: add `server/web/node_modules/`. `dist/` is already ignored.

## Tests

`npm run build` and `npm run check` pass.

## Out of scope

Mantine, i18n, router, tests (tasks 13–16).

## Review focus

Dependency versions and the lint rule set.
