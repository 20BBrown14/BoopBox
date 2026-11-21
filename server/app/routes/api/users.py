"""Read routes for the users screens. Everything here needs `users.manage`."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import require_permission
from app.db import users
from app.db.timestamps import timestamp
from app.errors import ApiError, ErrorCode
from app.routes.api.me import LoginOut
from app.routes.api.pagination import Page, PageParams, page_params

router = APIRouter(dependencies=[Depends(require_permission("users.manage"))])


class UserOut(BaseModel):
    id: int
    display_name: str
    email: str | None
    is_owner: bool
    status: Literal["active", "pending", "disabled"]
    login: LoginOut | None
    last_login_at: str | None
    locked: bool
    created_at: str


class UserDetailOut(UserOut):
    open_invite_expires_at: str | None


class UserPage(Page[UserOut]):
    pass


def _user_fields(user: users.UserSummary) -> dict:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "is_owner": user.is_owner,
        "status": user.status,
        "login": (
            None
            if user.provider is None
            else LoginOut(
                provider=user.provider, username=user.username, label=user.label
            )
        ),
        "last_login_at": user.last_login_at,
        "locked": user.locked,
        "created_at": user.created_at,
    }


@router.get("/users")
async def list_users(
    request: Request,
    page: PageParams = Depends(page_params),  # noqa: B008
) -> UserPage:
    async with request.app.state.db.read() as conn:
        total = await users.count_users(conn)
        rows = await users.list_users(
            conn, timestamp(), limit=page.limit, offset=page.offset
        )
    return UserPage(
        items=[UserOut(**_user_fields(row)) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/users/{user_id}")
async def get_user(request: Request, user_id: int) -> UserDetailOut:
    async with request.app.state.db.read() as conn:
        user = await users.get_user(conn, user_id, timestamp())
    if user is None:
        raise ApiError(ErrorCode.not_found)
    return UserDetailOut(
        **_user_fields(user), open_invite_expires_at=user.open_invite_expires_at
    )
