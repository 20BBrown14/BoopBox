"""Local username and password login, for scripts (bearer token) and for the
browser (session cookie), plus logout, logging out everywhere and changing
your own password."""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.deps import (
    AuthError,
    require_user,
    require_user_allow_password_change,
)
from app.auth.jwt import issue_user_jwt, now_seconds
from app.auth.login import client_address, login_local
from app.auth.passwords import (
    hash_password,
    normalize_password,
    password_problem,
    verify_password,
)
from app.auth.session import (
    clear_session,
    request_is_https,
    require_json_same_origin,
    set_session,
)
from app.db import users
from app.db.timestamps import timestamp
from app.db.users import AuthUser
from app.errors import ApiError, ErrorCode

router = APIRouter()


class TokenRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class SessionOut(BaseModel):
    must_change_password: bool


def _issue(user_id: int, version: int, settings: dict) -> tuple[str, int]:
    ttl = settings["auth.token_lifetime_hours"] * 3600
    token = issue_user_jwt(
        user_id,
        version=version,
        secret=settings["secrets.auth_token"],
        ttl_seconds=ttl,
        now=now_seconds(),
    )
    return token, ttl


def _token_response(user_id: int, version: int, settings: dict, must_change: bool):
    token, ttl = _issue(user_id, version, settings)
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ttl,
            "must_change_password": must_change,
        }
    )


async def _check_login(request: Request, body: TokenRequest) -> tuple[AuthUser, dict]:
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
        raise ApiError(
            ErrorCode.unauthorized,
            "invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user, settings


def _set_cookie_session(
    request: Request, response: Response, user_id: int, version: int, settings: dict
) -> None:
    token, ttl = _issue(user_id, version, settings)
    set_session(
        response,
        token,
        secret=settings["secrets.auth_token"],
        max_age=ttl,
        secure=request_is_https(request, settings["auth.trust_forwarded_header"]),
    )


async def _reissue(request: Request, user_id: int, version: int) -> JSONResponse:
    """A new credential for the new token version, in the form the caller used."""
    settings = await request.app.state.settings.snapshot()
    if request.state.auth_via != "cookie":
        return _token_response(user_id, version, settings, False)
    response = JSONResponse(SessionOut(must_change_password=False).model_dump())
    _set_cookie_session(request, response, user_id, version, settings)
    return response


@router.post("/auth/token", dependencies=[Depends(require_json_same_origin)])
async def auth_token(request: Request, body: TokenRequest) -> JSONResponse:
    user, settings = await _check_login(request, body)
    return _token_response(
        user.id, user.token_version, settings, user.must_change_password
    )


@router.post("/auth/login", dependencies=[Depends(require_json_same_origin)])
async def auth_login(
    request: Request, response: Response, body: TokenRequest
) -> SessionOut:
    user, settings = await _check_login(request, body)
    _set_cookie_session(request, response, user.id, user.token_version, settings)
    return SessionOut(must_change_password=user.must_change_password)


@router.post("/auth/logout", status_code=204)
async def auth_logout(
    request: Request,
    _user: AuthUser = Depends(require_user_allow_password_change),  # noqa: B008
) -> Response:
    response = Response(status_code=204)
    if request.state.auth_via == "cookie":
        trust = await request.app.state.settings.get("auth.trust_forwarded_header")
        clear_session(response, secure=request_is_https(request, trust))
    return response


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
        raise ApiError(
            ErrorCode.forbidden,
            "current password is incorrect",
            field="current_password",
        )

    new_password = normalize_password(body.new_password)
    problem = password_problem(new_password)
    if problem is not None:
        raise ApiError(ErrorCode.invalid_request, problem, field="new_password")

    new_hash = await hash_password(new_password)
    async with db.write() as conn:
        version = await users.change_password(
            conn, user.id, user.identity_id, new_hash, timestamp()
        )
    return await _reissue(request, user.id, version)


@router.post("/auth/logout-all")
async def logout_all(
    request: Request,
    user: AuthUser = Depends(require_user),  # noqa: B008
) -> JSONResponse:
    """Revoke every session of this user, then log this one back in."""
    async with request.app.state.db.write() as conn:
        version = await users.bump_token_version(conn, user.id)
    return await _reissue(request, user.id, version)
