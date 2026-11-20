"""require_json_same_origin, exercised through POST /api/auth/token."""

import pytest
from fastapi.testclient import TestClient

from app.auth.session import same_origin
from app.config import get_env
from app.main import create_app
from tests.conftest import OWNER, OWNER_PASSWORD

CREDENTIALS = {"username": OWNER, "password": OWNER_PASSWORD}


def _login(client, headers=None):
    return client.post("/api/auth/token", json=CREDENTIALS, headers=headers)


@pytest.fixture
def trusting_client(env, monkeypatch):
    monkeypatch.setenv("BOOPBOX_AUTH_TRUST_FORWARDED_HEADER", "true")
    get_env.cache_clear()
    with TestClient(create_app()) as c:
        yield c


def test_no_origin_passes(client):
    assert _login(client).status_code == 200


def test_matching_origin_passes(client):
    assert _login(client, {"Origin": "http://testserver"}).status_code == 200


@pytest.mark.parametrize(
    "origin",
    ["http://evil.example", "http://testserver:8080", "null", "file://testserver"],
)
def test_foreign_origin_is_403(client, origin):
    r = _login(client, {"Origin": origin})
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"


def test_form_body_is_422(client):
    r = client.post("/api/auth/token", data=CREDENTIALS)
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"


def test_json_with_charset_passes(client):
    r = client.post(
        "/api/auth/token",
        content=f'{{"username": "{OWNER}", "password": "{OWNER_PASSWORD}"}}',
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert r.status_code == 200


def test_text_plain_json_is_422(client):
    r = client.post(
        "/api/auth/token",
        content=f'{{"username": "{OWNER}", "password": "{OWNER_PASSWORD}"}}',
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 422


def test_forwarded_host_ignored_without_trust(client):
    headers = {"Origin": "https://boop.example", "X-Forwarded-Host": "boop.example"}
    assert _login(client, headers).status_code == 403


def test_forwarded_host_used_with_trust(trusting_client):
    headers = {"Origin": "https://boop.example", "X-Forwarded-Host": "boop.example"}
    assert _login(trusting_client, headers).status_code == 200
    headers["Origin"] = "https://evil.example"
    assert _login(trusting_client, headers).status_code == 403


@pytest.mark.parametrize(
    ("origin", "host", "expected"),
    [
        ("http://boop.local:9685", "boop.local:9685", True),
        ("https://boop.example", "boop.example", True),
        ("https://boop.example", "boop.example:443", True),
        ("http://BOOP.local:9685", "boop.local:9685", True),
        ("http://[::1]:9685", "[::1]:9685", True),
        ("https://boop.example", "boop.example:9685", False),
        ("http://boop.local:9685", "", False),
        ("http://boop.local:99999", "boop.local:99999", False),
    ],
)
def test_same_origin(origin, host, expected):
    assert same_origin(origin, host) is expected
