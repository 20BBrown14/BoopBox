# 38 — `ResponsiveList` component

Step 6 (Users and invites) · Depends on: 15 · Size: S

## Goal

Define a list's columns once and get a table on desktop and cards on phones.

## Changes

`src/components/ResponsiveList.tsx`:

- Props: `rows`, `rowKey`, `columns: {id, header, render, primary?}[]`,
  `rowHref?`, `empty` (a translated node).
- `useMediaQuery` at the `sm` breakpoint: a Mantine `Table` above it, a stack of
  `Card`s below it. The `primary` column becomes the card title; the rest are
  label–value rows.
- When `rowHref` is set, each row or card is a real link, so it works with the
  keyboard and opens in a new tab.

## Tests

Both modes, using a mocked `matchMedia`; empty state; rows link to `rowHref`.
