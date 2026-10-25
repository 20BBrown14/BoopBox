from app.sources.fake import FakeSource, _build_fake
from app.sources.jellyfin import JellyfinSource, _build_jellyfin
from app.sources.registry import SourceRegistry, build_source, register_source_type

# "fake" is handy for config-driven tests;
register_source_type("fake", _build_fake)
register_source_type("jellyfin", _build_jellyfin)

__all__ = [
    "FakeSource",
    "JellyfinSource",
    "SourceRegistry",
    "build_source",
    "register_source_type",
]
