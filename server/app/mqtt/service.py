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

import aiomqtt

from app.config import Settings
from app.db.devices import DeviceRepository
from app.models import Cmd, Error, Play
from app.mqtt.handler import build_response
from app.mqtt.publish import publish_cmd, publish_error, publish_play
from app.sources import SourceRegistry

logger = logging.getLogger(__name__)

BOOP_TOPIC = "boopbox/+/boop"
# boopbox/<id>/boop -> capture <id>. <id> excludes '/' so the segment is exact.
_BOOP_RE = re.compile(r"^boopbox/([^/]+)/boop$")
_RECONNECT_DELAY_SECONDS = 5


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


def device_id_from_topic(topic: str) -> str | None:
    """Extract the authoritative device id from a boop topic, or None."""
    match = _BOOP_RE.match(topic)
    return match.group(1) if match else None


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
    ) -> None:
        self._settings = settings
        self._sources = sources
        self._devices = devices
        self._client_factory = client_factory
        self._rng = rng or random.Random()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self.client: aiomqtt.Client | None = None

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
                    await client.subscribe(BOOP_TOPIC)
                    logger.info("mqtt connected; subscribed %s", BOOP_TOPIC)
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
        device_id = device_id_from_topic(topic)
        if device_id is None:
            logger.warning("mqtt: unexpected topic %r, ignoring", topic)
            return
        payload = message.payload
        raw = payload if isinstance(payload, (bytes, bytearray)) else b""

        # Exactly one response per boop: build_response returns one model.
        response = await build_response(
            device_id,
            bytes(raw),
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

    async def send_cmd(self, target: str, cmd: Cmd) -> None:
        """Publish a `cmd` to a device or the broadcast target.

        The MVP entrypoint for the check-now nudge (P8/ops call this). Raises if
        the client is not currently connected.
        """
        if self.client is None:
            raise RuntimeError("mqtt client not connected")
        await publish_cmd(self.client, target, cmd)
