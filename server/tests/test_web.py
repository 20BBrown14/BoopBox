import logging

import pytest
from fastapi.testclient import TestClient

from app.config import RESERVED_ENV_NAMES, get_env
from app.main import create_app
from app.routes.web import ASSET_CACHE, NO_CACHE, RESERVED_PREFIXES

INDEX = "<!doctype html><title>BoopBox</title>"


@pytest.fixture
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX)
    (root / "color-scheme.js").write_text("// scheme")
    (root / "assets" / "index-abc123.js").write_text("// app")
    (tmp_path / "secret.txt").write_text("outside dist")
    return root


def _client(monkeypatch, web_dir: str) -> TestClient:
    monkeypatch.setenv("BOOPBOX_WEB_DIR", web_dir)
    get_env.cache_clear()
    return TestClient(create_app())


@pytest.fixture
def web(env, dist, monkeypatch):
    with _client(monkeypatch, str(dist)) as c:
        yield c


def _assert_json_404(response):
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize("path", ["/", "/devices", "/users/7", "/a/b/c?x=1"])
def test_ui_paths_get_index(web, path):
    r = web.get(path)
    assert r.status_code == 200
    assert r.text == INDEX
    assert r.headers["cache-control"] == NO_CACHE


def test_head_on_a_ui_path(web):
    r = web.head("/devices")
    assert r.status_code == 200
    assert r.headers["cache-control"] == NO_CACHE


def test_asset_is_cached_for_good(web):
    r = web.get("/assets/index-abc123.js")
    assert r.status_code == 200
    assert r.text == "// app"
    assert r.headers["cache-control"] == ASSET_CACHE


def test_missing_asset_is_a_json_404(web):
    _assert_json_404(web.get("/assets/nope.js"))


def test_top_level_file_is_served_uncached(web):
    r = web.get("/color-scheme.js")
    assert r.status_code == 200
    assert r.text == "// scheme"
    assert r.headers["cache-control"] == NO_CACHE


@pytest.mark.parametrize("prefix", RESERVED_PREFIXES)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_reserved_prefixes_never_fall_back(web, prefix, method):
    _assert_json_404(web.request(method, f"{prefix}/no-such-route"))


@pytest.mark.parametrize("path", ["/api", "/docs", "/redoc"])
def test_bare_reserved_prefix_does_not_fall_back(web, path):
    r = web.get(path)
    assert r.text != INDEX


def test_a_name_that_only_starts_like_a_prefix_is_a_ui_path(web):
    assert web.get("/apiary").text == INDEX


def test_non_get_to_a_ui_path_is_a_json_404(web):
    _assert_json_404(web.post("/devices"))


def test_real_routes_still_win(web):
    assert web.get("/health").json() == {"status": "ok"}
    assert web.get("/openapi.json").json()["info"]["title"] == "BoopBox Server"
    _assert_json_404(web.get("/api/no-such-route"))


@pytest.mark.parametrize(
    "path",
    [
        "/..%2fsecret.txt",
        "/%2e%2e/secret.txt",
        "/assets/..%2f..%2fsecret.txt",
        "/assets/%2e%2e/%2e%2e/secret.txt",
    ],
)
def test_traversal_is_a_404(web, path):
    r = web.get(path)
    assert r.status_code == 404
    assert "outside dist" not in r.text


def test_unset_dir_serves_no_ui(env, monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger="app.routes.web"):
        with _client(monkeypatch, "") as c:
            _assert_json_404(c.get("/"))
            assert c.get("/health").json() == {"status": "ok"}
    assert "not served" in caplog.text


def test_missing_dir_serves_no_ui(env, tmp_path, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="app.routes.web"):
        with _client(monkeypatch, str(tmp_path / "nope")) as c:
            _assert_json_404(c.get("/"))
    assert "not served" in caplog.text


def test_dir_without_index_serves_no_ui(env, dist, monkeypatch):
    (dist / "index.html").unlink()
    with _client(monkeypatch, str(dist)) as c:
        _assert_json_404(c.get("/"))
        _assert_json_404(c.get("/assets/index-abc123.js"))


EXPECTED_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@pytest.mark.parametrize(
    "path", ["/", "/users/7", "/color-scheme.js", "/assets/index-abc123.js"]
)
def test_ui_responses_carry_the_security_headers(web, path):
    r = web.get(path)
    assert r.status_code == 200
    assert r.headers["content-security-policy"] == EXPECTED_CSP
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_headers_are_not_duplicated(web):
    r = web.get("/")
    assert r.headers.get_list("x-content-type-options") == ["nosniff"]


@pytest.mark.parametrize(
    "path", ["/health", "/api/no-such-route", "/firmware/manifest.json"]
)
def test_other_responses_get_nosniff_only(web, path):
    r = web.get(path)
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in r.headers
    assert "referrer-policy" not in r.headers


def test_nosniff_without_the_ui(env, monkeypatch):
    with _client(monkeypatch, "") as c:
        assert c.get("/health").headers["x-content-type-options"] == "nosniff"


def test_web_dir_is_a_reserved_env_name():
    assert "BOOPBOX_WEB_DIR" in RESERVED_ENV_NAMES
