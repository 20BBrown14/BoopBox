from app.sources.fake import FakeSource, _build_fake
from app.sources.jellyfin import JellyfinSource, _build_jellyfin
from app.sources.registry import (
    SourceRegistry,
    known_source_types,
    register_source_type,
)

register_source_type("fake", _build_fake)
register_source_type("jellyfin", _build_jellyfin)

__all__ = [
    "FakeSource",
    "JellyfinSource",
    "SourceRegistry",
    "known_source_types",
    "register_source_type",
]
