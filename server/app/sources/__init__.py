from app.sources.fake import FakeSource, _build_fake
from app.sources.registry import SourceRegistry, build_source, register_source_type

# P9 registers "jellyfin" the same way. "fake" is handy for config-driven tests.
register_source_type("fake", _build_fake)

__all__ = [
    "FakeSource",
    "SourceRegistry",
    "build_source",
    "register_source_type",
]
