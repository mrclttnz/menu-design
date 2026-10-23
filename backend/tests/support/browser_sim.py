"""Un "browser" minimo sopra il `TestClient`: cookie, intestazioni e flusso di accesso (SL-03a).

Il `TestClient` ha un solo vasetto di cookie; per simulare più browser (la vittima e
l'aggressore, due dispositivi) ogni `Browser` tiene i propri cookie e li invia come
intestazione `Cookie`; il vasetto del client si svuota a ogni richiesta. Le intestazioni
`Set-Cookie` sono lette per intero, così i test controllano gli attributi (SR-005, SR-037).
"""

import json as json_module
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from support.fake_oidc import FakeOidc, Identity, TokenOptions

ORIGIN = "https://testserver"
SESSION, CSRF, FLOW = "__Host-session", "__Host-csrf", "__Host-auth_flow"
CALLBACK = "/api/v1/auth/google/callback"
UA_PHONE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Mobile Safari/537.36"
)


@dataclass(frozen=True)
class SetCookie:
    name: str
    value: str
    attrs: dict[str, str]

    @property
    def deleted(self) -> bool:
        if self.value == "" or self.attrs.get("max-age") == "0":
            return True
        expires = self.attrs.get("expires")
        if expires and "max-age" not in self.attrs:
            when = parsedate_to_datetime(expires)
            return when < datetime.now(UTC)
        return False

    def flag(self, name: str) -> bool:
        return bool(self.attrs.get(name))


def parse_set_cookies(response: Response) -> list[SetCookie]:
    out = []
    for header in response.headers.get_list("set-cookie"):
        jar: SimpleCookie = SimpleCookie()
        jar.load(header)
        for name, morsel in jar.items():
            attrs = {k: v for k, v in morsel.items() if v != ""} | {
                k: "1" for k, v in morsel.items() if v is True
            }
            out.append(SetCookie(name, morsel.value, {k.lower(): str(v) for k, v in attrs.items()}))
    return out


def raw_set_cookie_headers(response: Response, name: str) -> list[str]:
    return [h for h in response.headers.get_list("set-cookie") if h.startswith(f"{name}=")]


@dataclass
class Browser:
    client: TestClient
    cookies: dict[str, str] = field(default_factory=dict)
    user_agent: str = UA_PHONE
    last_cookies: list[SetCookie] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        send_cookies: bool = True,
        csrf: str | None = None,
        origin: str | None = ORIGIN,
        sec_fetch_site: str | None = "same-origin",
        content_type: str | None = "application/json",
    ) -> Response:
        sent: dict[str, str] = {"user-agent": self.user_agent}
        if method not in ("GET", "HEAD", "OPTIONS"):
            if origin is not None:
                sent["origin"] = origin
            if sec_fetch_site is not None:
                sent["sec-fetch-site"] = sec_fetch_site
            if csrf is not None:
                sent["x-csrf-token"] = csrf
        body = content
        if json is not None:
            body = json_module.dumps(json).encode()
        if body is not None and content_type is not None:
            sent["content-type"] = content_type
        if send_cookies and self.cookies:
            sent["cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        sent.update({k.lower(): v for k, v in (headers or {}).items()})
        self.client.cookies.clear()
        # Corpo sempre come byte: httpx non aggiunge così alcun `Content-Type` per conto suo.
        response: Response = self.client.request(
            method, path, content=body, headers=sent, follow_redirects=False
        )
        self.client.cookies.clear()
        self.last_cookies = parse_set_cookies(response)
        for cookie in self.last_cookies:
            if cookie.deleted:
                self.cookies.pop(cookie.name, None)
            else:
                self.cookies[cookie.name] = cookie.value
        return response

    def get(self, path: str, **kw: Any) -> Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: Any = None, **kw: Any) -> Response:
        return self.request("POST", path, json={} if body is None else body, **kw)

    # -- sessione e CSRF ---------------------------------------------------------------------
    def session(self, **kw: Any) -> Response:
        return self.get("/api/v1/session", **kw)

    def anonymous_csrf(self) -> str:
        """Il cookie `__Host-csrf` arriva con `GET /session` (ADR-0004 rev. 3, punto 1)."""
        if CSRF not in self.cookies:
            assert self.session().status_code == 200
        return self.cookies[CSRF]

    def session_csrf(self) -> str:
        body = self.session().json()
        assert body["authenticated"] is True, body
        return str(body["csrfToken"])

    # -- il flusso di accesso -----------------------------------------------------------------
    def start_login(self, return_to: str | None = None, **kw: Any) -> Response:
        body: dict[str, Any] = {"purpose": "login"}
        if return_to is not None:
            body["returnTo"] = return_to
        csrf = kw.pop("csrf", None) or self.anonymous_csrf()
        return self.post("/api/v1/auth/google/start", body, csrf=csrf, **kw)

    def login(
        self,
        oidc: FakeOidc,
        identity: Identity,
        *,
        return_to: str | None = None,
        claims: dict[str, Any] | None = None,
        options: TokenOptions | None = None,
    ) -> Response:
        """Percorso completo: start, consenso al provider, callback. Restituisce il callback."""
        started = self.start_login(return_to)
        assert started.status_code == 200, started.text
        grant = oidc.authorize(
            started.json()["redirectUrl"], identity, claims=claims, options=options
        )
        return self.get(grant.callback_path)

    def logout(self, csrf: str | None = None) -> Response:
        return self.post("/api/v1/auth/logout", {}, csrf=csrf or self.session_csrf())


def location(response: Response) -> str:
    """`Location` di una risposta `302` (il callback risponde sempre così, plan §4.3)."""
    assert response.status_code == 302, (response.status_code, response.text)
    return response.headers["location"]
