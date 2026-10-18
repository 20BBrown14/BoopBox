import pytest

from app.errors import (
    ErrorCode,
    http_error,
    http_status_for,
    mqtt_error,
)
from app.models import BoopRef, Error
from app.protocol import PROTOCOL_VERSION


def test_http_status_mapping():
    assert http_status_for(ErrorCode.unauthorized) == 401
    assert http_status_for(ErrorCode.forbidden) == 403
    assert http_status_for(ErrorCode.item_unavailable) == 404
    assert http_status_for(ErrorCode.source_unavailable) == 502


@pytest.mark.parametrize(
    "code", [ErrorCode.unknown_tag, ErrorCode.unsupported_version]
)
def test_mqtt_only_codes_have_no_http_status(code):
    with pytest.raises(KeyError):
        http_status_for(code)


def test_http_error_returns_body_and_status():
    body, status = http_error(ErrorCode.forbidden, "stream token expired")
    assert body == {"code": "forbidden", "message": "stream token expired"}
    assert status == 403


def test_http_error_uses_generic_default_when_omitted():
    body, status = http_error(ErrorCode.item_unavailable)
    assert body["code"] == "item_unavailable"
    assert body["message"]  # non-empty generic message
    assert status == 404


def test_http_error_message_scrubs_upstream_detail():
    # A leaky upstream error maps to a vocabulary code with a generic message;
    # the builder only emits what the caller passes, and the default is generic.
    leaky = "Jellyfin 401: http://jellyfin:8096/Items/abc123?api_key=SECRET"
    body, _ = http_error(ErrorCode.source_unavailable)
    assert leaky not in body["message"]
    assert "jellyfin" not in body["message"].lower()
    assert "api_key" not in body["message"].lower()
    assert "SECRET" not in body["message"]


def test_mqtt_error_returns_valid_model_with_correlation_block():
    err = mqtt_error(
        ErrorCode.unknown_tag,
        BoopRef(id="b1", slug="boop/zelda"),
    )
    assert isinstance(err, Error)
    assert err.v == PROTOCOL_VERSION
    assert err.code is ErrorCode.unknown_tag
    assert err.boop == BoopRef(id="b1", slug="boop/zelda")
    assert err.message  # generic default


def test_mqtt_error_partial_boop_for_unsupported_version():
    err = mqtt_error(
        ErrorCode.unsupported_version,
        BoopRef(slug="boop/zelda"),
    )
    assert err.boop.id is None
    assert err.boop.slug == "boop/zelda"


def test_mqtt_error_scrubs_upstream_detail_by_default():
    leaky = "Jellyfin 404 body: item abc123 not found at http://jellyfin:8096"
    err = mqtt_error(ErrorCode.item_unavailable, BoopRef(id="b1", slug="s"))
    assert leaky not in err.message
    assert "jellyfin" not in err.message.lower()
