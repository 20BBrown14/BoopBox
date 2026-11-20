"""scripts/dump_openapi.py, run the way `npm run gen:api` runs it."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.settings import REGISTRY

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dump_openapi.py"


def _dump(out_dir: Path) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out-dir", str(out_dir)],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def dumped(env, tmp_path):
    out_dir = tmp_path / "out"
    _dump(out_dir)
    return out_dir


def test_dump_is_deterministic(env, dumped, tmp_path):
    again = tmp_path / "again"
    _dump(again)
    for name in ("openapi.json", "server-setting-keys.json"):
        assert (dumped / name).read_text() == (again / name).read_text()


def test_schema_describes_the_api(dumped):
    schema = json.loads((dumped / "openapi.json").read_text())
    assert "/api/me" in schema["paths"]
    assert "MeOut" in schema["components"]["schemas"]


def test_keys_are_the_sorted_registry(dumped):
    keys = json.loads((dumped / "server-setting-keys.json").read_text())
    assert keys == sorted(REGISTRY)


def test_dump_does_not_create_the_firmware_directory(env, tmp_path, monkeypatch):
    missing = tmp_path / "not-created"
    monkeypatch.setenv("BOOPBOX_FIRMWARE_DIR", str(missing))
    _dump(tmp_path / "out")
    assert not missing.exists()
