"""GET /firmware/manifest.json — the generated ESP-Web-Tools manifest.

The bins themselves are served by a StaticFiles mount at /firmware (Range out of
the box). This generated route is registered BEFORE that mount so it wins over
any stray on-disk manifest.json in the firmware dir.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/firmware/manifest.json")
async def firmware_manifest(request: Request) -> JSONResponse:
    cache = request.app.state.firmware
    return JSONResponse(cache.manifest(), media_type="application/json")
