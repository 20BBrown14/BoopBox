"""User management routes. Everything here needs `users.manage`."""

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.auth import require_permission
from app.db import users
from app.db.timestamps import timestamp
from app.db.users import AuthUser
from app.errors import ApiError, ErrorCode
from app.routes.api.me import LoginOut
from app.routes.api.pagination import Page, PageParams, page_params
from app.validation import (
    clean,
    email_problem,
    length_problem,
    require,
    single_line_problem,
)

DISPLAY_NAME_MIN, DISPLAY_NAME_MAX = 1, 64

# One callable for the router and the handlers, so FastAPI runs the check once
# per request and hands the handlers the same user.
_require_manage = require_permission("users.manage")

router = APIRouter(dependencies=[Depends(_require_manage)])


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


class UserCreate(BaseModel):
    display_name: str
    email: str | None = None


class UserUpdate(BaseModel):
    # Absent leaves a field alone. The defaults aren't validated, so an explicit
    # null is still rejected for the fields typed without None.
    display_name: str = Field(default=None)
    email: str | None = None
    disabled: bool = Field(default=None)


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


def _detail_out(user: users.UserDetail) -> UserDetailOut:
    return UserDetailOut(
        **_user_fields(user), open_invite_expires_at=user.open_invite_expires_at
    )


def _display_name(raw: str) -> str:
    value = clean(raw)
    require(
        single_line_problem(value)
        or length_problem(value, DISPLAY_NAME_MIN, DISPLAY_NAME_MAX),
        "display_name",
    )
    return value


def _email(raw: str | None) -> str:
    """The cleaned email, or "" for none."""
    value = clean(raw or "")
    if value:
        require(single_line_problem(value) or email_problem(value), "email")
    return value


async def _existing(conn, user_id: int, now: str) -> users.UserDetail:
    user = await users.get_user(conn, user_id, now)
    if user is None:
        raise ApiError(ErrorCode.not_found)
    return user


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


@router.post("/users", status_code=201)
async def create_user(
    request: Request,
    body: UserCreate,
    actor: AuthUser = Depends(_require_manage),  # noqa: B008
) -> UserDetailOut:
    display_name = _display_name(body.display_name)
    email = _email(body.email) or None
    now = timestamp()
    async with request.app.state.db.write() as conn:
        user_id = await users.create_user(conn, display_name, email, actor.id, now)
        user = await _existing(conn, user_id, now)
    return _detail_out(user)


@router.get("/users/{user_id}")
async def get_user(request: Request, user_id: int) -> UserDetailOut:
    async with request.app.state.db.read() as conn:
        user = await _existing(conn, user_id, timestamp())
    return _detail_out(user)


@router.patch("/users/{user_id}")
async def update_user(
    request: Request,
    user_id: int,
    body: UserUpdate,
    actor: AuthUser = Depends(_require_manage),  # noqa: B008
) -> UserDetailOut:
    sent = body.model_fields_set
    changes = users.UserChanges(
        display_name=_display_name(body.display_name)
        if "display_name" in sent
        else None,
        email=_email(body.email) if "email" in sent else None,
        disabled=body.disabled if "disabled" in sent else None,
    )
    now = timestamp()
    async with request.app.state.db.write() as conn:
        user = await _existing(conn, user_id, now)
        if changes.disabled:
            if user.is_owner:
                raise ApiError(
                    ErrorCode.invalid_request,
                    "the owner can't be disabled",
                    field="disabled",
                )
            if user.id == actor.id:
                raise ApiError(
                    ErrorCode.invalid_request,
                    "you can't disable yourself",
                    field="disabled",
                )
        await users.update_user(conn, user_id, changes, actor.id, now)
        user = await _existing(conn, user_id, now)
    return _detail_out(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    request: Request,
    user_id: int,
    actor: AuthUser = Depends(_require_manage),  # noqa: B008
) -> Response:
    now = timestamp()
    async with request.app.state.db.write() as conn:
        user = await _existing(conn, user_id, now)
        if user.is_owner:
            raise ApiError(ErrorCode.invalid_request, "the owner can't be deleted")
        if user.id == actor.id:
            raise ApiError(ErrorCode.invalid_request, "you can't delete yourself")
        await users.delete_user(conn, user_id, actor.id, now)
    return Response(status_code=204)
