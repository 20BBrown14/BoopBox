from app.errors import ErrorCode
from app.models import Boop, BoopRef, Cmd, CmdName, Error, Play
from app.protocol import PROTOCOL_VERSION

BOOP_JSON = {
    "v": 1,
    "id": "b1",
    "slug": "boop/zelda",
    "uid": "04:A3:FF",
    "ts": 1760000000,
}


def test_boop_round_trips_design_shape():
    boop = Boop.model_validate(BOOP_JSON)
    assert boop.slug == "boop/zelda"
    assert boop.ts == 1760000000
    assert boop.model_dump() == BOOP_JSON


def test_play_with_boop_block():
    play = Play(
        boop=BoopRef(id="b1", slug="boop/zelda"),
        url="http://server/stream?sig=tok",
        title="Song Title",
        duration=184,
        album="Album Title",
        artist="Artist Name",
    )
    dumped = play.model_dump()
    assert dumped["v"] == PROTOCOL_VERSION
    assert dumped["boop"] == {"id": "b1", "slug": "boop/zelda"}
    assert dumped["url"] == "http://server/stream?sig=tok"
    assert dumped["duration"] == 184


def test_play_without_boop_block():
    play = Play(url="http://server/stream?sig=tok")
    assert play.boop is None
    assert play.model_dump()["boop"] is None


def test_play_parses_sample_payload():
    play = Play.model_validate(
        {
            "v": 1,
            "boop": {"id": "b1", "slug": "boop/zelda"},
            "url": "http://server/stream?sig=tok",
            "title": "Song Title",
            "duration": 184,
            "album": "Album Title",
            "artist": "Artist Name",
        }
    )
    assert play.boop.id == "b1"
    assert play.artist == "Artist Name"


def test_error_with_full_boop_block():
    err = Error(
        boop=BoopRef(id="b1", slug="boop/zelda"),
        code=ErrorCode.unknown_tag,
        message="no mapping for slug 'boop/zelda'",
    )
    dumped = err.model_dump()
    assert dumped["v"] == PROTOCOL_VERSION
    assert dumped["boop"] == {"id": "b1", "slug": "boop/zelda"}
    assert dumped["code"] == "unknown_tag"


def test_error_partial_boop_for_unsupported_version():
    # Only the slug was parseable before hitting the unknown v.
    err = Error(
        boop=BoopRef(slug="boop/zelda"),
        code=ErrorCode.unsupported_version,
        message="unsupported protocol version",
    )
    assert err.boop.id is None
    assert err.boop.slug == "boop/zelda"


def test_error_absent_boop_for_unsupported_version():
    err = Error(
        code=ErrorCode.unsupported_version,
        message="unsupported protocol version",
    )
    assert err.boop is None


def test_error_code_serializes_to_lowercase_string():
    err = Error(code=ErrorCode.source_unavailable, message="x")
    assert err.model_dump()["code"] == "source_unavailable"
    assert '"code":"source_unavailable"' in err.model_dump_json().replace(" ", "")


def test_cmd_defaults_and_shape():
    cmd = Cmd(cmd=CmdName.check_update)
    dumped = cmd.model_dump()
    assert dumped["v"] == PROTOCOL_VERSION
    assert dumped["cmd"] == "check_update"


def test_outbound_models_default_version():
    assert Play(url="u").v == PROTOCOL_VERSION
    assert Error(code=ErrorCode.forbidden, message="x").v == PROTOCOL_VERSION
    assert Cmd(cmd=CmdName.check_update).v == PROTOCOL_VERSION
