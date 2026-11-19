"""Every setting the server knows. The database stores only overrides."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.config import ENV_PREFIX


class SettingError(ValueError):
    pass


@dataclass(frozen=True)
class Setting:
    key: str
    kind: str  # string | integer | boolean | enum | secret
    default: Any = None
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    choices: tuple[str, ...] = ()
    url: bool = False
    generated: bool = False
    min_length: int = 0

    @property
    def secret(self) -> bool:
        return self.kind == "secret"

    @property
    def env_name(self) -> str:
        return ENV_PREFIX + self.key.upper().replace(".", "_")

    def parse_env(self, raw: str) -> Any:
        if self.kind == "integer":
            try:
                return self.validate(int(raw.strip()))
            except ValueError as err:
                raise SettingError(f"{self.env_name}: {err}") from None
        if self.kind == "boolean":
            text = raw.strip().lower()
            if text in ("1", "true", "yes", "on"):
                return True
            if text in ("0", "false", "no", "off"):
                return False
            raise SettingError(f"{self.env_name}: expected true or false")
        try:
            return self.validate(raw)
        except SettingError as err:
            raise SettingError(f"{self.env_name}: {err}") from None

    def validate(self, value: Any) -> Any:
        if self.kind == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise SettingError("expected an integer")
            if self.minimum is not None and value < self.minimum:
                raise SettingError(f"must be at least {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise SettingError(f"must be at most {self.maximum}")
            return value
        if self.kind == "boolean":
            if not isinstance(value, bool):
                raise SettingError("expected true or false")
            return value
        if not isinstance(value, str):
            raise SettingError("expected a string")
        if self.kind == "enum" and value not in self.choices:
            raise SettingError(f"must be one of {', '.join(self.choices)}")
        if self.max_length is not None and len(value) > self.max_length:
            raise SettingError(f"must be at most {self.max_length} characters")
        if len(value) < self.min_length:
            raise SettingError(f"must be at least {self.min_length} characters")
        if self.url:
            value = value.strip().rstrip("/")
            parts = urlsplit(value)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise SettingError("must be an http or https URL")
            if parts.username or parts.password or parts.query or parts.fragment:
                raise SettingError("must not contain credentials, query or fragment")
        return value


def _int(key, default, minimum, maximum) -> Setting:
    return Setting(key, "integer", default, minimum=minimum, maximum=maximum)


def _bool(key, default) -> Setting:
    return Setting(key, "boolean", default)


def _str(key, default, max_length) -> Setting:
    return Setting(key, "string", default, max_length=max_length)


# backup.directory's real default depends on the database path; see defaults().
REGISTRY: dict[str, Setting] = {
    s.key: s
    for s in (
        Setting(
            "public_base_url",
            "string",
            "http://127.0.0.1:9685",
            max_length=2048,
            url=True,
        ),
        _str("mqtt.host", "localhost", 255),
        _int("mqtt.port", 1883, 1, 65535),
        _str("mqtt.username", "", 255),
        Setting("mqtt.password", "secret", "", max_length=1024),
        _bool("mqtt.tls", False),
        _str("mqtt.tls_ca", "", 16384),
        Setting("streaming.mode", "enum", "proxy", choices=("proxy", "redirect")),
        _int("streaming.pause_budget_seconds", 1800, 0, 86400),
        _str("ota.manifest_version", "", 32),
        _int("auth.token_lifetime_hours", 8, 1, 720),
        _int("invites.expiry_days", 3, 1, 30),
        _int("auth.lockout_threshold", 5, 1, 100),
        _int("auth.lockout_minutes", 15, 1, 1440),
        _int("auth.history_retention_days", 90, 0, 3650),
        _bool("auth.trust_forwarded_header", False),
        _int("playback.idle_timeout_days", 3, 1, 365),
        _int("boops.retention_days", 90, 0, 3650),
        _int("invites.retention_days", 30, 0, 3650),
        _int("retention.purge_interval_hours", 24, 1, 168),
        _bool("backup.enabled", True),
        _int("backup.interval_hours", 24, 1, 720),
        _int("backup.keep_count", 7, 0, 1000),
        _str("backup.directory", "backups", 1024),
        # HS256 needs a key at least as long as its 32-byte output.
        Setting(
            "secrets.stream",
            "secret",
            None,
            generated=True,
            min_length=32,
            max_length=1024,
        ),
        Setting(
            "secrets.auth_token",
            "secret",
            None,
            generated=True,
            min_length=32,
            max_length=1024,
        ),
    )
}
