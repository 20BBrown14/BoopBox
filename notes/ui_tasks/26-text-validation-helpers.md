# 26 — Text validation helpers

Step 6 (Users and invites) · Depends on: 04 · Size: S

## Goal

The normalization and limit rules from data_design.md "Limits and validation",
in one module every route uses.

## Changes

New `app/validation.py`:

- `clean(raw) -> str`: trim, then NFC.
- `single_line_problem(value) -> str | None`: rejects control characters,
  including newlines.
- `length_problem(value, min, max) -> str | None`: counts code points.
- `email_problem(value) -> str | None`: at most 254 characters, exactly one `@`,
  and a non-empty part on each side.
- `require(problem, field)`: raises `ApiError(invalid_request, problem, field)`
  when `problem` is set.

`app/auth/passwords.py` keeps its own username and password rules.

## Tests

Unit tests per helper, including combining characters (a string that becomes
shorter after NFC) and padding that is trimmed.
