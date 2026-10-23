"""CSRF, origine e tipo del contenuto su avvio del login e logout (SL-03a).

SR-023 (protezione CSRF sulle richieste che modificano dati), THR-007 (token per sessione
nell'header `X-CSRF-Token` confrontato con `hmac.compare_digest`; `Origin` o `Sec-Fetch-Site:
same-origin` su OGNI metodo non sicuro, anche anonimo; `Content-Type: application/json`
obbligatorio; nessun `GET` con effetti, logout compreso; per i `POST` anonimi doppio invio del
cookie `__Host-csrf`). 08 §7.2. ADR-0004 rev. 2 punto 4. Piano §4.1: `403 csrf_failed`, `415`.

Ogni rifiuto non lascia effetti: nessuna riga `auth_flow`, nessun cookie di flusso, la sessione
resta com'era.
"""

from pathlib import Path
from typing import Any

import pytest
from httpx import Response

from support.accounts import AlfaWorld, count
from support.browser_sim import CSRF, FLOW, SESSION, Browser
from support.fake_oidc import FakeOidc
from support.owner import Owner
from support.paths import SRC

pytestmark = [pytest.mark.sec, pytest.mark.integration]

START = "/api/v1/auth/google/start"
LOGOUT = "/api/v1/auth/logout"
BODY = {"purpose": "login"}
FOREIGN_ORIGINS = [
    "https://evil.example",
    "http://testserver",
    "https://testserver.evil.example",
    "https://evil.testserver",
    "https://testserver:8443",
    "null",
    "",
]


def _is_csrf_failure(response: Response) -> None:
    assert response.status_code == 403, (response.status_code, response.text)
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "csrf_failed"


def _no_start_effects(browser: Browser, owner: Owner, oidc: FakeOidc) -> None:
    assert count(owner, "auth_flow") == 0, "un rifiuto non crea stato di flusso"
    assert FLOW not in browser.cookies
    assert oidc.exchanges == []


# --- avvio anonimo: doppio invio del cookie ---------------------------------------------------


def test_start_works_with_a_matching_cookie_and_header_and_a_same_origin_post(
    browser: Browser,
) -> None:
    csrf = browser.anonymous_csrf()
    response = browser.post(START, BODY, csrf=csrf)
    assert response.status_code == 200
    assert response.json()["redirectUrl"].startswith("http")
    assert FLOW in browser.cookies


def test_start_accepts_a_json_content_type_with_a_charset(browser: Browser) -> None:
    csrf = browser.anonymous_csrf()
    response = browser.post(START, BODY, csrf=csrf, content_type="application/json; charset=utf-8")
    assert response.status_code == 200


@pytest.mark.parametrize(
    "header",
    [None, "", "x", "token-sbagliato-ma-lungo-quanto-uno-vero-0123456789", "null", "undefined"],
    ids=["senza-header", "vuoto", "corto", "lungo-sbagliato", "null", "undefined"],
)
def test_start_without_a_matching_csrf_header_is_403(
    browser: Browser, owner: Owner, oidc: FakeOidc, header: str | None
) -> None:
    browser.anonymous_csrf()
    _is_csrf_failure(browser.post(START, BODY, csrf=header))
    _no_start_effects(browser, owner, oidc)


def test_start_with_the_header_but_without_the_cookie_is_403(
    browser: Browser, owner: Owner, oidc: FakeOidc
) -> None:
    """Il header da solo non basta: serve il doppio invio (un sito terzo non può leggere il."""
    csrf = browser.anonymous_csrf()
    browser.cookies.pop(CSRF)
    _is_csrf_failure(browser.post(START, BODY, csrf=csrf))
    _no_start_effects(browser, owner, oidc)


def test_start_with_the_cookie_of_another_browser_is_403(
    browser: Browser, other_browser: Browser, owner: Owner, oidc: FakeOidc
) -> None:
    """Un token valido ma di un altro browser, nel header, non coincide con il cookie di questo."""
    stolen = other_browser.anonymous_csrf()
    browser.anonymous_csrf()
    _is_csrf_failure(browser.post(START, BODY, csrf=stolen))
    _no_start_effects(browser, owner, oidc)


@pytest.mark.parametrize("origin", FOREIGN_ORIGINS)
def test_start_from_a_foreign_origin_is_403_even_with_a_valid_token(
    browser: Browser, owner: Owner, oidc: FakeOidc, origin: str
) -> None:
    csrf = browser.anonymous_csrf()
    _is_csrf_failure(browser.post(START, BODY, csrf=csrf, origin=origin))
    _no_start_effects(browser, owner, oidc)


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
@pytest.mark.parametrize("origin", ["https://testserver", None], ids=["origin-ok", "senza-origin"])
def test_start_with_a_non_same_origin_fetch_metadata_is_403(
    browser: Browser, owner: Owner, oidc: FakeOidc, site: str, origin: str | None
) -> None:
    csrf = browser.anonymous_csrf()
    _is_csrf_failure(browser.post(START, BODY, csrf=csrf, origin=origin, sec_fetch_site=site))
    _no_start_effects(browser, owner, oidc)


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/plain;charset=UTF-8",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/xml",
        "application/jsonp",
        "text/json",
    ],
)
def test_start_with_a_non_json_content_type_is_415(
    browser: Browser, owner: Owner, oidc: FakeOidc, content_type: str
) -> None:
    """Un `<form>` cross-site non può inviare `application/json` senza preflight: lo si rifiuta."""
    csrf = browser.anonymous_csrf()
    response = browser.post(START, BODY, csrf=csrf, content_type=content_type)
    assert response.status_code == 415, response.text
    assert response.json()["code"] == "unsupported_media_type"
    _no_start_effects(browser, owner, oidc)


def test_start_without_a_content_type_is_415(
    browser: Browser, owner: Owner, oidc: FakeOidc
) -> None:
    csrf = browser.anonymous_csrf()
    response = browser.post(START, BODY, csrf=csrf, content_type=None)
    assert response.status_code == 415
    _no_start_effects(browser, owner, oidc)


@pytest.mark.parametrize(
    ("body", "field_code"),
    [
        ({}, "required"),
        ({"purpose": "login", "familyId": "x"}, "unknown_field"),
        ({"purpose": "login", "role": "admin"}, "unknown_field"),
        ({"purpose": "invite"}, "invalid_value"),
        ({"purpose": "LOGIN"}, "invalid_value"),
        ({"purpose": 1}, "invalid_value"),
        ({"purpose": "login", "returnTo": 123}, "invalid_value"),
    ],
)
def test_start_validates_its_body_with_closed_vocabularies(
    browser: Browser, owner: Owner, oidc: FakeOidc, body: dict[str, Any], field_code: str
) -> None:
    csrf = browser.anonymous_csrf()
    response = browser.post(START, body, csrf=csrf)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation"
    assert field_code in {e["code"] for e in response.json()["errors"]}
    _no_start_effects(browser, owner, oidc)


def test_start_refuses_an_oversized_body(browser: Browser, owner: Owner, oidc: FakeOidc) -> None:
    csrf = browser.anonymous_csrf()
    big = b'{"purpose":"login","returnTo":"/piano' + b"a" * 70_000 + b'"}'
    response = browser.request("POST", START, content=big, csrf=csrf)
    assert response.status_code == 413
    _no_start_effects(browser, owner, oidc)


def test_start_ignores_cors_preflight_from_foreign_origins(browser: Browser) -> None:
    """SR-023: nessun CORS; un'origine estranea non riceve `Access-Control-Allow-Origin`."""
    assert browser.start_login().status_code == 200, "la rotta esiste"
    response = browser.request(
        "OPTIONS",
        START,
        headers={
            "origin": "https://evil.example",
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type,x-csrf-token",
        },
    )
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


# --- logout: token legato alla sessione -------------------------------------------------------


@pytest.fixture
def logged(browser: Browser, oidc: FakeOidc, alfa: AlfaWorld) -> Browser:
    browser.login(oidc, alfa.admin)
    return browser


def _session_survives(browser: Browser, owner: Owner) -> None:
    assert count(owner, "session") >= 1
    assert browser.session().json()["authenticated"] is True


def test_logout_with_the_session_csrf_token_works(logged: Browser) -> None:
    assert logged.post(LOGOUT, {}, csrf=logged.session_csrf()).status_code == 204


@pytest.mark.parametrize(
    "header", [None, "", "x", "y" * 43], ids=["assente", "vuoto", "corto", "lungo"]
)
def test_logout_without_a_valid_session_token_is_403_and_keeps_the_session(
    logged: Browser, owner: Owner, header: str | None
) -> None:
    _is_csrf_failure(logged.post(LOGOUT, {}, csrf=header))
    _session_survives(logged, owner)


def test_logout_does_not_accept_the_anonymous_double_submit_value(
    logged: Browser, owner: Owner
) -> None:
    """Chi controlla un cookie (per esempio da un sottodominio) non deve poter disconnettere o
    agire su una sessione: il token di una sessione autenticata è quello legato alla sessione."""
    logged.session_csrf()
    _is_csrf_failure(logged.post(LOGOUT, {}, csrf=logged.cookies[CSRF]))
    _session_survives(logged, owner)


def test_logout_with_a_token_of_another_session_of_the_same_account_is_403(
    logged: Browser, other_browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    other_browser.login(oidc, alfa.admin)
    foreign = other_browser.session_csrf()
    _is_csrf_failure(logged.post(LOGOUT, {}, csrf=foreign))
    assert count(owner, "session") == 2


def test_logout_with_a_token_of_another_account_is_403(
    logged: Browser, other_browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    other_browser.login(oidc, alfa.member)
    foreign = other_browser.session_csrf()
    _is_csrf_failure(logged.post(LOGOUT, {}, csrf=foreign))
    assert count(owner, "session") == 2


@pytest.mark.parametrize("origin", FOREIGN_ORIGINS)
def test_logout_from_a_foreign_origin_is_403_even_with_the_right_token(
    logged: Browser, owner: Owner, origin: str
) -> None:
    csrf = logged.session_csrf()
    _is_csrf_failure(logged.post(LOGOUT, {}, csrf=csrf, origin=origin))
    _session_survives(logged, owner)


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_logout_with_a_non_same_origin_fetch_metadata_is_403(
    logged: Browser, owner: Owner, site: str
) -> None:
    csrf = logged.session_csrf()
    _is_csrf_failure(logged.post(LOGOUT, {}, csrf=csrf, origin=None, sec_fetch_site=site))
    _session_survives(logged, owner)


@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"],
)
def test_logout_with_a_non_json_content_type_is_415(
    logged: Browser, owner: Owner, content_type: str
) -> None:
    csrf = logged.session_csrf()
    response = logged.post(LOGOUT, {}, csrf=csrf, content_type=content_type)
    assert response.status_code == 415
    _session_survives(logged, owner)


def test_logout_refuses_unknown_body_fields_and_keeps_the_session(
    logged: Browser, owner: Owner
) -> None:
    csrf = logged.session_csrf()
    response = logged.post(LOGOUT, {"everywhere": True}, csrf=csrf)
    assert response.status_code == 422
    assert "unknown_field" in {e["code"] for e in response.json()["errors"]}
    _session_survives(logged, owner)


# --- nessun GET con effetti (THR-007) ---------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_logout_is_never_reachable_with_a_safe_method(
    logged: Browser, owner: Owner, method: str
) -> None:
    response = logged.request(method, LOGOUT)
    assert response.status_code in (404, 405), response.status_code
    _session_survives(logged, owner)


def test_start_is_not_reachable_with_get(browser: Browser, owner: Owner) -> None:
    response = browser.get(START)
    assert response.status_code in (404, 405)
    assert count(owner, "auth_flow") == 0


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_the_session_resource_only_answers_get(browser: Browser, method: str) -> None:
    csrf = browser.anonymous_csrf()
    response = browser.request(method, "/api/v1/session", json={}, csrf=csrf)
    assert response.status_code in (404, 405)


def test_get_session_has_no_side_effect_beyond_the_csrf_cookie(
    logged: Browser, owner: Owner, alfa: AlfaWorld
) -> None:
    before = {t: count(owner, t) for t in ("account", "session", "person", "auth_flow", "family")}
    for _ in range(3):
        logged.session()
    after = {t: count(owner, t) for t in before}
    assert before == after


def test_a_cookie_other_than_the_session_never_authenticates(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    """Il token di sessione viaggia solo nel cookie `__Host-session`: né header né query."""
    browser.login(oidc, alfa.admin)
    token = browser.cookies[SESSION]
    thief = Browser(browser.client)
    for headers in (
        {"authorization": f"Bearer {token}"},
        {"x-session": token},
        {"cookie": f"session={token}"},
        {"cookie": f"__Secure-session={token}"},
    ):
        assert thief.get("/api/v1/session", headers=headers).json()["authenticated"] is False
    assert (
        thief.get(f"/api/v1/session?session={token}&token={token}").json()["authenticated"] is False
    )


# --- confronto in tempo costante (THR-007) ----------------------------------------------------


def test_identity_compares_csrf_tokens_with_compare_digest() -> None:
    """Rete statica: il confronto dei token è con `hmac.compare_digest` e non con `==`."""
    code = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted((SRC / "identity").rglob("*.py"))
    )
    assert "compare_digest" in code, "THR-007: confronto del token CSRF in tempo costante"


def test_identity_generates_tokens_with_the_secrets_module() -> None:
    """SR-037: CSPRNG. Nessun `random` nel modulo; il token viene da `secrets`."""
    files = sorted((SRC / "identity").rglob("*.py"))
    code = "\n".join(p.read_text(encoding="utf-8") for p in files)
    assert "secrets." in code or "from secrets" in code
    assert not [p for p in files if _imports_random(p)], "il modulo `random` non è un CSPRNG"


def _imports_random(path: Path) -> bool:
    import ast

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import) and any(a.name == "random" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "random":
            return True
    return False
