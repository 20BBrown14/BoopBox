"""Firmware OTA host.

- `GET /firmware/manifest.json` — the generated ESP-Web-Tools manifest. Public:
  it is browser provisioning metadata (served over USB by ESP-Web-Tools), not a
  box-authenticated fetch.
- `GET /firmware/{chip}/{filename}` — the actual bin, Range-aware and behind
  per-device OTA auth (`require_device_ota`, HTTP Basic). Replaces the old
  unauthenticated StaticFiles mount.

The manifest route is registered BEFORE the bin route so it wins over any stray
on-disk manifest.json. The bin route resolves paths under the configured
firmware dir and refuses traversal outside it.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.auth import require_device_ota
from app.config import get_settings
from app.errors import ErrorCode, http_error
from app.routes.stream import UNSATISFIABLE, _parse_range
from app.types.device import Device

router = APIRouter()


@router.get("/firmware/manifest.json")
async def firmware_manifest(request: Request) -> JSONResponse:
    cache = request.app.state.firmware
    return JSONResponse(cache.manifest(), media_type="application/json")


def _resolve_bin(chip: str, filename: str) -> Path | None:
    """Resolve a bin path under the firmware dir, or None if it escapes/absent.

    Rejects any path that resolves outside the firmware dir (traversal) and any
    non-file target. Keeps the served surface to real bins under the dir.
    """
    base = Path(get_settings().firmware_dir).resolve()
    candidate = (base / chip / filename).resolve()
    if base not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _not_found() -> JSONResponse:
    body, status = http_error(ErrorCode.item_unavailable)
    return JSONResponse(body, status_code=status)


@router.get("/firmware/{chip}/{filename}")
async def firmware_bin(
    request: Request,
    chip: str,
    filename: str,
    _device: Device = Depends(require_device_ota),  # noqa: B008
) -> Response:
    path = _resolve_bin(chip, filename)
    if path is None:
        return _not_found()

    total = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path,
            media_type="application/octet-stream",
            headers={"Accept-Ranges": "bytes"},
        )

    parsed = _parse_range(range_header, total)
    if parsed is UNSATISFIABLE:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{total}"},
        )
    if parsed is None:
        # Malformed/multi-range: serve the full bin (matches /stream behavior).
        return FileResponse(
            path,
            media_type="application/octet-stream",
            headers={"Accept-Ranges": "bytes"},
        )

    start, end = parsed.start, parsed.end
    with path.open("rb") as f:
        f.seek(start)
        chunk = f.read(end - start + 1)
    return Response(
        chunk,
        status_code=206,
        media_type="application/octet-stream",
        headers={
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(chunk)),
        },
    )
