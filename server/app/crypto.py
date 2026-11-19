"""Keyring encryption for secrets stored in the database.

Format: v1:<kid>:<base64url(nonce || ciphertext)>, AES-256-GCM, with the row's
identity bound in as associated data.
"""

import base64
import binascii
import hashlib
import logging
import os
import stat
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Environment

log = logging.getLogger(__name__)

_VERSION = "v1"
_NONCE_BYTES = 12
KEY_BYTES = 32


class KeyringError(RuntimeError):
    pass


class DecryptError(RuntimeError):
    pass


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:8]


def setting_aad(key: str) -> str:
    return f"settings:{key}"


def source_aad(source_id: int) -> str:
    return f"media_sources:{source_id}"


def kid_of(value: str) -> str:
    version, kid, _ = _split(value)
    return kid


def _split(value: str) -> tuple[str, str, str]:
    parts = value.split(":", 2)
    if len(parts) != 3 or parts[0] != _VERSION:
        raise DecryptError("not a v1 ciphertext")
    return parts[0], parts[1], parts[2]


class Keyring:
    """The first key is active and encrypts; the rest only decrypt."""

    def __init__(self, keys: list[bytes]) -> None:
        if not keys:
            raise KeyringError("the keyring has no keys")
        for key in keys:
            if len(key) != KEY_BYTES:
                raise KeyringError(f"every key must be {KEY_BYTES} bytes")
        self._keys = {key_id(k): k for k in keys}
        self.active_kid = key_id(keys[0])

    @property
    def kids(self) -> set[str]:
        return set(self._keys)

    def encrypt(self, plaintext: str, aad: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        sealed = AESGCM(self._keys[self.active_kid]).encrypt(
            nonce, plaintext.encode("utf-8"), aad.encode("utf-8")
        )
        return f"{_VERSION}:{self.active_kid}:{_b64url_encode(nonce + sealed)}"

    def decrypt(self, value: str, aad: str) -> str:
        _, kid, body = _split(value)
        key = self._keys.get(kid)
        if key is None:
            raise DecryptError(f"key {kid} is not in the keyring")
        try:
            raw = _b64url_decode(body)
            plaintext = AESGCM(key).decrypt(
                raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], aad.encode("utf-8")
            )
        except (InvalidTag, binascii.Error, ValueError) as err:
            raise DecryptError("ciphertext failed to decrypt") from err
        return plaintext.decode("utf-8")

    @classmethod
    def from_env(cls, env: Environment) -> "Keyring":
        if env.secret_keys_file:
            path = Path(env.secret_keys_file)
            try:
                text = path.read_text()
            except OSError as err:
                raise KeyringError(
                    f"BOOPBOX_SECRET_KEYS_FILE can't be read: {err}"
                ) from err
            if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                log.warning("keyring file %s is readable by other users", path)
            lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            source = "BOOPBOX_SECRET_KEYS_FILE"
        elif env.secret_key:
            lines = [env.secret_key.strip()]
            source = "BOOPBOX_SECRET_KEY"
        else:
            raise KeyringError(
                "no encryption key: set BOOPBOX_SECRET_KEY or BOOPBOX_SECRET_KEYS_FILE"
            )
        keys = []
        for number, line in enumerate(lines, start=1):
            try:
                key = _b64url_decode(line)
            except (binascii.Error, ValueError):
                key = b""
            if len(key) != KEY_BYTES:
                raise KeyringError(
                    f"{source}: key {number} is not {KEY_BYTES} base64url-encoded bytes"
                )
            keys.append(key)
        return cls(keys)
