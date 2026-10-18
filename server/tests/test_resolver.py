import textwrap

from app.config import Settings
from app.resolver import resolve
from app.types.config import MappingKind

CONFIG = textwrap.dedent(
    """
    sources:
      - id: jellyfin-main
        type: jellyfin
        base_url: http://jellyfin:8096
    mappings:
      "boop/zelda":
        - source: jellyfin-main
          item: "abc123"
      "boop/soundtracks":
        - source: jellyfin-main
          item: "collection-xyz"
          kind: collection
        - source: jellyfin-main
          item: "track-1"
          kind: item
    """
)


def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", "s3cret")
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return Settings(_env_file=None, config_path=str(path))


def test_resolve_hit(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    entries = resolve(settings, "boop/zelda")
    assert entries is not None
    assert len(entries) == 1
    assert entries[0].source == "jellyfin-main"
    assert entries[0].item == "abc123"
    assert entries[0].kind == MappingKind.item


def test_resolve_list_with_mixed_kinds(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    entries = resolve(settings, "boop/soundtracks")
    assert entries is not None
    assert len(entries) == 2
    assert entries[0].kind == MappingKind.collection
    assert entries[1].kind == MappingKind.item


def test_resolve_miss(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    assert resolve(settings, "boop/unknown") is None
