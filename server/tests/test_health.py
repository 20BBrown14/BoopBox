import textwrap

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

CONFIG = textwrap.dedent(
    """
    sources: []
    mappings: {}
    """
)


def test_health_returns_ok(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG)
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    monkeypatch.setenv("BOOPBOX_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("BOOPBOX_DB_PATH", str(tmp_path / "devices.db"))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    get_settings.cache_clear()
