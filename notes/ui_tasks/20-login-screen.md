# 20 — Form error helper and login screen

Step 4 (Scaffold) · Depends on: 19, 09 · Size: S

## Goal

The login page, plus the helper that puts server errors on form fields.

## Changes

- `src/api/formErrors.ts`: `applyApiError(form, err, t)`. If `err.field` names a
  form field, `form.setFieldError(field, errorText(t, err))`; otherwise a
  notification.
- `/login`: username, password, submit → `POST /api/auth/login`; then
  invalidate `['me']` and navigate to `next`.
- `next` is accepted only if it starts with `/` and not `//`, so it can't be
  used as an open redirect.
- Failure shows the one generic message.
- Already logged in → redirect to `/`.

## Tests

Success redirects to `next`; an off-site `next` (`//evil`, `https://…`) falls
back to `/`; generic error shown; `applyApiError` field vs notification.
