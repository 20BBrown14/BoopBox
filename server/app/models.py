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
    elsewhere (P2/P7).
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
    check_update = "check_update"


class Cmd(BaseModel):
    """Command published to `boopbox/<id>/cmd` or `boopbox/all/cmd`."""

    v: int = PROTOCOL_VERSION
    cmd: CmdName
