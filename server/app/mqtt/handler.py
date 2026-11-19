"""The boop -> one response flow.

`handle_boop` returns exactly one `Play` or `Error`, plus the boop history
record to write. Publishing and writing live in the service around it.
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote

from pydantic import ValidationError

from app.db.boops import BoopRecord
from app.db.engine import Database
from app.db.timestamps import timestamp
from app.errors import ErrorCode, mqtt_error
from app.models import Boop, BoopRef, Error, Play, VersionReply
from app.playback import SLUG_MAX, resolve
from app.protocol import is_supported
from app.stream_token import mint
from app.types.token import StreamClaims

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 4096
UID_MAX = 32
_UID_CHARS = frozenset("0123456789ABCDEF:")
# A box clock before this is unset, not real.
_EARLIEST_BOX_TIME = 1577836800  # 2020-01-01
_BOX_CLOCK_SLACK = 86400

# out_of_scope is only for the log; the box can't learn the slug exists elsewhere.
_REPLY_CODE = {
    "unknown_tag": ErrorCode.unknown_tag,
    "out_of_scope": ErrorCode.unknown_tag,
    "item_unavailable": ErrorCode.item_unavailable,
    "source_unavailable": ErrorCode.source_unavailable,
}


@dataclass
class BoopResult:
    response: Play | Error
    record: BoopRecord | None = None
    entry_status: dict[int, str] = field(default_factory=dict)


def normalize_uid(raw: str) -> str | None:
    """Uppercase hex with ':' separators, or None if it can't be one."""
    text = raw.strip().upper().replace("-", ":").replace(" ", ":")
    if ":" not in text and len(text) % 2 == 0:
        text = ":".join(text[i : i + 2] for i in range(0, len(text), 2))
    if not 1 <= len(text) <= UID_MAX or not set(text) <= _UID_CHARS:
        return None
    return text


def box_time(ts: int, now: float) -> str | None:
    if not _EARLIEST_BOX_TIME <= ts <= now + _BOX_CLOCK_SLACK:
        return None
    return timestamp(datetime.fromtimestamp(ts, UTC))


def _best_effort_ref(payload: object) -> BoopRef:
    """Only for replies to payloads that couldn't be parsed as a boop."""
    if not isinstance(payload, dict):
        return BoopRef()
    bid = payload.get("id")
    slug = payload.get("slug")
    return BoopRef(
        id=bid if isinstance(bid, str) else None,
        slug=slug if isinstance(slug, str) else None,
    )


def _supported_version(payload: object) -> bool | None:
    """True/False for an integer `v`, None when there is no usable `v`."""
    version = payload.get("v") if isinstance(payload, dict) else None
    if not isinstance(version, int) or isinstance(version, bool):
        return None
    return is_supported(version)


async def handle_boop(
    device_id: str,
    raw: bytes,
    *,
    db: Database,
    sources,
    settings: dict,
    rng: random.Random,
) -> BoopResult:
    """`device_id` comes from the topic and is authoritative."""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("boop from %s: undecodable payload", device_id)
        return BoopResult(mqtt_error(ErrorCode.unsupported_version, BoopRef()))

    supported = _supported_version(payload)
    if not supported:
        reply = mqtt_error(ErrorCode.unsupported_version, _best_effort_ref(payload))
        if supported is False:
            return BoopResult(reply, BoopRecord(device_id, "unsupported_version"))
        return BoopResult(reply)

    try:
        boop = Boop.model_validate(payload)
    except ValidationError:
        logger.warning("boop from %s: invalid structure", device_id)
        return BoopResult(
            mqtt_error(ErrorCode.unsupported_version, _best_effort_ref(payload))
        )
    uid = normalize_uid(boop.uid)
    if uid is None:
        logger.warning("boop from %s: invalid tag uid", device_id)
        return BoopResult(
            mqtt_error(ErrorCode.unsupported_version, _best_effort_ref(payload))
        )

    ref = BoopRef(id=boop.id, slug=boop.slug)
    now = time.time()
    res = await resolve(db, sources, device_id, boop.slug, rng=rng)
    record = BoopRecord(
        device_id=device_id,
        outcome=res.outcome,
        uid=uid,
        slug=boop.slug.strip()[:SLUG_MAX],
        correlation_id=boop.id,
        box_at=box_time(boop.ts, now),
        mapping_id=res.mapping_id,
        entry_id=res.entry_id,
        source_id=res.source_id,
        item=res.item,
    )
    if res.outcome != "played":
        return BoopResult(
            mqtt_error(_REPLY_CODE[res.outcome], ref), record, res.entry_status
        )

    token = mint(
        StreamClaims(device=device_id, source=str(res.source_id), item=res.item, exp=0),
        res.duration,
        now=int(now),
        secret=settings["secrets.stream"],
        pause_budget=settings["streaming.pause_budget_seconds"],
    )
    url = f"{settings['public_base_url']}/stream?sig={quote(token, safe='')}"
    return BoopResult(
        Play(boop=ref, url=url, duration=res.duration), record, res.entry_status
    )


def parse_version_reply(device_id: str, raw: bytes) -> VersionReply | None:
    """A `/version` reply, or None if it should be dropped."""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("version from %s: undecodable payload, dropping", device_id)
        return None
    if not _supported_version(payload):
        logger.warning("version from %s: unsupported or missing v, dropping", device_id)
        return None
    try:
        return VersionReply.model_validate(payload)
    except ValidationError:
        logger.warning("version from %s: invalid structure, dropping", device_id)
        return None
