"""POST /auth/token: log in with a local username and password.
POST /auth/password: change your own password (required after first login)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.deps import AuthError, require_user_allow_password_change
from app.auth.jwt import issue_user_jwt, now_seconds
from app.auth.login import client_address, login_local
from app.auth.passwords import (
    hash_password,
    normalize_password,
    password_problem,
    verify_password,
)
from app.db import users
from app.db.timestamps import timestamp
from app.db.users import AuthUser
from app.errors import ErrorCode, http_error

router = APIRouter()


class TokenRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


def _token_response(user_id: int, version: int, settings: dict, must_change: bool):
    ttl = settings["auth.token_lifetime_hours"] * 3600
    token = issue_user_jwt(
        user_id,
        version=version,
        secret=settings["secrets.auth_token"],
        ttl_seconds=ttl,
        now=now_seconds(),
    )
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ttl,
            "must_change_password": must_change,
        }
    )


@router.post("/auth/token")
async def auth_token(request: Request, body: TokenRequest) -> JSONResponse:
    settings = await request.app.state.settings.snapshot()
    user = await login_local(
        request.app.state.db,
        settings,
        username=body.username,
        password=body.password,
        client_ip=client_address(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
            settings["auth.trust_forwarded_header"],
        ),
        user_agent=request.headers.get("user-agent"),
    )
    if user is None:
        err_body, status = http_error(
            ErrorCode.unauthorized, "invalid username or password"
        )
        return JSONResponse(
            err_body, status_code=status, headers={"WWW-Authenticate": "Bearer"}
        )
    return _token_response(
        user.id, user.token_version, settings, user.must_change_password
    )


@router.post("/auth/password")
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    user: AuthUser = Depends(require_user_allow_password_change),  # noqa: B008
) -> JSONResponse:
    db = request.app.state.db
    if user.identity_id is None:
        raise AuthError(ErrorCode.forbidden)
    async with db.read() as conn:
        stored = await users.get_secret_hash(conn, user.identity_id)
    if stored is None or not await verify_password(
        stored, normalize_password(body.current_password)
    ):
        raise AuthError(ErrorCode.forbidden)

    new_password = normalize_password(body.new_password)
    problem = password_problem(new_password)
    if problem is not None:
        err_body, status = http_error(ErrorCode.invalid_request, problem)
        return JSONResponse(err_body, status_code=status)

    new_hash = await hash_password(new_password)
    async with db.write() as conn:
        version = await users.change_password(
            conn, user.id, user.identity_id, new_hash, timestamp()
        )
    settings = await request.app.state.settings.snapshot()
    return _token_response(user.id, version, settings, False)
