"""Browser session: the user JWT in an httpOnly cookie, plus a CSRF value
derived from it that the page echoes back in a header on writes."""

import base64
import hashlib
import hmac

from fastapi import Request, Response

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
