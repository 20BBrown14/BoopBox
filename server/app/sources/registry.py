"""Media sources built from `media_sources` rows, keyed by id.

A built source is cached and rebuilt when its row changes. Replaced instances
are closed at shutdown rather than immediately, since a stream may still be
reading from one.
"""

import json
import logging
from collections.abc import Callable

from app.crypto import DecryptError, Keyring, source_aad
from app.db import sources as rows
from app.db.engine import Database
from app.db.sources import SourceRow
from app.errors import ErrorCode
from app.types.source import Source, SourceError

log = logging.getLogger(__name__)

# (row, decrypted credential or None, parsed settings) -> Source
SourceBuilder = Callable[[SourceRow, str | None, dict], Source]

_BUILDERS: dict[str, SourceBuilder] = {}


def register_source_type(type_name: str, builder: SourceBuilder) -> None:
    _BUILDERS[type_name] = builder


def known_source_types() -> set[str]:
    return set(_BUILDERS)


def _unavailable(detail: str) -> SourceError:
    return SourceError(ErrorCode.source_unavailable, log_detail=detail)


class SourceRegistry:
    def __init__(self, db: Database, keyring: Keyring) -> None:
        self._db = db
        self._keyring = keyring
        self._cache: dict[int, tuple[tuple, Source]] = {}
        self._retired: list[Source] = []

    async def get(self, source_id: int) -> Source:
        """The source for a live, enabled row. Raises `SourceError`
        (source_unavailable) otherwise."""
        async with self._db.read() as conn:
            row = await rows.get(conn, source_id)
        if row is None:
            raise _unavailable(f"source {source_id} does not exist or is deleted")
        if not row.enabled:
            raise _unavailable(f"source {source_id} is disabled")

        fingerprint = (row.type, row.base_url, row.settings, row.secret_encrypted)
        cached = self._cache.get(source_id)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]

        builder = _BUILDERS.get(row.type)
        if builder is None:
            raise _unavailable(f"source {source_id} has unknown type {row.type!r}")
        try:
            options = json.loads(row.settings)
        except ValueError:
            options = None
        if not isinstance(options, dict):
            raise _unavailable(f"source {source_id} settings are not a JSON object")
        secret = None
        if row.secret_encrypted is not None:
            try:
                secret = self._keyring.decrypt(
                    row.secret_encrypted, source_aad(source_id)
                )
            except DecryptError as err:
                raise _unavailable(f"source {source_id} credential: {err}") from err

        source = builder(row, secret, options)
        if cached is not None:
            self._retired.append(cached[1])
        self._cache[source_id] = (fingerprint, source)
        return source

    async def aclose(self) -> None:
        for source in [*self._retired, *(s for _, s in self._cache.values())]:
            closer = getattr(source, "aclose", None)
            if closer is not None:
                try:
                    await closer()
                except Exception:
                    log.exception("closing a media source failed")
        self._cache.clear()
        self._retired.clear()
