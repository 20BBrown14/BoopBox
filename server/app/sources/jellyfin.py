"""Jellyfin media source.

Opens an item's audio byte stream (honoring Range), reports duration from item
metadata, and expands a collection to its member item ids. Every upstream
failure maps to a `SourceError` with a generic code; the real detail (URLs,
item ids, keys, upstream bodies) stays in `log_detail` and never reaches the
client.
"""

import logging
from collections.abc import AsyncIterator

import httpx2 as httpx

from app.errors import ErrorCode
from app.types.source import Range, SourceError

logger = logging.getLogger(__name__)

# Ticks are 100-nanosecond units; 10_000_000 per second.
_TICKS_PER_SECOND = 10_000_000
_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class JellyfinStream:
    """An open ranged read over a Jellyfin audio response.

    Async context manager: `__aexit__` closes the underlying httpx stream so the
    upstream connection is released when the box disconnects mid-stream.
    """

    def __init__(self, response: httpx.Response, ctx: object) -> None:
        self._response = response
        self._ctx = ctx
        self.closed = False

        self.content_type = response.headers.get(
            "content-type", "application/octet-stream"
        )
        content_range = response.headers.get("content-range")
        if response.status_code == 206 and content_range:
            start, end, total = _parse_content_range(content_range)
            self.content_range: tuple[int, int, int] | None = (start, end, total)
            self.total_size = total
            self.content_length = end - start + 1
        else:
            self.content_range = None
            length = response.headers.get("content-length")
            self.total_size = int(length) if length is not None else 0
            self.content_length = self.total_size

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        async for chunk in self._response.aiter_bytes():
            yield chunk

    async def __aenter__(self) -> "JellyfinStream":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._ctx.__aexit__(*exc)
        self.closed = True


def _parse_content_range(header: str) -> tuple[int, int, int]:
    # "bytes 0-1023/2048"
    _, _, spec = header.partition(" ")
    rng, _, total = spec.partition("/")
    start_s, _, end_s = rng.partition("-")
    return int(start_s), int(end_s), int(total)


class JellyfinSource:
    """A `Source` backed by a Jellyfin server, addressed by opaque item ids."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        user_id: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._user_id = user_id or None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._auth_headers(),
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f'MediaBrowser Token="{self._api_key}"'}

    def _require_key(self) -> None:
        if not self._api_key:
            raise SourceError(
                ErrorCode.source_unavailable,
                log_detail="jellyfin api key not configured",
            )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def duration(self, item: str) -> int | None:
        self._require_key()
        params = {"userId": self._user_id} if self._user_id else None
        try:
            resp = await self._client.get(f"/Items/{item}", params=params)
        except httpx.HTTPError as err:
            raise _connection_error(err) from err
        _raise_for_status(resp, item)
        try:
            body = resp.json()
        except ValueError as err:
            raise SourceError(
                ErrorCode.source_unavailable,
                log_detail=f"jellyfin metadata not JSON for {item!r}",
            ) from err
        ticks = body.get("RunTimeTicks")
        if not ticks:  # None or 0 -> unknown
            return None
        return int(ticks) // _TICKS_PER_SECOND

    async def open(self, item: str, byte_range: Range | None) -> JellyfinStream:
        self._require_key()
        headers = {}
        if byte_range is not None:
            headers["Range"] = f"bytes={byte_range.start}-{byte_range.end}"
        ctx = self._client.stream(
            "GET",
            f"/Audio/{item}/stream",
            params={"static": "true"},
            headers=headers,
        )
        try:
            response = await ctx.__aenter__()
        except httpx.HTTPError as err:
            raise _connection_error(err) from err
        if response.status_code >= 400:
            # Read + close before mapping so the connection is released.
            await response.aread()
            await ctx.__aexit__(None, None, None)
            _raise_for_status(response, item)
        return JellyfinStream(response, ctx)

    async def _list_items(self, item: str, **params: str) -> list[dict]:
        """GET /Items with `params`, returning the raw `Items` list.

        No `userId` is sent: the API key scopes the request, and user-scoping a
        collection query can silently drop BoxSet members server-side. Upstream
        failures map to the error vocabulary with log-only detail.
        """
        try:
            resp = await self._client.get("/Items", params=params)
        except httpx.HTTPError as err:
            raise _connection_error(err) from err
        _raise_for_status(resp, item)
        try:
            body = resp.json()
        except ValueError as err:
            raise SourceError(
                ErrorCode.source_unavailable,
                log_detail=f"jellyfin items not JSON for {item!r}",
            ) from err
        return body.get("Items") or []

    async def members(self, collection: str) -> list[str]:
        """Expand a collection to its playable `Audio` item ids.

        Two-level walk: a Jellyfin collection (`BoxSet`) lists its children
        (albums, loose tracks), but a single recursive+Audio query does not
        descend through an album to its tracks. So each non-`Audio` child
        container is expanded one level to its `Audio` items; loose `Audio`
        children pass through directly.
        """
        self._require_key()
        children = await self._list_items(collection, parentId=collection, recursive="true")

        member_ids: list[str] = []
        for child in children:
            cid = child.get("Id")
            if not cid:
                continue
            if child.get("Type") == "Audio":
                member_ids.append(cid)
                continue
            tracks = await self._list_items(
                cid, parentId=cid, includeItemTypes="Audio"
            )
            member_ids.extend(t["Id"] for t in tracks if t.get("Id"))

        if not member_ids:
            raise SourceError(
                ErrorCode.item_unavailable,
                log_detail=f"jellyfin collection {collection!r} has no audio members",
            )
        return member_ids


def _build_jellyfin(config, settings) -> JellyfinSource:
    """Registry builder for `type: jellyfin`.

    Reads base_url/user_id from the source config and the API key from .env by
    source id (BOOPBOX_SOURCE_<ID>_API_KEY).
    """
    return JellyfinSource(
        base_url=config.base_url,
        api_key=settings.api_key_for(config.id),
        user_id=config.user_id,
    )


def _connection_error(err: httpx.HTTPError) -> SourceError:
    logger.warning("jellyfin connection error: %s", err)
    return SourceError(
        ErrorCode.source_unavailable, log_detail=f"jellyfin connection error: {err!r}"
    )


def _raise_for_status(resp: httpx.Response, item: str) -> None:
    """Map a Jellyfin HTTP status to the error vocabulary.

    404 -> item_unavailable (the item/collection is gone); 401/403 -> the source
    can't serve (bad/missing key is a source problem, not an item problem); any
    other >=400 -> source_unavailable. Upstream detail stays log-only.
    """
    status = resp.status_code
    if status < 400:
        return
    if status == 404:
        raise SourceError(
            ErrorCode.item_unavailable,
            log_detail=f"jellyfin 404 for {item!r}",
        )
    raise SourceError(
        ErrorCode.source_unavailable,
        log_detail=f"jellyfin status {status} for {item!r}",
    )
