"""Pure HMAC stream-token mint and verify.

Dependency-free (stdlib only, no `Settings`, no clock of its own): the secret,
pause budget, and `now` are all passed in by the caller (P6/P7 source them from
`Settings` and the real clock). This keeps the single-server-clock rule honest
and the module trivially unit-testable.

Token format (must match the design exactly):

    claims = {device, source, item, exp}   # exp is unix seconds, server clock
    body   = base64url(json(claims))        # deterministic JSON, no padding
    mac    = HMAC-SHA256(secret, body)      # body is the ASCII token text
    token  = body + "." + base64url(mac)    # the opaque <token> in ?sig=<token>

base64url variant is url-safe, padding stripped, for both `body` and `mac`;
verify decodes the same variant. JSON is sorted-keys, no spaces, so identical
claims always produce an identical `body`.

Verify fails as `unauthorized` (can't parse) vs `forbidden` (parsed, rejected),
matching the 401/403 boundary; P6 turns the code into an HTTP status.
"""

import base64
import binascii
import hashlib
import hmac
import json

from app.errors import ErrorCode
from app.types.token import StreamClaims

# Final fallback window when neither item duration nor pause budget is known.
_FALLBACK_EXP_SECONDS = 300


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    # validate=True so non-alphabet characters raise instead of being silently
    # dropped; a malformed token must be rejected as malformed, not slip through.
    translated = text.replace("-", "+").replace("_", "/")
    padding = "=" * (-len(translated) % 4)
    return base64.b64decode(translated + padding, validate=True)


def _mac(secret: str, body: str) -> bytes:
    return hmac.new(
        secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).digest()


def mint(
    claims: StreamClaims,
    duration: int | None,
    now: int,
    *,
    secret: str,
    pause_budget: int,
) -> str:
    """Mint the opaque token for `claims`, computing `exp` from `now`.

    Duration-aware expiry:
        known duration    -> exp = now + duration + pause_budget
        no duration       -> exp = now + pause_budget
        neither           -> exp = now + 300  (final fallback)

    `claims.exp` on the input is ignored; the computed `exp` is authoritative.
    """
    if duration is not None:
        exp = now + duration + pause_budget
    elif pause_budget:
        exp = now + pause_budget
    else:
        exp = now + _FALLBACK_EXP_SECONDS

    payload = {
        "device": claims.device,
        "source": claims.source,
        "item": claims.item,
        "exp": exp,
    }
    body = _b64url_encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    mac = _b64url_encode(_mac(secret, body))
    return f"{body}.{mac}"


def verify(token: str, now: int, *, secret: str) -> StreamClaims | ErrorCode:
    """Verify `token` and return its claims, or an error code.

    Strict order, failing at the first failure:
      1. split/shape/base64 of the mac       -> unauthorized (malformed)
      2. HMAC constant-time compare           -> forbidden on mismatch
      3. decode body JSON (only after 2)      -> unauthorized (malformed)
      4. exp <= now                           -> forbidden (expired)
      5. return claims

    A valid MAC over structurally broken claims is malformed (401), not a
    rejection (403): the MAC proved authenticity, the payload is simply garbage.
    """
    # Step 1: shape + mac base64.
    body, sep, mac_part = token.partition(".")
    if not sep or not body or not mac_part:
        return ErrorCode.unauthorized
    try:
        provided_mac = _b64url_decode(mac_part)
    except (binascii.Error, ValueError):
        return ErrorCode.unauthorized

    # Step 2: constant-time MAC compare.
    if not hmac.compare_digest(provided_mac, _mac(secret, body)):
        return ErrorCode.forbidden

    # Step 3: decode body only after the MAC verifies.
    try:
        payload = json.loads(_b64url_decode(body))
    except (binascii.Error, ValueError):
        return ErrorCode.unauthorized
    if not isinstance(payload, dict):
        return ErrorCode.unauthorized
    try:
        claims = StreamClaims(
            device=payload["device"],
            source=payload["source"],
            item=payload["item"],
            exp=payload["exp"],
        )
    except (KeyError, TypeError):
        return ErrorCode.unauthorized
    if not isinstance(claims.exp, int) or isinstance(claims.exp, bool):
        return ErrorCode.unauthorized

    # Step 4: expiry against the passed-in server clock.
    if claims.exp <= now:
        return ErrorCode.forbidden

    # Step 5.
    return claims
