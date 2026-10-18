from dataclasses import dataclass


@dataclass(frozen=True)
class StreamClaims:
    """Claims carried by the opaque stream token.

    `device` is provenance only (who booped); it is recorded, not used to
    authorize the stream requester. `exp` is unix seconds on the server clock.
    """

    device: str
    source: str
    item: str
    exp: int
