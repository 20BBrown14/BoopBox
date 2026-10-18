import textwrap

import pytest
from pydantic import ValidationError

from app.config import Settings, source_api_key_env
from app.types.config import StreamingMode

MINIMAL_CONFIG = textwrap.dedent(
    """
    sources:
      - id: jellyfin-main
        type: jellyfin
        base_url: http://jellyfin:8096
    mappings:
      "boop/zelda":
        - source: jellyfin-main
          item: "abc123"
    """
)


def _write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return str(path)


def test_defaults_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    config_path = _write(tmp_path, MINIMAL_CONFIG)

    settings = Settings(_env_file=None, config_path=config_path)

    assert settings.mqtt_host == "localhost"
    assert settings.mqtt_port == 1883
    assert settings.mqtt_tls is False
    assert settings.public_base_url == "http://127.0.0.1:9685"
    assert settings.seed_device_id == "boop-test"
    assert settings.config.streaming.mode is StreamingMode.proxy
    assert settings.config.streaming.pause_budget_seconds == 1800
    assert settings.config.ota.manifest_version == "0.1.0"


def test_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    monkeypatch.setenv("BOOPBOX_MQTT_HOST", "broker.example")
    monkeypatch.setenv("BOOPBOX_MQTT_PORT", "8883")
    monkeypatch.setenv("BOOPBOX_MQTT_TLS", "true")
    monkeypatch.setenv("BOOPBOX_PUBLIC_BASE_URL", "https://boop.example")
    config_path = _write(tmp_path, MINIMAL_CONFIG)

    settings = Settings(_env_file=None, config_path=config_path)

    assert settings.mqtt_host == "broker.example"
    assert settings.mqtt_port == 8883
    assert settings.mqtt_tls is True
    assert settings.public_base_url == "https://boop.example"


def test_config_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    config_path = _write(
        tmp_path,
        textwrap.dedent(
            """
            sources:
              - id: jellyfin-main
                type: jellyfin
                base_url: http://jellyfin:8096
            mappings: {}
            streaming:
              mode: proxy
              pause_budget_seconds: 600
            ota:
              manifest_version: "9.9.9"
            """
        ),
    )

    settings = Settings(_env_file=None, config_path=config_path)

    assert settings.config.streaming.pause_budget_seconds == 600
    assert settings.config.ota.manifest_version == "9.9.9"


def test_missing_stream_secret_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("BOOPBOX_STREAM_SECRET", raising=False)
    config_path = _write(tmp_path, MINIMAL_CONFIG)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, config_path=config_path)


def test_mapping_to_undefined_source_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    config_path = _write(
        tmp_path,
        textwrap.dedent(
            """
            sources:
              - id: jellyfin-main
                type: jellyfin
                base_url: http://jellyfin:8096
            mappings:
              "boop/zelda":
                - source: does-not-exist
                  item: "abc123"
            """
        ),
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None, config_path=config_path)


def test_malformed_config_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    config_path = _write(tmp_path, "- just\n- a\n- list\n")

    with pytest.raises((ValidationError, ValueError)):
        Settings(_env_file=None, config_path=config_path)


def test_wrong_type_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    config_path = _write(
        tmp_path,
        textwrap.dedent(
            """
            sources: []
            mappings: {}
            streaming:
              pause_budget_seconds: "not-a-number"
            """
        ),
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None, config_path=config_path)


def test_source_api_key_env_naming():
    assert source_api_key_env("jellyfin-main") == "BOOPBOX_SOURCE_JELLYFIN_MAIN_API_KEY"
    assert source_api_key_env("plex.home") == "BOOPBOX_SOURCE_PLEX_HOME_API_KEY"


def test_api_key_for_reads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    monkeypatch.setenv("BOOPBOX_SOURCE_JELLYFIN_MAIN_API_KEY", "key-xyz")
    config_path = _write(tmp_path, MINIMAL_CONFIG)

    settings = Settings(_env_file=None, config_path=config_path)

    assert settings.api_key_for("jellyfin-main") == "key-xyz"
    assert settings.api_key_for("unknown") == ""
