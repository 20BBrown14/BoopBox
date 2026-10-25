"""The MQTT service: aiomqtt client on the app's single loop.

Owns one background task that connects, subscribes `boopbox/+/boop`, and
dispatches each boop through `build_response` to exactly one publish. A
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

from app.config import Settings
from app.db.devices import DeviceRepository
from app.models import Cmd, Error, FlashCmd, Play, VersionReply
from app.mqtt.handler import build_response, parse_version_reply
from app.mqtt.publish import publish_cmd, publish_error, publish_flash, publish_play
from app.sources import SourceRegistry

logger = logging.getLogger(__name__)

BOOP_TOPIC = "boopbox/+/boop"
VERSION_TOPIC = "boopbox/+/version"
SUBSCRIPTIONS = (BOOP_TOPIC, VERSION_TOPIC)
# boopbox/<id>/<suffix> -> capture (<id>, <suffix>). <id> excludes '/' so the
# segment is exact; suffix routing happens in _dispatch.
_TOPIC_RE = re.compile(r"^boopbox/([^/]+)/([^/]+)$")
_RECONNECT_DELAY_SECONDS = 5

# A P11 push-policy hook: called with each parsed version reply. The policy
# decides whether to flash and uses this service's publish helpers; P7 never
# decides to flash itself.
VersionReplyHandler = Callable[[str, VersionReply], Awaitable[None]]


def _build_client(settings: Settings) -> aiomqtt.Client:
    tls_params: aiomqtt.TLSParameters | None = None
    if settings.mqtt_tls:
        tls_params = aiomqtt.TLSParameters(
            ca_certs=settings.mqtt_tls_ca or None,
            cert_reqs=ssl.CERT_REQUIRED,
        )
    return aiomqtt.Client(
        hostname=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username or None,
        password=settings.mqtt_password or None,
        tls_params=tls_params,
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
        settings: Settings,
        sources: SourceRegistry,
        devices: DeviceRepository,
        *,
        client_factory=_build_client,
        rng: random.Random | None = None,
        on_version_reply: VersionReplyHandler | None = None,
    ) -> None:
        self._settings = settings
        self._sources = sources
        self._devices = devices
        self._client_factory = client_factory
        self._rng = rng or random.Random()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self.client: aiomqtt.Client | None = None
        # P11 push-policy seam; may be set after construction (P11 wires it in).
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
                async with self._client_factory(self._settings) as client:
                    self.client = client
                    for topic in SUBSCRIPTIONS:
                        await client.subscribe(topic)
                    logger.info("mqtt connected; subscribed %s", SUBSCRIPTIONS)
                    async for message in client.messages:
                        await self._dispatch(client, message)
            except aiomqtt.MqttError as err:
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

        if suffix == "boop":
            await self._handle_boop(client, device_id, raw)
        elif suffix == "version":
            await self._handle_version(device_id, raw)
        else:
            logger.warning("mqtt: unexpected topic suffix %r, ignoring", topic)

    async def _handle_boop(
        self, client: aiomqtt.Client, device_id: str, raw: bytes
    ) -> None:
        # Exactly one response per boop: build_response returns one model.
        response = await build_response(
            device_id,
            raw,
            self._settings,
            self._sources,
            rng=self._rng,
        )
        if isinstance(response, Play):
            await publish_play(client, device_id, response)
        elif isinstance(response, Error):
            await publish_error(client, device_id, response)

        # Step 7: stamp last_seen off-loop (aiosqlite runs off the loop thread).
        try:
            await self._devices.update_last_seen(device_id)
        except Exception:  # last_seen is best-effort; never drop the response
            logger.exception("mqtt: last_seen update failed for %s", device_id)

    async def _handle_version(self, device_id: str, raw: bytes) -> None:
        """Parse a `/version` reply, stamp the DB, and hand it to the P11 policy.

        Never publishes a response itself — a version reply is request/response
        telemetry, not the boop->play/error contract. The flash decision lives
        behind `on_version_reply` (P11), which reuses this service's publishers.
        """
        reply = parse_version_reply(device_id, raw)
        if reply is None:
            return

        # Cache/telemetry only (not the decision input); best-effort off-loop.
        try:
            await self._devices.update_last_seen(
                device_id, firmware_version=reply.firmware
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

        P11's push policy calls this with a FlashCmd built from P8's firmware
        index. Raises if the client is not currently connected.
        """
        if self.client is None:
            raise RuntimeError("mqtt client not connected")
        await publish_flash(self.client, device_id, flash)
