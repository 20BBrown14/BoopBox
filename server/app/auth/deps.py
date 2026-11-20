"""FastAPI auth dependencies. Each accepts only its own credential type:

- `require_user`: user JWT in `Authorization: Bearer`, or the session cookie
  with a CSRF header on writes. UI/human actions.
- `require_device_ota`: device OTA secret as the HTTP Basic password.
- `require_device_api`: device token in `Authorization: Bearer` plus
  `X-Device-Id`.

401 means a missing or malformed credential, 403 a rejected one.
"""

import base64
import binascii

from fastapi import Depends, Request

from app.auth.jwt import InvalidToken, verify_user_jwt
from app.auth.session import CSRF_HEADER, SESSION_COOKIE, csrf_matches
from app.db import devices
from app.db import users as user_rows
from app.db.users import AuthUser
from app.errors import ApiError, ErrorCode
from app.permissions import can
from app.security import verify_secret
from app.types.device import Device

_MESSAGES = {
    ErrorCode.unauthorized: "authentication required",
    ErrorCode.forbidden: "not allowed",
}

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuthError(ApiError):
    def __init__(self, code: ErrorCode, *, scheme: str | None = None) -> None:
        super().__init__(
            code,
            _MESSAGES[code],
            headers={"WWW-Authenticate": scheme} if scheme else None,
        )


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError(ErrorCode.unauthorized, scheme="Bearer")
    return token.strip()


def _basic(request: Request) -> tuple[str, str]:
    header = request.headers.get("authorization", "")
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded.strip():
        raise AuthError(ErrorCode.unauthorized, scheme="Basic")
    try:
        raw = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise AuthError(ErrorCode.unauthorized, scheme="Basic") from None
    username, sep, password = raw.partition(":")
    if not sep:
        raise AuthError(ErrorCode.unauthorized, scheme="Basic")
    return username, password


def _user_token(request: Request) -> tuple[str, str]:
    """(jwt, how it arrived). Any Authorization header wins over the cookie,
    so a malformed one fails rather than falling back."""
    if "authorization" in request.headers:
        return _bearer(request), "bearer"
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        raise AuthError(ErrorCode.unauthorized, scheme="Bearer")
    return cookie, "cookie"


async def _authenticate(request: Request) -> AuthUser:
    token, via = _user_token(request)
    secret = await request.app.state.settings.get("secrets.auth_token")
    try:
        user_id, version = verify_user_jwt(token, secret=secret)
    except InvalidToken:
        raise AuthError(ErrorCode.forbidden) from None
    # A browser attaches cookies cross-site on its own, but never this header.
    if (
        via == "cookie"
        and request.method in _WRITE_METHODS
        and not csrf_matches(token, secret, request.headers.get(CSRF_HEADER))
    ):
        raise AuthError(ErrorCode.forbidden)
    async with request.app.state.db.read() as conn:
        user = await user_rows.get_active(conn, user_id)
    if user is None or user.token_version != version:
        raise AuthError(ErrorCode.forbidden)
    request.state.auth_via = via
    return user


async def require_user_allow_password_change(request: Request) -> AuthUser:
    """Like require_user, but also admits a user who must change their
    password. Only the change-password route uses it."""
    return await _authenticate(request)


async def require_user(request: Request) -> AuthUser:
    user = await _authenticate(request)
    if user.must_change_password:
        raise AuthError(ErrorCode.forbidden)
    return user


def require_permission(permission: str, device_param: str | None = None):
    """Dependency factory: a user holding `permission`, globally or on the
    device named by the `device_param` path parameter."""

    async def dependency(
        request: Request,
        user: AuthUser = Depends(require_user),  # noqa: B008
    ) -> AuthUser:
        device_id = request.path_params.get(device_param) if device_param else None
        async with request.app.state.db.read() as conn:
            allowed = await can(conn, user, permission, device_id)
        if not allowed:
            raise AuthError(ErrorCode.forbidden)
        return user

    return dependency


async def _load_live_device(request: Request, device_id: str) -> Device:
    async with request.app.state.db.read() as conn:
        device = await devices.get(conn, device_id)
    if device is None or device.revoked:
        raise AuthError(ErrorCode.forbidden)
    return device


async def require_device_ota(request: Request) -> Device:
    """Basic username is the device id, password the flashed OTA secret."""
    device_id, secret = _basic(request)
    device = await _load_live_device(request, device_id)
    if not verify_secret(secret, device.ota_secret_hash):
        raise AuthError(ErrorCode.forbidden, scheme="Basic")
    return device


async def require_device_api(request: Request) -> Device:
    token = _bearer(request)
    device_id = request.headers.get("x-device-id", "").strip()
    if not device_id:
        raise AuthError(ErrorCode.unauthorized, scheme="Bearer")
    device = await _load_live_device(request, device_id)
    if not verify_secret(token, device.device_token_hash):
        raise AuthError(ErrorCode.forbidden, scheme="Bearer")
    return device
