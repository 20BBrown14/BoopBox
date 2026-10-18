"""MQTT protocol version and unknown-version handling.

Stdlib-only. One global integer protocol version spans every message type
(boop, play, error, cmd); a bump is a breaking change to the whole contract.
"""

PROTOCOL_VERSION: int = 1


def is_supported(v: int) -> bool:
    """Whether the server speaks protocol version ``v``.

    Plain integer equality against ``PROTOCOL_VERSION`` (no semver). Enables two
    fail-safe behaviors, each enacted elsewhere:

    - Server receives a ``boop`` with an unsupported ``v`` -> P7 rejects it and
      publishes an ``error`` with code ``unsupported_version``.
    - A consumer receiving a higher ``v`` than it speaks ignores the message.
    """
    return v == PROTOCOL_VERSION
