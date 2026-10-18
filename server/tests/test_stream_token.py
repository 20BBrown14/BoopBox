import inspect

from app.errors import ErrorCode
from app.stream_token import mint, verify
from app.types.token import StreamClaims

SECRET = "test-secret"
BUDGET = 1800


def _claims(exp: int = 0) -> StreamClaims:
    return StreamClaims(device="boop-test", source="jellyfin", item="abc123", exp=exp)


def test_round_trip_returns_original_claims():
    now = 1_000_000
    token = mint(_claims(), duration=1200, now=now, secret=SECRET, pause_budget=BUDGET)
    result = verify(token, now=now + 10, secret=SECRET)
    assert isinstance(result, StreamClaims)
    assert result.device == "boop-test"
    assert result.source == "jellyfin"
    assert result.item == "abc123"
    assert result.exp == now + 1200 + BUDGET


def test_tampered_body_is_forbidden():
    now = 1_000_000
    token = mint(_claims(), duration=1200, now=now, secret=SECRET, pause_budget=BUDGET)
    body, _, mac = token.partition(".")
    flipped = ("Z" if body[0] != "Z" else "Y") + body[1:]
    tampered = f"{flipped}.{mac}"
    assert verify(tampered, now=now + 10, secret=SECRET) is ErrorCode.forbidden


def test_tampered_mac_is_forbidden():
    now = 1_000_000
    token = mint(_claims(), duration=1200, now=now, secret=SECRET, pause_budget=BUDGET)
    body, _, mac = token.partition(".")
    flipped = ("Z" if mac[0] != "Z" else "Y") + mac[1:]
    tampered = f"{body}.{flipped}"
    assert verify(tampered, now=now + 10, secret=SECRET) is ErrorCode.forbidden


def test_wrong_secret_is_forbidden():
    now = 1_000_000
    token = mint(_claims(), duration=1200, now=now, secret=SECRET, pause_budget=BUDGET)
    assert verify(token, now=now + 10, secret="other-secret") is ErrorCode.forbidden


def test_missing_dot_is_unauthorized():
    assert verify("justonepart", now=1, secret=SECRET) is ErrorCode.unauthorized


def test_empty_token_is_unauthorized():
    assert verify("", now=1, secret=SECRET) is ErrorCode.unauthorized


def test_one_part_with_trailing_dot_is_unauthorized():
    assert verify("body.", now=1, secret=SECRET) is ErrorCode.unauthorized
    assert verify(".mac", now=1, secret=SECRET) is ErrorCode.unauthorized


def test_non_base64_mac_is_unauthorized():
    # A well-formed shape but a mac that isn't valid base64url.
    assert verify("body.!!!!", now=1, secret=SECRET) is ErrorCode.unauthorized


def test_expired_is_forbidden():
    now = 1_000_000
    token = mint(_claims(), duration=None, now=now, secret=SECRET, pause_budget=1)
    # exp == now + 1; verify well past it.
    assert verify(token, now=now + 100, secret=SECRET) is ErrorCode.forbidden


def test_exactly_at_exp_is_forbidden():
    now = 1_000_000
    token = mint(_claims(), duration=None, now=now, secret=SECRET, pause_budget=10)
    assert verify(token, now=now + 10, secret=SECRET) is ErrorCode.forbidden


def test_uses_constant_time_compare():
    src = inspect.getsource(verify)
    assert "compare_digest" in src


def test_exp_known_duration():
    now = 500
    token = mint(_claims(), duration=1200, now=now, secret=SECRET, pause_budget=BUDGET)
    result = verify(token, now=now, secret=SECRET)
    assert isinstance(result, StreamClaims)
    assert result.exp == now + 1200 + BUDGET


def test_exp_no_duration_uses_budget():
    now = 500
    token = mint(_claims(), duration=None, now=now, secret=SECRET, pause_budget=BUDGET)
    result = verify(token, now=now, secret=SECRET)
    assert isinstance(result, StreamClaims)
    assert result.exp == now + BUDGET


def test_exp_no_duration_no_budget_falls_back_to_300():
    now = 500
    token = mint(_claims(), duration=None, now=now, secret=SECRET, pause_budget=0)
    result = verify(token, now=now, secret=SECRET)
    assert isinstance(result, StreamClaims)
    assert result.exp == now + 300


def test_server_clock_only_same_token_valid_then_expired():
    now = 1_000_000
    token = mint(_claims(), duration=0, now=now, secret=SECRET, pause_budget=60)
    # exp == now + 60. Valid before, expired after, purely from `now`.
    assert isinstance(verify(token, now=now + 30, secret=SECRET), StreamClaims)
    assert verify(token, now=now + 60, secret=SECRET) is ErrorCode.forbidden
    assert verify(token, now=now + 90, secret=SECRET) is ErrorCode.forbidden


def test_acceptance_20_minute_item_default_budget():
    now = 1_700_000_000
    token = mint(_claims(), duration=1200, now=now, secret=SECRET, pause_budget=1800)
    result = verify(token, now=now + 600, secret=SECRET)
    assert isinstance(result, StreamClaims)
    assert result.exp == now + 3000  # ~50 min
