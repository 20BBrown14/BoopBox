"""Session cookie and CSRF helpers."""

from http.cookies import SimpleCookie

import pytest
from fastapi import Request, Response

from app.auth.session import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    clear_session,
    csrf_matches,
    csrf_token,
    request_is_https,
    set_session,
)

JWT = "header.payload.signature"
SECRET = "s" * 32


def _request(scheme: str = "http", headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": scheme,
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "server": ("boopbox.local", 9685),
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
            ],
        }
    )


def _cookies(response: Response) -> dict[str, SimpleCookie]:
    parsed = {}
    for name, value in response.raw_headers:
        if name == b"set-cookie":
            cookie = SimpleCookie(value.decode())
            parsed.update({key: cookie[key] for key in cookie})
    return parsed


# --- request_is_https ---


def test_scheme_decides_without_trust():
    assert request_is_https(_request("https"), False)
    assert not request_is_https(_request("http"), False)


def test_forwarded_proto_ignored_without_trust():
    request = _request("http", {"X-Forwarded-Proto": "https"})
    assert not request_is_https(request, False)


def test_forwarded_proto_used_with_trust():
    assert request_is_https(_request("http", {"X-Forwarded-Proto": "https"}), True)
    assert not request_is_https(_request("https", {"X-Forwarded-Proto": "http"}), True)


def test_rightmost_forwarded_proto_wins():
    request = _request("http", {"X-Forwarded-Proto": "https, http"})
    assert not request_is_https(request, True)
    request = _request("http", {"X-Forwarded-Proto": "http, HTTPS"})
    assert request_is_https(request, True)


def test_trust_without_header_falls_back_to_scheme():
    assert request_is_https(_request("https"), True)
    assert not request_is_https(_request("http"), True)


# --- CSRF ---


def test_csrf_is_deterministic_and_base64url():
    token = csrf_token(JWT, SECRET)
    assert token == csrf_token(JWT, SECRET)
    assert "=" not in token and "+" not in token and "/" not in token


def test_csrf_depends_on_jwt_and_secret():
    token = csrf_token(JWT, SECRET)
    assert token != csrf_token(JWT + "x", SECRET)
    assert token != csrf_token(JWT, "t" * 32)


@pytest.mark.parametrize("presented", [None, "", "wrong", "é"])
def test_csrf_mismatch(presented):
    assert not csrf_matches(JWT, SECRET, presented)


def test_csrf_match():
    assert csrf_matches(JWT, SECRET, csrf_token(JWT, SECRET))


# --- cookies ---


@pytest.mark.parametrize("secure", [True, False])
def test_set_session_cookie_attributes(secure):
    response = Response()
    set_session(response, JWT, secret=SECRET, max_age=3600, secure=secure)
    cookies = _cookies(response)

    session = cookies[SESSION_COOKIE]
    assert session.value == JWT
    assert session["httponly"] is True
    assert session["samesite"] == "strict"
    assert session["path"] == "/api"
    assert session["max-age"] == "3600"
    assert bool(session["secure"]) is secure

    csrf = cookies[CSRF_COOKIE]
    assert csrf.value == csrf_token(JWT, SECRET)
    assert not csrf["httponly"]
    assert csrf["samesite"] == "strict"
    assert csrf["path"] == "/"
    assert csrf["max-age"] == "3600"
    assert bool(csrf["secure"]) is secure


@pytest.mark.parametrize("secure", [True, False])
def test_clear_session_expires_both_on_their_paths(secure):
    response = Response()
    clear_session(response, secure=secure)
    cookies = _cookies(response)
    assert cookies[SESSION_COOKIE]["path"] == "/api"
    assert cookies[CSRF_COOKIE]["path"] == "/"
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        assert cookies[name].value == ""
        assert cookies[name]["max-age"] == "0"
        assert bool(cookies[name]["secure"]) is secure
