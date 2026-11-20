"""Framework-raised errors use the {code, message, field} shape."""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import create_app

SECRET_INPUT = "do-not-echo-this-value"


class Inner(BaseModel):
    count: int


class Outer(BaseModel):
    name: str
    items: list[Inner]


@pytest.fixture
def client(env):
    app = create_app()

    @app.post("/api/_test/nested")
    async def _nested(body: Outer):
        return {}

    @app.get("/api/_test/query")
    async def _query(limit: int):
        return {}

    with TestClient(app) as c:
        yield c


def test_missing_body_field(client):
    r = client.post("/api/auth/token", json={"username": "someone"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "invalid_request"
    assert body["field"] == "password"
    assert body["message"]


def test_nested_field_is_dotted(client):
    r = client.post(
        "/api/_test/nested",
        json={"name": "x", "items": [{"count": 1}, {"count": SECRET_INPUT}]},
    )
    assert r.status_code == 422
    assert r.json()["field"] == "items.1.count"
    assert SECRET_INPUT not in r.text


def test_query_field_drops_location(client):
    r = client.get("/api/_test/query", params={"limit": SECRET_INPUT})
    assert r.status_code == 422
    assert r.json()["field"] == "limit"
    assert SECRET_INPUT not in r.text


def test_malformed_json_has_no_field(client):
    r = client.post(
        "/api/auth/token",
        content=b'{"username": ',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"
    assert "field" not in r.json()


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/no-such-thing")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"code": "not_found", "message": "not found"}


def test_other_http_errors_keep_the_default(client):
    r = client.get("/api/auth/token")
    assert r.status_code == 405
    assert r.json() == {"detail": "Method Not Allowed"}
