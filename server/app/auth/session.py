"""Browser session: the user JWT in an httpOnly cookie, plus a CSRF value
derived from it that the page echoes back in a header on writes."""

import base64
import hashlib
import hmac
from urllib.parse import urlsplit

from fastapi import Request, Response

from app.errors import ApiError, ErrorCode

SESSION_COOKIE = "boopbox_session"
CSRF_COOKIE = "boopbox_csrf"
CSRF_HEADER = "x-csrf-token"

_SESSION_PATH = "/api"
_CSRF_PATH = "/"


def request_is_https(request: Request, trust_forwarded: bool) -> bool:
    """The rightmost X-Forwarded-Proto entry is the one the trusted proxy added."""
    if trust_forwarded:
        forwarded = request.headers.get("x-forwarded-proto", "")
        last = forwarded.split(",")[-1].strip().lower()
        if last:
            return last == "https"
    return request.url.scheme == "https"


def csrf_token(jwt: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), b"csrf:" + jwt.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def csrf_matches(jwt: str, secret: str, presented: str | None) -> bool:
    if not presented:
        return False
    return hmac.compare_digest(
        csrf_token(jwt, secret).encode("ascii"), presented.encode("utf-8")
    )


def set_session(
    response: Response, jwt: str, *, secret: str, max_age: int, secure: bool
) -> None:
    """`secret` is the JWT signing secret; the CSRF value is derived from it."""
    response.set_cookie(
        SESSION_COOKIE,
        jwt,
        max_age=max_age,
        path=_SESSION_PATH,
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    # Readable by scripts on purpose: the page copies it into CSRF_HEADER.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token(jwt, secret),
        max_age=max_age,
        path=_CSRF_PATH,
        secure=secure,
        httponly=False,
        samesite="strict",
    )


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _host_port(netloc: str, scheme: str) -> tuple[str, int | None] | None:
    try:
        parts = urlsplit(f"//{netloc}")
        port = parts.port
    except ValueError:
        return None
    if not parts.hostname:
        return None
    return parts.hostname, port or _DEFAULT_PORTS.get(scheme)


def same_origin(origin: str, host: str) -> bool:
    """Host and port only. Behind a TLS proxy that isn't trusted the app sees
    http, so the scheme can't be compared. A missing port is the default for
    the Origin's scheme on both sides."""
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in _DEFAULT_PORTS:
        return False
    theirs = _host_port(parsed.netloc, parsed.scheme)
    ours = _host_port(host, parsed.scheme)
    return theirs is not None and theirs == ours


async def require_json_same_origin(request: Request) -> None:
    """For unauthenticated writes, which have no session to bind CSRF to.
    A cross-site HTML form can't send application/json, and a cross-site
    fetch carries a foreign Origin."""
    content_type = request.headers.get("content-type", "")
    if content_type.split(";")[0].strip().lower() != "application/json":
        raise ApiError(ErrorCode.invalid_request, "expected application/json")
    origin = request.headers.get("origin")
    if origin is None:
        return
    host = request.headers.get("host", "")
    if await request.app.state.settings.get("auth.trust_forwarded_header"):
        forwarded = request.headers.get("x-forwarded-host", "")
        host = forwarded.split(",")[-1].strip() or host
    if not same_origin(origin, host):
        raise ApiError(ErrorCode.forbidden, "cross-origin request refused")


def clear_session(response: Response, *, secure: bool) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path=_SESSION_PATH,
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE, path=_CSRF_PATH, secure=secure, samesite="strict"
    )
