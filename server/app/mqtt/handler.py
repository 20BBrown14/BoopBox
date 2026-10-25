"""The boop -> one response flow (P7 steps 1-7).

`build_response` is pure dispatch: it parses, version-checks, resolves,
selects, mints, and returns exactly one `Play` or `Error` — never both, never
zero. Enforcing single-response structurally (one return value) is the whole
point. Side effects (publishing, last_seen) live in the service around this.
"""

import json
import logging
import random
import time
from urllib.parse import quote

from pydantic import ValidationError

from app.config import Settings
from app.errors import ErrorCode, mqtt_error
from app.models import Boop, BoopRef, Error, Play, VersionReply
from app.mqtt.selection import select_entry
from app.protocol import is_supported
from app.resolver import resolve
from app.sources import SourceRegistry
from app.stream_token import mint
from app.types.source import SourceError
from app.types.token import StreamClaims

logger = logging.getLogger(__name__)


def _best_effort_ref(payload: object) -> BoopRef:
    """A partial BoopRef parsed before an unknown `v` is trusted.

    Only `id`/`slug` if they are plain strings; anything else stays None. Used
    solely for `unsupported_version`, which is best-effort by contract.
    """
    if not isinstance(payload, dict):
        return BoopRef()
    bid = payload.get("id")
    slug = payload.get("slug")
    return BoopRef(
        id=bid if isinstance(bid, str) else None,
        slug=slug if isinstance(slug, str) else None,
    )


def _stream_url(settings: Settings, token: str) -> str:
    # public_base_url is admin-supplied and used verbatim; never derive the host
    # from the socket. The token is URL-encoded into the query safely.
    return f"{settings.public_base_url}/stream?sig={quote(token, safe='')}"


async def build_response(
    device_id: str,
    raw: bytes,
    settings: Settings,
    sources: SourceRegistry,
    *,
    rng: random.Random,
) -> Play | Error:
    """Build the single response for one boop. Returns a `Play` or an `Error`.

    `device_id` comes from the topic (`boopbox/<id>/boop`) and is authoritative.
    Returns None only would violate the single-response contract — it never
    does; every branch returns exactly one model.
    """
    # Step 1: decode + version-check.
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("boop from %s: undecodable payload, dropping", device_id)
        return mqtt_error(ErrorCode.unsupported_version, BoopRef())

    version = payload.get("v") if isinstance(payload, dict) else None
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or not is_supported(version)
    ):
        return mqtt_error(ErrorCode.unsupported_version, _best_effort_ref(payload))

    # Step 2: parse the Boop model at a supported version.
    try:
        boop = Boop.model_validate(payload)
    except ValidationError:
        # Supported v but structurally invalid. If id/slug happen to be present,
        # echo them so the box can correlate; otherwise unsupported_version is
        # the only honest signal (there is no valid boop.id to key on).
        ref = _best_effort_ref(payload)
        logger.warning("boop from %s: invalid structure at v=%s", device_id, version)
        return mqtt_error(ErrorCode.unsupported_version, ref)

    ref = BoopRef(id=boop.id, slug=boop.slug)

    # Step 3: resolve slug.
    entries = resolve(settings, boop.slug)
    if entries is None:
        return mqtt_error(ErrorCode.unknown_tag, ref)

    # Collection-aware selection -> one concrete (source, item).
    try:
        selection = await select_entry(entries, sources, rng=rng)
    except SourceError as err:
        logger.warning("boop from %s: select failed: %s", device_id, err.log_detail)
        return mqtt_error(err.code, ref)

    # Step 4: duration + mint.
    source = sources.get(selection.source)
    try:
        duration = await source.duration(selection.item)
    except SourceError as err:
        logger.warning("boop from %s: duration failed: %s", device_id, err.log_detail)
        return mqtt_error(err.code, ref)

    token = mint(
        StreamClaims(
            device=device_id,
            source=selection.source,
            item=selection.item,
            exp=0,
        ),
        duration,
        now=int(time.time()),
        secret=settings.stream_secret,
        pause_budget=settings.config.streaming.pause_budget_seconds,
    )

    # Step 5-6: build URL + play.
    return Play(
        boop=ref,
        url=_stream_url(settings, token),
        duration=duration,
    )


def parse_version_reply(device_id: str, raw: bytes) -> VersionReply | None:
    """Parse a `boopbox/<id>/version` reply, or None if it should be dropped.

    Separate from `build_response` (the boop -> one play/error contract): a
    version reply produces no response, only a parsed value the push policy (P11)
    acts on. Undecodable, unsupported-`v`, or structurally invalid payloads are
    dropped with a log and no side effect.
    """
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("version from %s: undecodable payload, dropping", device_id)
        return None

    version = payload.get("v") if isinstance(payload, dict) else None
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or not is_supported(version)
    ):
        logger.warning(
            "version from %s: unsupported/missing v=%r, dropping", device_id, version
        )
        return None

    try:
        return VersionReply.model_validate(payload)
    except ValidationError:
        logger.warning("version from %s: invalid structure at v=%s", device_id, version)
        return None
