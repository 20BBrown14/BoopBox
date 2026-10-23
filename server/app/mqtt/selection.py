"""Collection-aware entry selection: a slug's entry list -> one concrete item.

Selection rule (MVP): pick one entry uniformly at random from the list, then if
that entry is a collection, expand it via the source and pick one member
uniformly at random. Picking-then-expanding avoids expanding collections that
will not be played. Kept in one place so weighting can replace the uniform pick
later without touching the handler.
"""

import random

from app.sources import SourceRegistry
from app.types.config import MappingEntry, MappingKind


class Selection:
    """The resolved concrete target to mint against."""

    __slots__ = ("source", "item")

    def __init__(self, source: str, item: str) -> None:
        self.source = source
        self.item = item


async def select_entry(
    entries: list[MappingEntry],
    sources: SourceRegistry,
    *,
    rng: random.Random,
) -> Selection:
    """Turn a resolver entry list into one concrete `(source, item)`.

    Raises `SourceError` if a chosen collection cannot be expanded (empty or the
    source is unavailable); the caller maps that to the published error.
    """
    entry = rng.choice(entries)
    if entry.kind is MappingKind.collection:
        source = sources.get(entry.source)
        members = await source.members(entry.item)  # SourceError on empty/fail
        item = rng.choice(members)
        return Selection(source=entry.source, item=item)
    return Selection(source=entry.source, item=entry.item)
