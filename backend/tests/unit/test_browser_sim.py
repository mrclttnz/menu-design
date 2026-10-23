"""Il "browser" di prova legge i cookie come li legge un browser vero (SL-03a, SR-005, SR-037).

I test dell'accesso controllano gli attributi dei cookie `__Host-` con questo lettore: se sbagliasse
a riconoscere `HttpOnly`, `Secure`, `SameSite` o la cancellazione, un cookie scorretto passerebbe.
"""

import httpx
import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from support.auth_checks import assert_cookie, hashes_of, leaks
from support.browser_sim import Browser, parse_set_cookies

SESSION = "__Host-session=abc123_-XYZ; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Lax"


def _response(*cookies: str) -> httpx.Response:
    return httpx.Response(200, headers=[("set-cookie", c) for c in cookies])


def test_attributes_are_read_with_flags_as_booleans() -> None:
    (cookie,) = parse_set_cookies(_response(SESSION))
    assert cookie.name == "__Host-session"
    assert cookie.value == "abc123_-XYZ"
    assert cookie.flag("secure")
    assert cookie.flag("httponly")
    assert cookie.attrs["samesite"] == "Lax"
    assert cookie.attrs["path"] == "/"
    assert cookie.attrs["max-age"] == "2592000"
    assert "domain" not in cookie.attrs
    assert not cookie.deleted
    assert_cookie(cookie, http_only=True, same_site="Lax", max_age=2592000)


def test_a_missing_flag_is_not_reported_as_present() -> None:
    (cookie,) = parse_set_cookies(_response("__Host-csrf=t0ken; Path=/; Secure; SameSite=Strict"))
    assert not cookie.flag("httponly")
    assert cookie.flag("secure")
    assert_cookie(cookie, http_only=False, same_site="Strict")
    with pytest.raises(AssertionError, match="HttpOnly"):
        assert_cookie(cookie, http_only=True, same_site="Strict")


@pytest.mark.parametrize(
    ("header", "message"),
    [
        ("__Host-a=v; Path=/; HttpOnly; SameSite=Lax", "Secure"),
        ("__Host-a=v; Path=/x; Secure; HttpOnly; SameSite=Lax", "Path"),
        ("__Host-a=v; Path=/; Domain=example.test; Secure; HttpOnly; SameSite=Lax", "Domain"),
        ("__Host-a=v; Path=/; Secure; HttpOnly; SameSite=None", "a"),
        ("__Host-a=v; Path=/; Secure; HttpOnly", "a"),
        ("plain=v; Path=/; Secure; HttpOnly; SameSite=Lax", "plain"),
    ],
)
def test_assert_cookie_catches_each_mistake(header: str, message: str) -> None:
    (cookie,) = parse_set_cookies(_response(header))
    with pytest.raises(AssertionError, match=message):
        assert_cookie(cookie, http_only=True, same_site="Lax")


@pytest.mark.parametrize(
    "header",
    [
        "__Host-session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax",
        "__Host-session=gone; Max-Age=0; Path=/; Secure",
        "__Host-session=gone; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/; Secure",
    ],
)
def test_deletions_are_recognised(header: str) -> None:
    (cookie,) = parse_set_cookies(_response(header))
    assert cookie.deleted


def test_several_cookies_in_one_response_are_all_read() -> None:
    cookies = parse_set_cookies(
        _response(SESSION, "__Host-csrf=t; Path=/; Secure; SameSite=Strict")
    )
    assert [c.name for c in cookies] == ["__Host-session", "__Host-csrf"]


def test_leak_search_finds_a_secret_in_text_hex_and_decoded_forms() -> None:
    token = "q83Zz2uV0xKj9mL4pN7rT1yB6cD5eF8gH3iJ0kA2sW4"  # noqa: S105
    assert leaks(f"row: {token}", token)
    assert leaks("row: \\x" + token.encode().hex(), token)
    assert not leaks("row: niente di tutto questo", token)
    assert len(hashes_of(token)) == 2, "testo UTF-8 e byte base64url"


# --- il Browser sopra un'app minima -------------------------------------------------


def _echo_app() -> TestClient:
    app = FastAPI()

    @app.get("/set")
    def set_cookie(response: Response) -> dict[str, bool]:
        response.set_cookie(
            "__Host-x", "valore", secure=True, httponly=True, samesite="lax", path="/", max_age=60
        )
        return {"ok": True}

    @app.get("/drop")
    def drop(response: Response) -> dict[str, bool]:
        response.delete_cookie("__Host-x", secure=True, httponly=True, samesite="lax", path="/")
        return {"ok": True}

    @app.api_route("/echo", methods=["GET", "POST"])
    def echo(request: Request) -> dict[str, str]:
        return dict(request.headers)

    return TestClient(app, base_url="https://testserver")


def test_cookies_are_kept_per_browser_and_sent_as_a_cookie_header() -> None:
    client = _echo_app()
    one, two = Browser(client), Browser(client)
    one.get("/set")
    assert one.cookies == {"__Host-x": "valore"}
    assert two.cookies == {}
    assert one.get("/echo").json()["cookie"] == "__Host-x=valore"
    assert "cookie" not in two.get("/echo").json()
    assert "cookie" not in one.get("/echo", send_cookies=False).json()
    assert client.cookies.get("__Host-x") is None, "il vasetto del client resta vuoto"
    one.get("/drop")
    assert one.cookies == {}, "la cancellazione toglie il cookie"


def test_unsafe_requests_carry_origin_fetch_metadata_and_csrf_header() -> None:
    sent = Browser(_echo_app()).post("/echo", {"a": 1}, csrf="token-123").json()
    assert sent["origin"] == "https://testserver"
    assert sent["sec-fetch-site"] == "same-origin"
    assert sent["x-csrf-token"] == "token-123"
    assert sent["content-type"] == "application/json"


def test_origin_csrf_and_content_type_can_be_withheld_or_replaced() -> None:
    browser = Browser(_echo_app())
    bare = browser.post("/echo", {}, origin=None, sec_fetch_site=None, content_type="text/plain")
    sent = bare.json()
    assert "origin" not in sent
    assert "sec-fetch-site" not in sent
    assert "x-csrf-token" not in sent
    assert sent["content-type"] == "text/plain"
    assert browser.get("/echo").json().get("origin") is None, "le GET non portano Origin"
    assert browser.post("/echo", {}, content_type=None).json().get("content-type") is None
    empty = browser.post("/echo", {}, csrf="").json()
    assert empty["x-csrf-token"] == ""


def test_a_raw_body_is_sent_as_is_and_extra_headers_win() -> None:
    sent = Browser(_echo_app()).request(
        "POST", "/echo", content=b"x" * 10, headers={"X-Custom": "1", "Cookie": "a=b"}
    )
    assert sent.json()["x-custom"] == "1"
    assert sent.json()["cookie"] == "a=b"
