"""GET /api/me: who is logged in, and what the UI should show them. The
permissions only hide UI; every route still checks on its own."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_user_allow_password_change
from app.db import permissions as grant_rows
from app.db import users
from app.db.users import AuthUser
from app.permissions import CATALOG

router = APIRouter()


class LoginOut(BaseModel):
    provider: str
    username: str | None
    label: str | None


class PermissionsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    global_: list[str] = Field(alias="global")
    devices: dict[str, list[str]]


class MeOut(BaseModel):
    id: int
    display_name: str
    is_owner: bool
    must_change_password: bool
    login: LoginOut | None
    permissions: PermissionsOut


@router.get("/me")
async def me(
    request: Request,
    user: AuthUser = Depends(require_user_allow_password_change),  # noqa: B008
) -> MeOut:
    async with request.app.state.db.read() as conn:
        login = await users.get_login(conn, user.id)
        grants = await grant_rows.list_grants(conn, user.id)
    if user.is_owner:
        granted = PermissionsOut(global_=sorted(CATALOG), devices={})
    else:
        granted = PermissionsOut(
            global_=sorted(grants.global_ids),
            devices={
                device_id: sorted(ids)
                for device_id, ids in sorted(grants.devices.items())
            },
        )
    return MeOut(
        id=user.id,
        display_name=user.display_name,
        is_owner=user.is_owner,
        must_change_password=user.must_change_password,
        login=LoginOut(**vars(login)) if login else None,
        permissions=granted,
    )
