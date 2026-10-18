"""Deterministic in-memory source for downstream tests.

Serves fixed bytes with Range support, reports a configurable duration (or
None), and can simulate `item_unavailable` / `source_unavailable`. No external
dependencies so P6/P7/P9 tests stay stable.
"""

from collections.abc import AsyncIterator

from app.config import Settings
from app.errors import ErrorCode
from app.types.config import SourceConfig
from app.types.source import Range, SourceError

_CONTENT_TYPE = "audio/mpeg"
_CHUNK = 64 * 1024


class _FakeStream:
    """An open ranged read over in-memory bytes; async context manager so the
    close path is exercised exactly like a real upstream connection."""

    def __init__(self, data: bytes, byte_range: Range | None) -> None:
        self.content_type = _CONTENT_TYPE
        self.total_size = len(data)
        if byte_range is None:
            self._slice = data
            self.content_length = len(data)
            self.content_range = None
        else:
            start = max(0, byte_range.start)
            end = min(byte_range.end, len(data) - 1)
            self._slice = data[start : end + 1]
            self.content_length = len(self._slice)
            self.content_range = (start, end, len(data))
        self.closed = False

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for i in range(0, len(self._slice), _CHUNK):
            yield self._slice[i : i + _CHUNK]

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.closed = True


class FakeSource:
    """A `Source` over fixed bytes.

    `fail_with` forces every call to raise that unavailable code; otherwise a
    read for a missing `known_item` raises `item_unavailable`.
    """

    def __init__(
        self,
        data: bytes = b"boop" * 1024,
        duration: int | None = 180,
        known_item: str = "fake-item",
        fail_with: ErrorCode | None = None,
    ) -> None:
        self._data = data
        self._duration = duration
        self._known_item = known_item
        self._fail_with = fail_with
        # Exposed so tests can assert the last opened stream was closed.
        self.last_stream: _FakeStream | None = None

    def _guard(self, item: str) -> None:
        if self._fail_with is not None:
            raise SourceError(self._fail_with, log_detail=f"fake forced {item!r}")
        if item != self._known_item:
            raise SourceError(
                ErrorCode.item_unavailable, log_detail=f"no such fake item {item!r}"
            )

    async def open(self, item: str, byte_range: Range | None) -> _FakeStream:
        self._guard(item)
        stream = _FakeStream(self._data, byte_range)
        self.last_stream = stream
        return stream

    async def duration(self, item: str) -> int | None:
        self._guard(item)
        return self._duration


def _build_fake(config: SourceConfig, settings: Settings) -> "FakeSource":
    # The fake needs no base_url/secret; args accepted for the builder shape.
    return FakeSource()
