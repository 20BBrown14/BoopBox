"""User login tokens (HS256). A token carries the user id and the user's
token_version when it was issued; bumping the version revokes it."""

import time

import jwt

# Only tokens minted by issue_user_jwt carry this audience.
AUDIENCE = "boopbox-user"
_ALGORITHM = "HS256"


class InvalidToken(Exception):
    pass


def issue_user_jwt(
    user_id: int, *, version: int, secret: str, ttl_seconds: int, now: int
) -> str:
    payload = {
        "sub": str(user_id),
        "ver": version,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_user_jwt(token: str, *, secret: str) -> tuple[int, int]:
    """Return (user_id, token_version) or raise InvalidToken."""
    if not secret:
        raise InvalidToken("user auth not configured")
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            audience=AUDIENCE,
            options={"require": ["exp", "sub", "aud", "ver"]},
        )
        user_id = int(payload["sub"])
        version = payload["ver"]
    except (jwt.InvalidTokenError, ValueError) as err:
        raise InvalidToken(str(err)) from err
    if not isinstance(version, int) or isinstance(version, bool):
        raise InvalidToken("bad token version")
    return user_id, version


def now_seconds() -> int:
    return int(time.time())
