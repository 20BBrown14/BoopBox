# 18 — API client and query client

Step 4 (Scaffold) · Depends on: 15, 17 · Size: M

## Goal

A typed client and the global error handling from ui_design.md "Errors".

## Changes

- `src/api/client.ts`: `openapi-fetch` `createClient<paths>()` with a
  same-origin base URL.
- Middleware: add `X-CSRF-Token` from the `boopbox_csrf` cookie on `POST`,
  `PUT`, `PATCH` and `DELETE`; turn any non-2xx into
  `ApiError {status, code, message, field}`, falling back to a network or
  unknown error when the body isn't the expected shape.
- `src/api/queryClient.ts`: no retry on 4xx. `QueryCache` / `MutationCache`
  `onError`:
  - 401: clear the cache and go to `/login?next=<current path>`
  - 403: "no permission" notification, invalidate `['me']`
  - 5xx and network: retry notification
- Navigation from outside the router goes through a small navigator ref that
  the layout registers.
- `src/api/errorText.ts`: `errorText(t, err)` translates by `code`. It falls
  back to the server `message` only for `invalid_request`.
- Query keys follow the plain-English convention in ui_design.md (multi-word
  keys like `['server settings']`).

## Tests

CSRF header on writes only; error parsing; 401 redirect includes `next`;
`errorText` fallbacks.

## Review focus

Error mapping; nearly every later task relies on it.
