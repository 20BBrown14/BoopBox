# 16 — AppShell layout and routes

Step 4 (Scaffold) · Depends on: 15 · Size: M

## Goal

The app frame and route table, with placeholder pages.

## Changes

- React Router v8 in declarative mode (`BrowserRouter`, `Routes`).
- `src/app/AppLayout.tsx`: Mantine `AppShell` with a sidebar from `sm` up, and
  a header with a burger that opens the nav as a drawer below `sm`. The drawer
  closes on navigation.
- Nav items: Devices, Users, Server settings, Account. Every item is shown for
  now; task 19 hides them by permission.
- Routes: `/` → `/devices`; `/devices`, `/devices/:id`, `/users`, `/users/:id`,
  `/server-settings`, `/account` as placeholders inside the layout;
  `/login`, `/change-password`, `/invite` outside it; `*` → NotFound.
- `NotFound` and `NoPermission` pages.
- All text from `common.json`.

## Tests

Each route renders its placeholder; an unknown path renders NotFound; the burger
toggles the nav.

## Review focus

Route table shape; it is the skeleton every later page plugs into.
