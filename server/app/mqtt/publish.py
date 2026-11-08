"""Topic builders and publish helpers for the outbound MQTT models.

Topics: play/error are per-device under `boopbox/<id>/{play,error}`; cmd targets
either a device (`boopbox/<id>/cmd`) or the broadcast (`boopbox/all/cmd`). The
wire payload is each pydantic model's JSON.
"""

from typing import Protocol

from app.models import Cmd, Error, FlashCmd, Play

BROADCAST = "all"


class Publisher(Protocol):
    """The subset of the aiomqtt client the helpers need (eases testing)."""

    async def publish(self, topic: str, payload: object) -> None: ...


def play_topic(device_id: str) -> str:
    return f"boopbox/{device_id}/play"


def error_topic(device_id: str) -> str:
    return f"boopbox/{device_id}/error"


def cmd_topic(target: str) -> str:
    return f"boopbox/{target}/cmd"


def version_topic(device_id: str) -> str:
    return f"boopbox/{device_id}/version"


async def publish_play(client: Publisher, device_id: str, play: Play) -> None:
    await client.publish(play_topic(device_id), play.model_dump_json())


async def publish_error(client: Publisher, device_id: str, error: Error) -> None:
    await client.publish(error_topic(device_id), error.model_dump_json())


async def publish_cmd(client: Publisher, target: str, cmd: Cmd) -> None:
    """Publish a thin `cmd` to a device id or the broadcast.

    `target` is a device id (-> `boopbox/<id>/cmd`) or `BROADCAST` (->
    `boopbox/all/cmd`).
    """
    await client.publish(cmd_topic(target), cmd.model_dump_json())


async def publish_flash(client: Publisher, device_id: str, flash: FlashCmd) -> None:
    """Publish a fat `flash` command to a single device's `cmd` topic.

    Per-device only: each box gets the bin for its own chip, so flashing is never
    broadcast.
    """
    await client.publish(cmd_topic(device_id), flash.model_dump_json())
