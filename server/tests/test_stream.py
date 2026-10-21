import textwrap
import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.errors import ErrorCode, default_message
from app.main import create_app
from app.sources import FakeSource, SourceRegistry
from app.stream_token import mint
from app.types.token import StreamClaims

SECRET = "s3cret"
SOURCE_ID = "fake-main"
ITEM = "fake-item"
DATA = bytes(range(256)) * 8  # 2048 deterministic bytes

CONFIG = textwrap.dedent(
    """
    sources: []
    mappings: {}
    """
)


def _claims(exp: int = 0, item: str = ITEM) -> StreamClaims:
    return StreamClaims(device="boop-test", source=SOURCE_ID, item=item, exp=exp)


def _token(now: int, *, duration: int | None = 180, item: str = ITEM) -> str:
    return mint(
        _claims(item=item),
        duration=duration,
        now=now,
        secret=SECRET,
        pause_budget=1800,
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG)
    monkeypatch.setenv("BOOPBOX_STREAM_SECRET", SECRET)
    monkeypatch.setenv("BOOPBOX_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("BOOPBOX_DB_PATH", str(tmp_path / "devices.db"))
    get_settings.cache_clear()

    fake = FakeSource(data=DATA, known_item=ITEM)
    with TestClient(create_app()) as c:
        # Swap in a test registry after startup built the (empty) real one.
        c.app.state.sources = SourceRegistry({SOURCE_ID: fake})
        c.fake = fake  # type: ignore[attr-defined]
        yield c

    get_settings.cache_clear()


def test_happy_path_full(client):
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}")
    assert r.status_code == 200
    assert r.content == DATA
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["content-length"] == str(len(DATA))
    assert r.headers["accept-ranges"] == "bytes"
    assert "content-range" not in r.headers


def test_range_forwarded(client):
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.content == DATA[10:20]
    assert r.headers["content-range"] == f"bytes 10-19/{len(DATA)}"
    assert r.headers["content-length"] == "10"
    assert r.headers["accept-ranges"] == "bytes"


def test_open_ended_range(client):
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}", headers={"Range": "bytes=2000-"})
    assert r.status_code == 206
    assert r.content == DATA[2000:]
    assert r.headers["content-range"] == f"bytes 2000-{len(DATA) - 1}/{len(DATA)}"


def test_suffix_range(client):
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}", headers={"Range": "bytes=-48"})
    assert r.status_code == 206
    assert r.content == DATA[-48:]
    start = len(DATA) - 48
    assert r.headers["content-range"] == f"bytes {start}-{len(DATA) - 1}/{len(DATA)}"


def test_malformed_range_ignored_serves_full(client):
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}", headers={"Range": "chunks=0-10"})
    assert r.status_code == 200
    assert r.content == DATA


def test_unsatisfiable_range_is_416(client):
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}", headers={"Range": f"bytes={len(DATA)}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(DATA)}"


def test_missing_sig_is_401(client):
    r = client.get("/stream")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_garbled_token_is_401(client):
    r = client.get("/stream?sig=not-a-real-token")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_tampered_token_is_403(client):
    token = _token(int(time.time()))
    body, _, mac = token.partition(".")
    flipped = ("Z" if mac[0] != "Z" else "Y") + mac[1:]
    r = client.get(f"/stream?sig={body}.{flipped}")
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"


def test_expired_token_is_403(client):
    past = int(time.time()) - 10_000
    token = _token(past, duration=0)  # exp = past + 1800, well before now
    r = client.get(f"/stream?sig={token}")
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"


def test_missing_item_is_404(client):
    token = _token(int(time.time()), item="no-such-item")
    r = client.get(f"/stream?sig={token}")
    assert r.status_code == 404
    assert r.json()["code"] == "item_unavailable"


def test_source_down_is_502(client):
    client.fake._fail_with = ErrorCode.source_unavailable
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}")
    assert r.status_code == 502
    assert r.json()["code"] == "source_unavailable"


def test_error_message_is_scrubbed(client):
    client.fake._fail_with = ErrorCode.source_unavailable
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}")
    assert r.json()["message"] == default_message(ErrorCode.source_unavailable)
    assert "fake forced" not in r.text


def test_cleanup_runs_on_completion(client):
    token = _token(int(time.time()))
    r = client.get(f"/stream?sig={token}")
    assert r.status_code == 200
    assert client.fake.last_stream is not None
    assert client.fake.last_stream.closed is True
