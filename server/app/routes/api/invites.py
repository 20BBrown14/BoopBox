"""The public invite page: check a code, then redeem it for a local login.

No session exists yet, so both routes are guarded by require_json_same_origin.
Every bad code gets the same response, whether unknown, used, revoked, expired,
oversized, or for a deleted or disabled user. There is no rate limit: codes are
256-bit random values, so guessing isn't practical.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.invites import CODE_MAX, hash_code
from app.auth.login import client_address
from app.auth.passwords import (
    hash_password,
    normalize_password,
    normalize_username,
    password_problem,
    username_problem,
)
from app.auth.session import require_json_same_origin
from app.db import invites, users
from app.db.timestamps import timestamp
from app.errors import ApiError, ErrorCode
from app.routes.api.auth import SessionOut, set_cookie_session
from app.validation import require

router = APIRouter(dependencies=[Depends(require_json_same_origin)])


class InviteCheckRequest(BaseModel):
    code: str


class InviteCheckOut(BaseModel):
    display_name: str


class InviteRedeemRequest(BaseModel):
    code: str
    username: str
    password: str


def _invalid_code() -> ApiError:
    return ApiError(ErrorCode.not_found, "invalid or expired invite", field="code")


async def _valid(request: Request, code: str) -> invites.InviteMatch:
    if len(code) > CODE_MAX:
        raise _invalid_code()
    async with request.app.state.db.read() as conn:
        match = await invites.find_valid(conn, hash_code(code), timestamp())
    if match is None:
        raise _invalid_code()
    return match


@router.post("/invites/check")
async def check_invite(request: Request, body: InviteCheckRequest) -> InviteCheckOut:
    match = await _valid(request, body.code)
    return InviteCheckOut(display_name=match.display_name)


@router.post("/invites/redeem")
async def redeem_invite(request: Request, body: InviteRedeemRequest) -> JSONResponse:
    """Counts as a login: the history row and last_login_at commit together
    with the redemption."""
    username = normalize_username(body.username)
    require(username_problem(username), "username")
    password = normalize_password(body.password)
    require(password_problem(password), "password")

    # Checked before hashing so a bad code costs no Argon2 work, and checked
    # again inside the transaction.
    await _valid(request, body.code)
    secret_hash = await hash_password(password)

    settings = await request.app.state.settings.snapshot()
    now = timestamp()
    async with request.app.state.db.write() as conn:
        try:
            result = await invites.redeem_local(
                conn, hash_code(body.code), username, secret_hash, now
            )
        except invites.UsernameTaken:
            raise ApiError(
                ErrorCode.conflict, "username is taken", field="username"
            ) from None
        if result is None:
            raise _invalid_code()
        await users.add_history(
            conn,
            at=now,
            outcome="success",
            provider="local",
            user_id=result.user_id,
            identifier=body.username,
            client_ip=client_address(
                request.client.host if request.client else None,
                request.headers.get("x-forwarded-for"),
                settings["auth.trust_forwarded_header"],
            ),
            user_agent=request.headers.get("user-agent"),
        )
        await users.set_last_login(conn, result.user_id, now)

    response = JSONResponse(SessionOut(must_change_password=False).model_dump())
    set_cookie_session(
        request, response, result.user_id, result.token_version, settings
    )
    return response
