"""Slug -> one concrete (source, item) to play, per the mapping's settings.

`all` and `all_repeat` currently play like `one`: how a box advances through a
queue is still undecided, so no playback_progress is kept yet.
"""

import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.db import mappings
from app.db.engine import Database
from app.db.mappings import Entry
from app.errors import ErrorCode
from app.types.source import SourceError

log = logging.getLogger(__name__)

SLUG_MAX = 128
QUEUE_CAP = 1000
# Bounds the upstream calls one boop can make when items keep failing.
MAX_ATTEMPTS = 5


def normalize_slug(raw: str) -> str:
    return raw.strip().lower()


@dataclass
class Resolution:
    outcome: str
    mapping_id: int | None = None
    entry_id: int | None = None
    source_id: int | None = None
    item: str | None = None
    duration: int | None = None
    entry_status: dict[int, str] = field(default_factory=dict)


class _Attempt:
    def __init__(self, sources, rng: random.Random, res: Resolution) -> None:
        self.sources = sources
        self.rng = rng
        self.res = res
        self.tries = 0
        self.item_failed = False

    def _note(self, entry: Entry, err: SourceError, mark: bool) -> None:
        log.info("entry %d: %s", entry.id, err.log_detail or err.code)
        if err.code is ErrorCode.item_unavailable:
            self.item_failed = True
            if mark:
                self.res.entry_status[entry.id] = "missing"

    async def expand(self, entry: Entry) -> list[str]:
        self.tries += 1
        try:
            source = await self.sources.get(entry.source_id)
            members = await source.members(entry.item)
        except SourceError as err:
            self._note(entry, err, mark=True)
            return []
        self.res.entry_status[entry.id] = "ok"
        return members

    async def candidates(
        self, group: list[Entry], play_order: str
    ) -> AsyncIterator[tuple[Entry, str]]:
        if play_order == "sequential":
            for entry in group:
                if entry.kind == "item":
                    yield entry, entry.item
                else:
                    for member in (await self.expand(entry))[:QUEUE_CAP]:
                        yield entry, member
            return
        pool: list[tuple[Entry, str]] = []
        for entry in group:
            if entry.kind == "item":
                pool.append((entry, entry.item))
            else:
                pool.extend((entry, m) for m in await self.expand(entry))
        if len(pool) > QUEUE_CAP:
            log.warning(
                "mapping %d: pool truncated to %d", self.res.mapping_id, QUEUE_CAP
            )
            pool = pool[:QUEUE_CAP]
        self.rng.shuffle(pool)
        for candidate in pool:
            yield candidate

    async def play(self, entry: Entry, item: str) -> bool:
        self.tries += 1
        try:
            source = await self.sources.get(entry.source_id)
            duration = await source.duration(item)
        except SourceError as err:
            self._note(entry, err, mark=entry.kind == "item")
            return False
        if entry.kind == "item":
            self.res.entry_status[entry.id] = "ok"
        self.res.outcome = "played"
        self.res.entry_id = entry.id
        self.res.source_id = entry.source_id
        self.res.item = item
        self.res.duration = duration
        return True


async def resolve(
    db: Database, sources, device_id: str, slug: str, *, rng: random.Random
) -> Resolution:
    key = normalize_slug(slug)
    if not key or len(key) > SLUG_MAX:
        return Resolution("unknown_tag")
    async with db.read() as conn:
        mapping = await mappings.find_by_slug(conn, key)
        if mapping is None:
            return Resolution("unknown_tag")
        if not mapping.all_devices and not await mappings.device_listed(
            conn, mapping.id, device_id
        ):
            return Resolution("out_of_scope", mapping_id=mapping.id)
        entries = await mappings.live_entries(conn, mapping.id)

    res = Resolution("item_unavailable", mapping_id=mapping.id)
    usable = [e for e in entries if e.source_usable]
    if entries and not usable:
        res.outcome = "source_unavailable"
    if not usable:
        return res

    attempt = _Attempt(sources, rng, res)
    healthy = [e for e in usable if e.status != "missing"]
    missing = [e for e in usable if e.status == "missing"]
    for group in (healthy, missing):
        if not group:
            continue
        async for entry, item in attempt.candidates(group, mapping.play_order):
            if await attempt.play(entry, item):
                return res
            if attempt.tries >= MAX_ATTEMPTS:
                break
        if attempt.tries >= MAX_ATTEMPTS:
            break

    res.outcome = "item_unavailable" if attempt.item_failed else "source_unavailable"
    return res
