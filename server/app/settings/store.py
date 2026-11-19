"""Effective setting values: environment, then database row, then default."""

import json
import logging
import secrets
from pathlib import Path
from typing import Any

from app.config import RESERVED_ENV_NAMES
from app.crypto import DecryptError, Keyring, setting_aad
from app.db import settings as rows
from app.db.engine import Database
from app.db.timestamps import timestamp
from app.settings.registry import REGISTRY, Setting, SettingError

log = logging.getLogger(__name__)


def parse_env_overrides(raw_env: dict[str, str]) -> dict[str, Any]:
    """Validate every BOOPBOX_* variable that names a setting.

    An empty variable counts as unset. Raises SettingError naming the variable.
    """
    by_env = {s.env_name: s for s in REGISTRY.values()}
    overrides: dict[str, Any] = {}
    for name, raw in raw_env.items():
        setting = by_env.get(name)
        if setting is None:
            if name not in RESERVED_ENV_NAMES:
                log.warning("ignoring unknown environment variable %s", name)
            continue
        if raw == "":
            continue
        overrides[setting.key] = setting.parse_env(raw)
    return overrides


def defaults(db_path: str) -> dict[str, Any]:
    values = {key: s.default for key, s in REGISTRY.items()}
    values["backup.directory"] = str(Path(db_path).resolve().parent / "backups")
    return values


class SettingsStore:
    def __init__(
        self,
        db: Database,
        keyring: Keyring,
        *,
        env_overrides: dict[str, Any],
        default_values: dict[str, Any],
    ) -> None:
        self._db = db
        self._keyring = keyring
        self._env = env_overrides
        self._defaults = default_values

    def overridden(self, key: str) -> bool:
        return key in self._env

    def _decode(self, setting: Setting, value: str, encrypted: bool) -> Any:
        if encrypted:
            value = self._keyring.decrypt(value, setting_aad(setting.key))
        elif setting.secret:
            log.warning("secret setting %s is stored unencrypted", setting.key)
        return setting.validate(json.loads(value))

    async def snapshot(self) -> dict[str, Any]:
        """Every setting's effective value. A stored value that no longer
        validates is logged and replaced by its default."""
        values = dict(self._defaults)
        async with self._db.read() as conn:
            stored = await rows.all_rows(conn)
        for row in stored:
            setting = REGISTRY.get(row.key)
            if setting is None:
                continue
            try:
                values[row.key] = self._decode(setting, row.value, bool(row.encrypted))
            except (SettingError, DecryptError, ValueError) as err:
                log.error("setting %s is invalid (%s); using its default", row.key, err)
        values.update(self._env)
        return values

    async def get(self, key: str) -> Any:
        return (await self.snapshot())[key]

    async def check_stored(self) -> None:
        """Startup check: refuse a stored value that doesn't validate."""
        async with self._db.read() as conn:
            stored = await rows.all_rows(conn)
        for row in stored:
            setting = REGISTRY.get(row.key)
            if setting is None:
                continue
            try:
                self._decode(setting, row.value, bool(row.encrypted))
            except (SettingError, DecryptError, ValueError) as err:
                raise SettingError(f"stored setting {row.key}: {err}") from None

    async def ensure_generated_secrets(self) -> None:
        for setting in REGISTRY.values():
            if not setting.generated or setting.key in self._env:
                continue
            async with self._db.write() as conn:
                if await rows.get(conn, setting.key) is not None:
                    continue
                value = json.dumps(secrets.token_urlsafe(32))
                await rows.put(
                    conn,
                    setting.key,
                    self._keyring.encrypt(value, setting_aad(setting.key)),
                    encrypted=True,
                    now=timestamp(),
                )
                log.info("generated %s", setting.key)
