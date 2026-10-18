"""Shared error-code vocabulary, HTTP status mapping, and the scrubbed
error-response builder.

`code` is the contract consumers branch on; `message` is inert, generic display
text that never carries upstream internals (bodies, URLs, item ids, keys, stack
traces). Upstream detail belongs in logs, never in `message`.
"""

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import BoopRef, Error


class ErrorCode(StrEnum):
    unknown_tag = "unknown_tag"
    item_unavailable = "item_unavailable"
    source_unavailable = "source_unavailable"
    unsupported_version = "unsupported_version"
    unauthorized = "unauthorized"
    forbidden = "forbidden"


# HTTP-surfaced codes only. unknown_tag and unsupported_version are MQTT-only and
# are deliberately absent: a lookup for them is a programming error, not a silent
# default, so P6 must never map an MQTT-only code to an HTTP status.
HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.unauthorized: 401,
    ErrorCode.forbidden: 403,
    ErrorCode.item_unavailable: 404,
    ErrorCode.source_unavailable: 502,
}


def http_status_for(code: ErrorCode) -> int:
    """HTTP status for an HTTP-surfaced code.

    Raises KeyError for MQTT-only codes (`unknown_tag`, `unsupported_version`):
    they have no HTTP status and a mislookup should surface loudly.
    """
    return HTTP_STATUS[code]


# Generic, inert default messages. No upstream specifics; safe to display as-is.
_DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.unknown_tag: "no mapping for the booped tag",
    ErrorCode.item_unavailable: "the requested item is unavailable",
    ErrorCode.source_unavailable: "the media source is unavailable",
    ErrorCode.unsupported_version: "unsupported protocol version",
    ErrorCode.unauthorized: "missing or malformed stream token",
    ErrorCode.forbidden: "stream token rejected",
}


def default_message(code: ErrorCode) -> str:
    """The generic, scrubbed message for a code."""
    return _DEFAULT_MESSAGES[code]


def http_error(
    code: ErrorCode, message: str | None = None
) -> tuple[dict[str, str], int]:
    """Build an HTTP error: ``({"code", "message"}, status)``.

    `message` must already be a safe, generic string; when omitted a generic
    default for the code is used. Any upstream detail goes to logs, not here.
    """
    body = {"code": str(code), "message": message or default_message(code)}
    return body, http_status_for(code)


def mqtt_error(
    code: ErrorCode,
    boop: "BoopRef | None",
    message: str | None = None,
) -> "Error":
    """Build an MQTT `Error` model with the boop correlation block.

    `message` must already be safe/generic; omitted uses the code's default.
    `boop` is normally a full BoopRef; it may be partial or None only for
    `unsupported_version` (best-effort, parsed before the unknown `v`).
    """
    # Imported here to avoid a module-load cycle (models imports ErrorCode).
    from app.models import Error

    return Error(code=code, boop=boop, message=message or default_message(code))
