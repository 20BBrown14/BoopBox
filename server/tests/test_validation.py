import pytest

from app.errors import ApiError, ErrorCode
from app.validation import (
    clean,
    email_problem,
    length_problem,
    require,
    single_line_problem,
)

# "e" plus a combining acute accent: two code points that NFC makes one "é".
DECOMPOSED_E = "e\u0301"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Kid  ", "Kid"),
        ("\t\nKid\r\n", "Kid"),
        ("\u00a0Kid\u3000", "Kid"),
        ("Ki d", "Ki d"),
        (f"Ren{DECOMPOSED_E}e", "Renée"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_clean_trims_then_normalizes(raw, expected):
    assert clean(raw) == expected


def test_clean_makes_combining_characters_shorter():
    raw = DECOMPOSED_E * 3
    assert len(raw) == 6
    assert len(clean(raw)) == 3


@pytest.mark.parametrize("value", ["Kid", "Renée", "🙂 emoji", "👩‍👩‍👧 family", ""])
def test_single_line_accepts_ordinary_text(value):
    assert single_line_problem(value) is None


@pytest.mark.parametrize(
    "value",
    ["a\nb", "a\rb", "a\tb", "a\x00b", "a\x1bb", "a\x7fb", "a\x85b", "a\u2028b"],
)
def test_single_line_rejects_breaks_and_controls(value):
    assert single_line_problem(value) is not None


@pytest.mark.parametrize(
    ("value", "min", "max", "ok"),
    [
        ("", 1, 64, False),
        ("a", 1, 64, True),
        ("a" * 64, 1, 64, True),
        ("a" * 65, 1, 64, False),
        ("", 0, 64, True),
        ("🙂" * 64, 1, 64, True),
        ("🙂" * 65, 1, 64, False),
    ],
)
def test_length_counts_code_points(value, min, max, ok):
    assert (length_problem(value, min, max) is None) is ok


def test_length_after_clean_uses_the_shorter_form():
    raw = DECOMPOSED_E * 64
    assert length_problem(raw, 1, 64) is not None
    assert length_problem(clean(raw), 1, 64) is None


def test_padding_does_not_count_once_cleaned():
    assert length_problem(clean("  " + "a" * 64 + "  "), 1, 64) is None


def test_length_messages():
    assert length_problem("", 1, 64) == "must be 1 to 64 characters"
    assert length_problem("a" * 65, 0, 64) == "must be at most 64 characters"


@pytest.mark.parametrize("value", ["kid@example.com", "a@b", "ü@exämple.de"])
def test_email_accepts(value):
    assert email_problem(value) is None


@pytest.mark.parametrize(
    "value", ["", "kid", "@example.com", "kid@", "kid@@example.com", "a@b@c"]
)
def test_email_needs_exactly_one_at_with_both_sides(value):
    assert email_problem(value) == "must be an email address"


def test_email_length_limit():
    domain = "@example.com"
    assert email_problem("a" * (254 - len(domain)) + domain) is None
    assert (
        email_problem("a" * (255 - len(domain)) + domain)
        == "must be at most 254 characters"
    )


def test_require_passes_without_a_problem():
    require(None, "display_name")


def test_require_raises_invalid_request_on_the_field():
    with pytest.raises(ApiError) as caught:
        require("must be 1 to 64 characters", "display_name")
    assert caught.value.code == ErrorCode.invalid_request
    assert caught.value.message == "must be 1 to 64 characters"
    assert caught.value.field == "display_name"
