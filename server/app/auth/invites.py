"""Invite codes: 256-bit random values, stored only as a SHA-256 hash. A fast
hash is enough for high-entropy secrets; Argon2id is for passwords."""

import secrets

from app.security import hash_secret

CODE_MAX = 128


def new_code() -> str:
    return secrets.token_urlsafe(32)


def hash_code(code: str) -> str:
    return hash_secret(code)
