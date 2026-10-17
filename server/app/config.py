from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Placeholder for now: no fields are loaded from config.yaml/.env yet. Later
    pieces add the real config and env fields here.
    """

    model_config = SettingsConfigDict(env_prefix="BOOPBOX_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
