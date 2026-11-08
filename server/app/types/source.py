"""Media source protocol and the types its stream result carries.

The source takes an opaque, source-internal `item` id; it never sees the tag
slug (the resolver already mapped slug -> (source, item)). Unavailable
conditions surface as a `SourceError` carrying an `ErrorCode`; upstream detail
(URLs, item ids, keys, bodies) rides in `log_detail` only and never reaches the
client. The scrubbed client-facing message is built from the code.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.errors import ErrorCode


@dataclass(frozen=True)
class Range:
    """A parsed, inclusive byte range. The stream route maps the HTTP `Range`
    header to this; the source stays transport-agnostic.
    `None` (not this type) means the whole object."""

    start: int
    end: int


class SourceError(Exception):
    """An unavailable condition from a source.

    `code` is the contract (`item_unavailable` / `source_unavailable`).
    `log_detail` is log-only and must never reach the client.
    """

    def __init__(self, code: ErrorCode, log_detail: str | None = None) -> None:
        super().__init__(log_detail or str(code))
        self.code = code
        self.log_detail = log_detail


class StreamResponse(Protocol):
    """An open, ranged byte stream plus the facts the stream route needs for a 200/206.

    An async context manager: `__aexit__` releases the upstream connection so the
    stream route can clean up when the box disconnects mid-stream.
    """

    content_type: str
    total_size: int
    # Bytes in this response (the slice length for a ranged read).
    content_length: int
    # (start, end, total) when this is a ranged response, else None.
    content_range: tuple[int, int, int] | None

    def aiter_bytes(self) -> AsyncIterator[bytes]: ...

    async def __aenter__(self) -> "StreamResponse": ...

    async def __aexit__(self, *exc: object) -> None: ...


@runtime_checkable
class Source(Protocol):
    """A media backend addressed by opaque `item` ids."""

    async def open(self, item: str, byte_range: Range | None) -> StreamResponse:
        """Open a byte stream for `item`, honoring `byte_range` (None = whole).

        Raises `SourceError` for unavailable conditions.
        """
        ...

    async def duration(self, item: str) -> int | None:
        """Item duration in seconds, or None if unknown.

        Obtainable without opening the stream: the boop handler needs it at
        token-mint time, before `open`. Raises `SourceError` if the item/source
        is unavailable.
        """
        ...

    async def members(self, collection: str) -> list[str]:
        """Expand a collection id to its member item ids.

        A mapping entry of kind `collection` names a collection, not a playable
        item; the boop handler calls this to turn it into concrete items and
        then picks one.
        An empty collection or a failed expansion raises `SourceError`
        (`item_unavailable` / `source_unavailable`); the handler
        publishes the scrubbed error. Implemented by the fake (tests) and Jellyfin.
        """
        ...
