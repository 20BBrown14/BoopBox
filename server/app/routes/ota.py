"""POST /ota/update — trigger the OTA version-check path (admin/fleet action).

Triggers a `get_version` query, not a forced flash: the normal version-check
path decides whether an update actually happens. An absent `device_id`
broadcasts the query to the fleet; a present one targets that device (404 if the
device id is unknown).

Behind user auth (JWT bearer): a human/UI action, never a box-facing path. A
device credential does not satisfy `require_user`.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import require_user

router = APIRouter()


class OtaUpdateRequest(BaseModel):
    # Absent = broadcast query to the fleet; present = that one device.
    device_id: str | None = None


@router.post("/ota/update", dependencies=[Depends(require_user)])
async def ota_update(
    request: Request, body: OtaUpdateRequest | None = None
) -> dict[str, str]:
    body = body or OtaUpdateRequest()
    policy = request.app.state.ota_policy

    if body.device_id is not None:
        device = await request.app.state.devices.get(body.device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="unknown device")
        await policy.query_version(body.device_id)
        return {"status": "queried", "device_id": body.device_id}

    await policy.query_version()
    return {"status": "queried", "device_id": "all"}
