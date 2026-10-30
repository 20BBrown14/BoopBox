"""User-auth JWT mint + verify (HS256).

The UI/API authenticates a user against the configured credential and receives a
short-lived token signed with `jwt_secret`. The token carries a fixed audience
(`AUDIENCE`) so a token minted for any other purpose can never satisfy user
auth; verification pins the algorithm and required claims.
"""

import time

import jwt

# Pins what a user token is for. Verification requires this audience, so only
# tokens issued by issue_user_jwt verify — nothing else is accepted as a user.
AUDIENCE = "boopbox-user"
_ALGORITHM = "HS256"


class InvalidToken(Exception):
    """A token failed verification (missing, malformed, expired, or wrong aud)."""


def issue_user_jwt(subject: str, *, secret: str, ttl_seconds: int, now: int) -> str:
    """Mint a user token for `subject`, expiring `ttl_seconds` after `now`."""
    payload = {
        "sub": subject,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_user_jwt(token: str, *, secret: str) -> str:
    """Verify a user token and return its subject, or raise InvalidToken.

    Signature, expiry, and audience are all enforced (PyJWT validates `exp` and
    `aud` when given). A blank secret is treated as misconfiguration and rejects
    everything rather than verifying against an empty key.
    """
    if not secret:
        raise InvalidToken("user auth not configured")
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            audience=AUDIENCE,
            options={"require": ["exp", "sub", "aud"]},
        )
    except jwt.InvalidTokenError as err:
        raise InvalidToken(str(err)) from err
    return payload["sub"]


def now_seconds() -> int:
    return int(time.time())
