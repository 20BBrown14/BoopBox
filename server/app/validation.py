"""Text rules shared by every route (data_design.md, "Limits and validation").

Clean a value first, then check it, so padding or combining characters can't
dodge a limit. Problems are short phrases without the field name, because the
error's `field` already says which input it is.
"""

import unicodedata

from app.errors import ApiError, ErrorCode

EMAIL_MAX = 254

# Cc is the control characters, newlines included. Zl and Zp are the Unicode
# line and paragraph separators, which break a line just the same.
_LINE_BREAKING = frozenset({"Cc", "Zl", "Zp"})


def clean(raw: str) -> str:
    """Trimmed, then NFC."""
    return unicodedata.normalize("NFC", raw.strip())


def single_line_problem(value: str) -> str | None:
    if any(unicodedata.category(char) in _LINE_BREAKING for char in value):
        return "must not contain line breaks or control characters"
    return None


def length_problem(value: str, min: int, max: int) -> str | None:
    """Counts code points, as SQLite's length() does."""
    if min <= len(value) <= max:
        return None
    if min == 0:
        return f"must be at most {max} characters"
    return f"must be {min} to {max} characters"


def email_problem(value: str) -> str | None:
    if len(value) > EMAIL_MAX:
        return f"must be at most {EMAIL_MAX} characters"
    local, at, domain = value.partition("@")
    if not at or not local or not domain or "@" in domain:
        return "must be an email address"
    return None


def require(problem: str | None, field: str) -> None:
    """Raise the problem as an `invalid_request` on `field`, if there is one."""
    if problem is not None:
        raise ApiError(ErrorCode.invalid_request, problem, field=field)
