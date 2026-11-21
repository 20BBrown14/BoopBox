"""User management routes. Everything here needs `users.manage`."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.auth import require_permission
from app.auth.invites import hash_code, new_code
from app.db import invites, users
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


class InviteOut(BaseModel):
    code: str
    url: str
    expires_at: str


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


@router.post("/users/{user_id}/invites", status_code=201)
async def issue_invite(
    request: Request,
    response: Response,
    user_id: int,
    actor: AuthUser = Depends(_require_manage),  # noqa: B008
) -> InviteOut:
    """For a pending user, or an active one who lost access (a re-invite). The
    code is only ever in this response."""
    settings = await request.app.state.settings.snapshot()
    now_dt = datetime.now(UTC)
    now = timestamp(now_dt)
    expires_at = timestamp(now_dt + timedelta(days=settings["invites.expiry_days"]))
    code = new_code()
    async with request.app.state.db.write() as conn:
        user = await _existing(conn, user_id, now)
        # Otherwise anyone with users.manage could take over the owner's login.
        if user.is_owner:
            raise ApiError(ErrorCode.invalid_request, "the owner can't be invited")
        if user.status == "disabled":
            raise ApiError(
                ErrorCode.invalid_request, "enable the user before inviting them"
            )
        await invites.issue(conn, user_id, hash_code(code), expires_at, actor.id, now)
    response.headers["Cache-Control"] = "no-store"
    return InviteOut(
        code=code,
        url=f"{settings['public_base_url']}/invite#code={code}",
        expires_at=expires_at,
    )


@router.delete("/users/{user_id}/invites", status_code=204)
async def revoke_invites(
    request: Request,
    user_id: int,
    actor: AuthUser = Depends(_require_manage),  # noqa: B008
) -> Response:
    now = timestamp()
    async with request.app.state.db.write() as conn:
        await _existing(conn, user_id, now)
        await invites.revoke_open(conn, user_id, actor.id, now)
    return Response(status_code=204)


@router.post("/users/{user_id}/unlock", status_code=204)
async def unlock_user(request: Request, user_id: int) -> Response:
    async with request.app.state.db.write() as conn:
        await _existing(conn, user_id, timestamp())
        await users.clear_lock(conn, user_id)
    return Response(status_code=204)


@router.post("/users/{user_id}/logout-all", status_code=204)
async def logout_user_everywhere(request: Request, user_id: int) -> Response:
    """Allowed on yourself too, which ends this session as well; the account
    page's /api/auth/logout-all is the one that keeps it."""
    async with request.app.state.db.write() as conn:
        await _existing(conn, user_id, timestamp())
        await users.bump_token_version(conn, user_id)
    return Response(status_code=204)


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
