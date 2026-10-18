from app.config import Settings
from app.types.config import MappingEntry


def resolve(settings: Settings, slug: str) -> list[MappingEntry] | None:
    """Resolve a tag slug to its list of mapping entries over the config mappings.

    Each entry carries `source`, `item`, and `kind` (item vs collection; a
    collection is resolved to a concrete item by the source layer at play time).
    The server picks one entry to play. Returns None on a miss. P7 maps the miss
    to the `unknown_tag` error code; this module does not import the error
    vocabulary. Pure over config, no I/O.
    """
    return settings.config.mappings.get(slug)
