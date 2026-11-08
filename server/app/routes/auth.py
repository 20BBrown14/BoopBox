"""POST /auth/token — exchange the configured user credential for a JWT.

The config-file auth has one user: the credential in `BOOPBOX_AUTH_*`. A correct
username+password returns a short-lived bearer token the API verifies on
user-facing routes. Wrong or unconfigured credentials return a generic 401 that
does not distinguish "no such user" from "bad password".
"""

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.jwt import issue_user_jwt, now_seconds
from app.config import get_settings
from app.errors import ErrorCode, http_error

router = APIRouter()


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def _credentials_match(username: str, password: str, settings) -> bool:
    """Constant-time credential check. False when auth is unconfigured, so a
    blank-credential deployment rejects every login rather than accepting one."""
    if not settings.auth_username or not settings.auth_password:
        return False
    user_ok = hmac.compare_digest(username, settings.auth_username)
    pass_ok = hmac.compare_digest(password, settings.auth_password)
    return user_ok and pass_ok


@router.post("/auth/token")
async def auth_token(request: Request, body: TokenRequest) -> JSONResponse:
    settings = get_settings()
    if not _credentials_match(body.username, body.password, settings):
        err_body, status = http_error(ErrorCode.unauthorized)
        return JSONResponse(
            err_body,
            status_code=status,
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = now_seconds()
    token = issue_user_jwt(
        body.username,
        secret=settings.jwt_secret,
        ttl_seconds=settings.jwt_ttl_seconds,
        now=now,
    )
    resp = TokenResponse(access_token=token, expires_in=settings.jwt_ttl_seconds)
    return JSONResponse(resp.model_dump())
