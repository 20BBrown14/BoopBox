"""GET /stream?sig=<token> — verify the token, resolve the bound source+item,
and proxy bytes honoring Range.
"""

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import get_settings
from app.errors import ErrorCode, http_error
from app.stream_token import verify
from app.types.source import Range, SourceError, StreamResponse
from app.types.token import StreamClaims

logger = logging.getLogger(__name__)

router = APIRouter()

# Returned by _parse_range for a well-formed but out-of-bounds range (-> 416).
UNSATISFIABLE = object()


def _json_error(code: ErrorCode) -> JSONResponse:
    body, status = http_error(code)
    return JSONResponse(body, status_code=status)


def _parse_range(header: str, total_size: int) -> Range | None | object:
    """Parse a single `bytes=` Range header against `total_size`.

    Honors `start-end`, `start-`, and `-suffix`. A malformed or multi-range
    header is ignored (-> None, serve 200 full). A well-formed but out-of-bounds
    range returns the UNSATISFIABLE sentinel (-> 416).
    """
    unit, _, spec = header.partition("=")
    if unit.strip() != "bytes" or "," in spec:
        return None
    start_s, sep, end_s = spec.strip().partition("-")
    if not sep:
        return None
    try:
        if not start_s:  # suffix: last N bytes
            n = int(end_s)
            if n <= 0:
                return None
            return Range(start=max(0, total_size - n), end=total_size - 1)
        start = int(start_s)
        end = int(end_s) if end_s else None  # None = open-ended
    except ValueError:
        return None
    if start < 0 or (end is not None and end < start):
        return None
    if start >= total_size:
        return UNSATISFIABLE
    resolved_end = total_size - 1 if end is None else min(end, total_size - 1)
    return Range(start=start, end=resolved_end)


def _stream_headers(resp: StreamResponse) -> tuple[int, dict[str, str]]:
    headers = {
        "Content-Length": str(resp.content_length),
        "Accept-Ranges": "bytes",
    }
    if resp.content_range is not None:
        start, end, total = resp.content_range
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return 206, headers
    return 200, headers


async def _proxy(resp: StreamResponse):
    """Stream bytes, closing the source CM on completion or client disconnect."""
    async with resp:
        async for chunk in resp.aiter_bytes():
            yield chunk


@router.get("/stream")
async def stream(request: Request, sig: str | None = None):
    settings = get_settings()

    if not sig:
        return _json_error(ErrorCode.unauthorized)

    result = verify(sig, now=int(time.time()), secret=settings.stream_secret)
    if isinstance(result, ErrorCode):
        return _json_error(result)
    claims: StreamClaims = result

    # Provenance only — never used to authorize the requester.
    logger.info("stream claim device=%s source=%s", claims.device, claims.source)

    source = request.app.state.sources.get(claims.source)

    range_header = request.headers.get("range")
    byte_range: Range | None = None
    if range_header:
        try:
            async with await source.open(claims.item, None) as probe:
                total_size = probe.total_size
        except SourceError as err:
            logger.warning("stream open failed: %s", err.log_detail)
            return _json_error(err.code)
        parsed = _parse_range(range_header, total_size)
        if parsed is UNSATISFIABLE:
            return JSONResponse(
                {
                    "code": "range_not_satisfiable",
                    "message": "requested range not satisfiable",
                },
                status_code=416,
                headers={"Content-Range": f"bytes */{total_size}"},
            )
        byte_range = parsed  # type: ignore[assignment]

    try:
        resp = await source.open(claims.item, byte_range)
    except SourceError as err:
        logger.warning("stream open failed: %s", err.log_detail)
        return _json_error(err.code)

    status, headers = _stream_headers(resp)
    return StreamingResponse(
        _proxy(resp),
        status_code=status,
        media_type=resp.content_type,
        headers=headers,
    )
