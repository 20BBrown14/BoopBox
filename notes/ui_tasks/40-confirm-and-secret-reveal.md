# 40 — `ConfirmDanger` and `SecretReveal`

Step 6 (Users and invites) · Depends on: 15 · Size: M

## Goal

The two modals from ui_design.md "Screens": one for destructive actions, one for
values shown only once.

## Changes

- `src/components/confirmDanger.tsx` (`.tsx` because the body is JSX): wraps
  `openConfirmModal` with a red confirm button and a body naming the target.
  Returns a promise.
- `src/components/SecretReveal.tsx`:
  - can't be closed by clicking outside, Escape or a close button
  - each secret has a read-only field and a `CopyButton`; an optional link
    field; an optional warning slot
  - a confirmation checkbox ("I've saved it") enables the Done button
  - on close it calls `onDone`, and the caller drops the value
- Rule for every mutation that returns a secret: `gcTime: 0`, and `reset()` on
  close, so the value doesn't linger in the mutation cache. `useSecretMutation`
  (`src/api/secretMutation.ts`) applies the `gcTime` half; the caller still
  calls `reset()` from `onDone`.

## Tests

- Escape and outside click don't close the reveal; Done is disabled until the
  checkbox is ticked.
- After the flow, no query or mutation in the client's caches still holds the
  secret.

## Review focus

The mutation-cache rule. TanStack keeps mutation results for 5 minutes by
default, which would break "never written to the query cache".
