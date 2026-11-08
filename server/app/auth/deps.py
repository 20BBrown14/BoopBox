"""FastAPI auth dependencies.

Three principals, strictly separated — each dependency accepts only its own
credential type and rejects the others:

- `require_user`        — user JWT in `Authorization: Bearer <jwt>`. UI/human
                          actions. Never satisfied by a device credential.
- `require_device_ota`  — per-device OTA secret as the HTTP Basic password.
                          Firmware bin fetch only.
- `require_device_api`  — per-device token in `Authorization: Bearer <token>`.
                          Device API routes only.

Failures use the shared error vocabulary: 401 for missing/malformed credentials,
403 for a present-but-rejected credential (bad secret, revoked device).
"""

import base64
import binascii

from fastapi import Request

from app.auth.jwt import InvalidToken, verify_user_jwt
from app.config import get_settings
from app.errors import ErrorCode, http_error
from app.security import verify_secret
from app.types.device import Device


class AuthError(Exception):
    """Raised by a dependency on auth failure; mapped to an HTTP error.

    Carries an ErrorCode so the handler reuses the 401/403 mapping and scrubbed
    messages. `scheme` sets the WWW-Authenticate challenge where one applies.
    """

    def __init__(self, code: ErrorCode, *, scheme: str | None = None) -> None:
        self.code = code
        self.scheme = scheme
        super().__init__(code)


def _bearer(request: Request) -> str:
    """Extract a bearer token, or raise unauthorized."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError(ErrorCode.unauthorized, scheme="Bearer")
    return token.strip()


def _basic(request: Request) -> tuple[str, str]:
    """Extract (username, password) from a Basic header, or raise unauthorized."""
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


async def require_user(request: Request) -> str:
    """Verify a user JWT and return its subject. Rejects any non-user token."""
    token = _bearer(request)
    settings = get_settings()
    try:
        return verify_user_jwt(token, secret=settings.jwt_secret)
    except InvalidToken:
        # A present-but-invalid bearer (bad signature, expired, wrong audience,
        # or a device token) is a rejection, not a malformed request.
        raise AuthError(ErrorCode.forbidden) from None


async def _load_live_device(request: Request, device_id: str) -> Device:
    """Load a device and reject a missing or revoked one as forbidden.

    `revoked` is the server-side kill switch: a revoked device fails immediately
    on every credential it holds, with no box interaction.
    """
    device = await request.app.state.devices.get(device_id)
    if device is None or device.revoked:
        raise AuthError(ErrorCode.forbidden)
    return device


async def require_device_ota(request: Request) -> Device:
    """Verify a device's OTA secret (HTTP Basic password) and return the device.

    Basic username is the device id; the password is the flashed OTA secret,
    checked against the stored hash. Guards the firmware bin fetch only.
    """
    device_id, secret = _basic(request)
    device = await _load_live_device(request, device_id)
    if not verify_secret(secret, device.ota_secret_hash):
        raise AuthError(ErrorCode.forbidden, scheme="Basic")
    return device


async def require_device_api(request: Request) -> Device:
    """Verify a device API token (Authorization: Bearer) and return the device.

    The device id is carried in the `X-Device-Id` header alongside the bearer
    token; the token is checked against the stored device-token hash. This
    header carrier is a provisional seam — the first real device API endpoint
    pins the final convention. Guards device API routes only (never firmware).
    """
    token = _bearer(request)
    device_id = request.headers.get("x-device-id", "").strip()
    if not device_id:
        raise AuthError(ErrorCode.unauthorized, scheme="Bearer")
    device = await _load_live_device(request, device_id)
    if not verify_secret(token, device.device_token_hash):
        raise AuthError(ErrorCode.forbidden, scheme="Bearer")
    return device


def auth_error_response(err: AuthError):
    """Build the JSON error response for an AuthError (shared by the handler)."""
    body, status = http_error(err.code)
    headers = {"WWW-Authenticate": err.scheme} if err.scheme else None
    return body, status, headers
