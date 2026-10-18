"""Source registry: build one `Source` per configured entry, keyed by id.

`SourceConfig.id` is the lookup key; `SourceConfig.type` selects the builder.
The type->builder map is open so P9 registers `jellyfin` without editing P5.
"""

from collections.abc import Callable

from app.config import Settings
from app.types.config import SourceConfig
from app.types.source import Source

# A builder turns a config entry + settings (for per-source secrets) into a
# Source. P9 registers the jellyfin builder via register_source_type.
SourceBuilder = Callable[[SourceConfig, Settings], Source]

_BUILDERS: dict[str, SourceBuilder] = {}


def register_source_type(type_name: str, builder: SourceBuilder) -> None:
    """Register a builder for a `type`. Idempotent per type name."""
    _BUILDERS[type_name] = builder


def build_source(config: SourceConfig, settings: Settings) -> Source:
    builder = _BUILDERS.get(config.type)
    if builder is None:
        raise ValueError(f"unknown source type: {config.type!r}")
    return builder(config, settings)


class SourceRegistry:
    """Holds built sources keyed by id. Constructed at startup from
    `Settings.config.sources` and stashed on app state; P6 reads it from there."""

    def __init__(self, sources: dict[str, Source]) -> None:
        self._sources = sources

    @classmethod
    def from_settings(cls, settings: Settings) -> "SourceRegistry":
        sources = {
            entry.id: build_source(entry, settings)
            for entry in settings.config.sources
        }
        return cls(sources)

    def get(self, source_id: str) -> Source:
        """Look up a source by id.

        Unknown id is a programming error: the resolver only yields configured
        ids, so a miss means a bug upstream, not bad input.
        """
        try:
            return self._sources[source_id]
        except KeyError:
            raise KeyError(f"unknown source id: {source_id!r}") from None
