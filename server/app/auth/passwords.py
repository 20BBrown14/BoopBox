import asyncio
import re
import secrets
import unicodedata
from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

USERNAME_MIN, USERNAME_MAX = 3, 32
PASSWORD_MIN, PASSWORD_MAX = 12, 128
_USERNAME_RE = re.compile(r"[a-z0-9._-]+")

_hasher = PasswordHasher()


def normalize_username(raw: str) -> str:
    return unicodedata.normalize("NFC", raw.strip()).lower()


def username_problem(username: str) -> str | None:
    if not USERNAME_MIN <= len(username) <= USERNAME_MAX:
        return f"username must be {USERNAME_MIN} to {USERNAME_MAX} characters"
    if not _USERNAME_RE.fullmatch(username):
        return "username may only contain a-z, 0-9, '.', '_' and '-'"
    return None


def normalize_password(raw: str) -> str:
    # Normalized but not trimmed: spaces are legitimate password characters.
    return unicodedata.normalize("NFC", raw)


def password_problem(password: str) -> str | None:
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        return f"password must be {PASSWORD_MIN} to {PASSWORD_MAX} characters"
    return None


@cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(16))


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


def _verify(stored: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored or _dummy_hash(), password) and stored is not None
    except (VerificationError, InvalidHashError):
        return False


async def verify_password(stored: str | None, password: str) -> bool:
    """With no stored hash this still runs a full check, so timing doesn't
    reveal whether the account exists."""
    if len(password) > PASSWORD_MAX:
        password = password[: PASSWORD_MAX + 1]
    return await asyncio.to_thread(_verify, stored, password)
