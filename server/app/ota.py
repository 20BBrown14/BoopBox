"""
Every update funnels through one compare-and-maybe-flash step. Triggers only
initiate a `get_version` query; none flashes directly. A `/version` reply
(solicited or unsolicited) lands on `on_version_reply`, which compares the
reported firmware to the target and, if stale, looks up the bin for the box's
own reported chip and publishes `flash` with that
`{url, md5}`.

Stateless/reactive: no outstanding-query tracking, no timeouts. An offline box
simply doesn't reply and is caught the next time it reports.
"""

import logging

from app.firmware import FirmwareCache
from app.models import Cmd, CmdName, FlashCmd, VersionReply
from app.mqtt.publish import BROADCAST
from app.mqtt.service import MqttService

logger = logging.getLogger(__name__)


class OtaPolicy:
    def __init__(
        self,
        firmware: FirmwareCache,
        target_version: str,
        mqtt: MqttService,
        *,
        auto_push_on_publish: bool = False,
    ) -> None:
        self._firmware = firmware
        self._target_version = target_version
        self._mqtt = mqtt
        self._auto_push_on_publish = auto_push_on_publish

    async def on_version_reply(self, device_id: str, reply: VersionReply) -> None:
        """Compare-and-maybe-flash for one `/version` reply.

        The same handler serves solicited and unsolicited replies. A box at the
        target is left alone. A stale box is flashed with the bin matching its
        own reported chip; an unknown chip (or no bin in the index) is logged and
        skipped, never guessed — a wrong-chip flash bricks the box.
        """
        logger.info(
            "ota: %s reports firmware %s chip %s (target %s)",
            device_id,
            reply.firmware,
            reply.chip,
            self._target_version,
        )
        if reply.firmware == self._target_version:
            return

        entry = self._firmware.index(reply.chip)
        if entry is None:
            logger.info(
                "ota: no bin for chip %r (device %s, firmware %s); skipping flash",
                reply.chip,
                device_id,
                reply.firmware,
            )
            return

        flash = FlashCmd(url=entry.path, md5=entry.md5)
        logger.info(
            "ota: flashing %s (%s -> %s, chip %s)",
            device_id,
            reply.firmware,
            self._target_version,
            reply.chip,
        )
        await self._mqtt.send_flash(device_id, flash)

    async def query_version(self, device_id: str | None = None) -> None:
        """Trigger the version-check path: publish `get_version` to one device or
        broadcast to the fleet. Never flashes directly — the reply decides."""
        target = device_id if device_id is not None else BROADCAST
        await self._mqtt.send_cmd(target, Cmd(cmd=CmdName.get_version))

    async def maybe_push_on_publish(self) -> None:
        """Admin-upload trigger, gated by `ota.auto_push_on_publish`.

        With the knob off this is inert. With it on, broadcast `get_version` so
        the normal path updates whichever online boxes are stale.
        """
        if not self._auto_push_on_publish:
            return
        await self.query_version()
