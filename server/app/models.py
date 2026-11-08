"""Pydantic v2 payload models for the MQTT contract: boop, play, error, cmd.

Every model carries `v`. Inbound `Boop` reads `v` from the wire (no default so
the server version-checks it). Outbound models (`Play`, `Error`, `Cmd`) default
`v` to the current `PROTOCOL_VERSION` so the server stamps it without every call
site doing so.
"""

from enum import StrEnum

from pydantic import BaseModel

from app.errors import ErrorCode
from app.protocol import PROTOCOL_VERSION


class BoopRef(BaseModel):
    """Correlation block `{ id, slug }` echoed in play/error.

    Fields are individually optional so an `unsupported_version` error can carry
    a partial ref (only what was parseable before the unknown `v`).
    """

    id: str | None = None
    slug: str | None = None


class Boop(BaseModel):
    """Inbound boop published by the box to `boopbox/<id>/boop`.

    Carries the wire fields only; the server records its own receive time
    elsewhere.
    """

    v: int
    id: str
    slug: str
    uid: str
    ts: int  # unix seconds (box SNTP clock), informational only


class Play(BaseModel):
    """Play command published to `boopbox/<id>/play`.

    `boop` is present only when a boop caused this play; a future
    server-initiated play omits it. Metadata fields are optional (the box may
    ignore them);
    """

    v: int = PROTOCOL_VERSION
    boop: BoopRef | None = None
    url: str
    title: str | None = None
    duration: int | None = None  # whole seconds
    album: str | None = None
    artist: str | None = None


class Error(BaseModel):
    """Error published to `boopbox/<id>/error`.

    `boop` is normally a full ref (an error always stems from a boop); it may be
    partial or None only for `unsupported_version`, which is best-effort because
    the payload may be unparseable past the unknown `v`.
    """

    v: int = PROTOCOL_VERSION
    boop: BoopRef | None = None
    code: ErrorCode
    message: str


class CmdName(StrEnum):
    get_version = "get_version"
    flash = "flash"


class Cmd(BaseModel):
    """Thin command published to `boopbox/<id>/cmd` or `boopbox/all/cmd`.

    The `{v, cmd}` shape for commands that need no payload (e.g. `get_version`).
    The fat `flash` command is a separate model (`FlashCmd`) so this shape stays
    untouched.
    """

    v: int = PROTOCOL_VERSION
    cmd: CmdName


class FlashCmd(BaseModel):
    """Fat `flash` command published to `boopbox/<id>/cmd` (per-device only).

    Carries what ESPHome's `ota: http_request.flash` action needs inline: the
    bin `url` and its `md5`. Both come from the firmware index (never
    hand-built): `url` is the absolute, non-redirecting served path and `md5` is
    computed from the bin's disk bytes. `cmd` is fixed to `flash` so the wire
    payload is self-describing and a consumer routes on `cmd` regardless of which
    model produced it.
    """

    v: int = PROTOCOL_VERSION
    cmd: CmdName = CmdName.flash
    url: str
    md5: str


class VersionReply(BaseModel):
    """Inbound reply on `boopbox/<id>/version`.

    The box publishes its running firmware here in reply to `get_version` (and
    optionally unsolicited, e.g. on boot). `v` is the protocol version (read from
    the wire, no default, so the server version-checks it). `firmware` is the
    version string; `chip` is the chip family and must match the firmware chip subfolder
    keys (e.g. `esp32s3`) so a flash targets the box's own reported chip.
    """

    v: int
    firmware: str
    chip: str
