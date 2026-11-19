"""The MQTT service: aiomqtt client on the app's single loop.

Owns one background task that connects, subscribes `boopbox/+/boop`, and
dispatches each boop through `handle_boop` to exactly one publish. A
reconnect loop keeps a broker blip from permanently ending message handling.
Start/stop are driven by the app lifespan.
"""

import asyncio
import logging
import random
import re
import ssl
from collections.abc import Awaitable, Callable

import aiomqtt

from app.db import boops, devices, mappings
from app.db.engine import Database
from app.db.timestamps import timestamp
from app.models import Cmd, Error, FlashCmd, Play, VersionReply
from app.mqtt.handler import (
    MAX_PAYLOAD_BYTES,
    BoopResult,
    handle_boop,
    parse_version_reply,
)
from app.mqtt.publish import publish_cmd, publish_error, publish_flash, publish_play
from app.settings import SettingsStore

logger = logging.getLogger(__name__)

BOOP_TOPIC = "boopbox/+/boop"
VERSION_TOPIC = "boopbox/+/version"
SUBSCRIPTIONS = (BOOP_TOPIC, VERSION_TOPIC)
# boopbox/<id>/<suffix> -> capture (<id>, <suffix>). <id> excludes '/' so the
# segment is exact; suffix routing happens in _dispatch.
_TOPIC_RE = re.compile(r"^boopbox/([^/]+)/([^/]+)$")
_RECONNECT_DELAY_SECONDS = 5

# Push-policy hook: called with each parsed version reply. The service never
# decides to flash itself.
VersionReplyHandler = Callable[[str, VersionReply], Awaitable[None]]


def _build_client(values: dict) -> aiomqtt.Client:
    tls_context: ssl.SSLContext | None = None
    if values["mqtt.tls"]:
        tls_context = ssl.create_default_context(cadata=values["mqtt.tls_ca"] or None)
    return aiomqtt.Client(
        hostname=values["mqtt.host"],
        port=values["mqtt.port"],
        username=values["mqtt.username"] or None,
        password=values["mqtt.password"] or None,
        tls_context=tls_context,
    )


def _route_from_topic(topic: str) -> tuple[str, str] | None:
    """Extract (device_id, suffix) from a `boopbox/<id>/<suffix>` topic, or None."""
    match = _TOPIC_RE.match(topic)
    return (match.group(1), match.group(2)) if match else None


def device_id_from_topic(topic: str) -> str | None:
    """Extract the authoritative device id from a boop topic, or None.

    Kept for the boop path (and callers that key on a boop topic specifically):
    returns the id only for a `.../boop` topic.
    """
    route = _route_from_topic(topic)
    return route[0] if route is not None and route[1] == "boop" else None


class MqttService:
    """aiomqtt loop owner. `start()` launches the background task on the running
    loop; `stop()` cancels it cleanly. The connected client is exposed as
    `self.client` while connected so cmd publishes can reuse it."""

    def __init__(
        self,
        db: Database,
        settings: SettingsStore,
        sources,
        *,
        client_factory=_build_client,
        rng: random.Random | None = None,
        on_version_reply: VersionReplyHandler | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._sources = sources
        self._client_factory = client_factory
        self._rng = rng or random.Random()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self.client: aiomqtt.Client | None = None
        # May be set after construction.
        self.on_version_reply: VersionReplyHandler | None = on_version_reply

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="mqtt-service")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            self.client = None

    async def _run(self) -> None:
        """Connect/subscribe/consume with reconnect until stop is requested."""
        while not self._stopping.is_set():
            try:
                values = await self._settings.snapshot()
                async with self._client_factory(values) as client:
                    self.client = client
                    for topic in SUBSCRIPTIONS:
                        await client.subscribe(topic)
                    logger.info("mqtt connected; subscribed %s", SUBSCRIPTIONS)
                    async for message in client.messages:
                        try:
                            await self._dispatch(client, message)
                        except aiomqtt.MqttError:
                            raise
                        except Exception:
                            logger.exception("mqtt: handling %s failed", message.topic)
            except Exception as err:
                # Also catches a bad TLS CA setting, so fixing it recovers.
                self.client = None
                if self._stopping.is_set():
                    break
                logger.warning(
                    "mqtt connection lost (%s); reconnecting in %ss",
                    err,
                    _RECONNECT_DELAY_SECONDS,
                )
                try:
                    await asyncio.sleep(_RECONNECT_DELAY_SECONDS)
                except asyncio.CancelledError:
                    break
            except asyncio.CancelledError:
                break
            finally:
                self.client = None

    async def _dispatch(self, client: aiomqtt.Client, message) -> None:
        topic = message.topic.value
        route = _route_from_topic(topic)
        if route is None:
            logger.warning("mqtt: unexpected topic %r, ignoring", topic)
            return
        device_id, suffix = route
        payload = message.payload
        raw = bytes(payload) if isinstance(payload, (bytes, bytearray)) else b""
        if len(raw) > MAX_PAYLOAD_BYTES:
            logger.warning("mqtt: %d-byte payload on %r, dropping", len(raw), topic)
            return
        if suffix not in ("boop", "version"):
            logger.warning("mqtt: unexpected topic suffix %r, ignoring", topic)
            return

        # Unknown, deleted and revoked devices are dropped before anything else.
        async with self._db.read() as conn:
            device = await devices.get(conn, device_id)
        if device is None or device.revoked:
            logger.info("mqtt: dropping %s from inactive device %r", suffix, device_id)
            return

        if suffix == "boop":
            await self._handle_boop(client, device_id, raw)
        else:
            await self._handle_version(device_id, raw)

    async def _handle_boop(
        self, client: aiomqtt.Client, device_id: str, raw: bytes
    ) -> None:
        result = await handle_boop(
            device_id,
            raw,
            db=self._db,
            sources=self._sources,
            settings=await self._settings.snapshot(),
            rng=self._rng,
        )
        if isinstance(result.response, Play):
            await publish_play(client, device_id, result.response)
        elif isinstance(result.response, Error):
            await publish_error(client, device_id, result.response)

        # History is best-effort: a failed write never drops the response.
        try:
            await self._record(device_id, result)
        except Exception:
            logger.exception("mqtt: recording boop from %s failed", device_id)

    async def _record(self, device_id: str, result: BoopResult) -> None:
        now = timestamp()
        async with self._db.write() as conn:
            for entry_id, status in result.entry_status.items():
                await mappings.set_entry_status(conn, entry_id, status, now)
            if result.record is not None:
                await boops.record(conn, result.record, now)
            await devices.touch(conn, device_id, now)

    async def _handle_version(self, device_id: str, raw: bytes) -> None:
        """Never publishes; the flash decision lives behind on_version_reply."""
        reply = parse_version_reply(device_id, raw)
        if reply is None:
            return
        try:
            async with self._db.write() as conn:
                await devices.touch(
                    conn, device_id, timestamp(), firmware_version=reply.firmware
                )
        except Exception:
            logger.exception("mqtt: firmware stamp failed for %s", device_id)

        if self.on_version_reply is not None:
            await self.on_version_reply(device_id, reply)

    async def send_cmd(self, target: str, cmd: Cmd) -> None:
        """Publish a thin `cmd` to a device or the broadcast target.

        Used for `get_version` (and any future thin command). Raises if the
        client is not currently connected.
        """
        if self.client is None:
            raise RuntimeError("mqtt client not connected")
        await publish_cmd(self.client, target, cmd)

    async def send_flash(self, device_id: str, flash: FlashCmd) -> None:
        """Publish a fat `flash` command to a single device (never broadcast).

        The push policy calls this with a FlashCmd built from the firmware
        index. Raises if the client is not currently connected.
        """
        if self.client is None:
            raise RuntimeError("mqtt client not connected")
        await publish_flash(self.client, device_id, flash)
