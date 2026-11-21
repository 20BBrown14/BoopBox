"""Values that can only come from the environment. Everything else is a
setting in the database (see app/settings)."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "BOOPBOX_"
ENV_FILE = ".env"


class Environment(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX, env_file=ENV_FILE, extra="ignore"
    )

    db_path: str = "boopbox.db"
    firmware_dir: str = "firmware-bins"
    default_username: str = ""
    default_password: str = ""
    secret_key: str = ""
    secret_keys_file: str = ""
    web_dir: str = ""


# Read by something other than a setting, so not reported as unknown.
RESERVED_ENV_NAMES = frozenset(
    {
        *(ENV_PREFIX + name.upper() for name in Environment.model_fields),
        "BOOPBOX_LOG_LEVEL",
        "BOOPBOX_BROKER_HOST_PORT",
    }
)


def raw_environment() -> dict[str, str]:
    """BOOPBOX_* variables from .env and the process; the process wins."""
    merged = (
        {
            key: value
            for key, value in dotenv_values(ENV_FILE).items()
            if value is not None
        }
        if Path(ENV_FILE).is_file()
        else {}
    )
    merged.update(os.environ)
    return {k: v for k, v in merged.items() if k.startswith(ENV_PREFIX)}


@lru_cache
def get_env() -> Environment:
    return Environment()
