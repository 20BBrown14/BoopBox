"""Hashing + constant-time verification for device auth secrets.

Device secrets (the OTA Basic password, the device API token) are high-entropy
random values, so a single-pass SHA-256 is the right fit — a slow password KDF
only buys resistance against brute-forcing low-entropy human passwords, which
these are not. Stored as the hex digest; compared in constant time.
"""

import hashlib
import hmac


def hash_secret(plaintext: str) -> str:
    """SHA-256 hex digest of a secret, suitable for storage."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def verify_secret(plaintext: str, stored_hash: str | None) -> bool:
    """Constant-time check of `plaintext` against a stored hex digest.

    False for an absent stored hash (device has no secret provisioned) or an
    empty plaintext, so a missing credential can never match.
    """
    if not stored_hash or not plaintext:
        return False
    return hmac.compare_digest(hash_secret(plaintext), stored_hash)
