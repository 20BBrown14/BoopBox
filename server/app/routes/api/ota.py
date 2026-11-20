"""POST /api/ota/update — trigger the OTA version-check path (admin/fleet action).

Triggers a `get_version` query, not a forced flash: the normal version-check
path decides whether an update actually happens. An absent `device_id`
broadcasts the query to the fleet; a present one targets that device (404 if the
device id is unknown).

Needs the `ota.manage` permission: a human/UI action, never a box-facing path.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import require_permission
from app.db import devices
from app.errors import ApiError, ErrorCode

router = APIRouter()


class OtaUpdateRequest(BaseModel):
    # Absent = broadcast query to the fleet; present = that one device.
    device_id: str | None = None


@router.post("/ota/update", dependencies=[Depends(require_permission("ota.manage"))])
async def ota_update(
    request: Request, body: OtaUpdateRequest | None = None
) -> dict[str, str]:
    body = body or OtaUpdateRequest()
    policy = request.app.state.ota_policy

    if body.device_id is not None:
        async with request.app.state.db.read() as conn:
            device = await devices.get(conn, body.device_id)
        if device is None:
            raise ApiError(ErrorCode.not_found, "unknown device", field="device_id")
        await policy.query_version(body.device_id)
        return {"status": "queried", "device_id": body.device_id}

    await policy.query_version()
    return {"status": "queried", "device_id": "all"}
