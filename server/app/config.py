import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.types.config import FileConfig

DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_DB_PATH = "devices.db"


def source_api_key_env(source_id: str) -> str:
    """Env var name holding a source's API key.

    Convention: BOOPBOX_SOURCE_<ID>_API_KEY, where <ID> is the source id
    uppercased with every run of non-alphanumeric characters collapsed to a
    single underscore. Centralized here so the convention is one edit to change.
    """
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", source_id).strip("_").upper()
    return f"BOOPBOX_SOURCE_{normalized}_API_KEY"


def _load_file_config(path: str | Path) -> FileConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"config file not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"config file must be a mapping at the top level: {config_path}"
        )
    return FileConfig.model_validate(raw)


class Settings(BaseSettings):
    """Typed application settings.

    Secrets and deploy-specific values load from the environment / .env under the
    BOOPBOX_ prefix. Structured config loads from config.yaml into `config`.
    """

    model_config = SettingsConfigDict(
        env_prefix="BOOPBOX_",
        env_file=".env",
        extra="ignore",
    )

    # Secret: required.
    stream_secret: str

    # Paths.
    config_path: str = DEFAULT_CONFIG_PATH
    db_path: str = DEFAULT_DB_PATH

    # MQTT connection.
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_tls: bool = False
    mqtt_tls_ca: str = ""

    # Public base URL for stream links.
    public_base_url: str = "http://127.0.0.1:9685"

    # Seed device (MVP only). The MQTT password is a broker concern and is never
    # stored in the devices table; the env var exists for broker provisioning.
    seed_device_id: str = "boop-test"
    seed_device_mqtt_password: str = ""

    config: FileConfig = Field(default_factory=FileConfig)

    @model_validator(mode="after")
    def _load_config_file(self) -> "Settings":
        self.config = _load_file_config(self.config_path)
        return self

    def api_key_for(self, source_id: str) -> str:
        """The API key for a source, read from its env var. Empty if unset."""
        return os.environ.get(source_api_key_env(source_id), "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
