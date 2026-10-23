"""Accesso con Google: avvio, callback, esiti, `returnTo` (SL-03a). Database e provider OIDC finto.

US-001: AC-001.1 (redirect e sessione; il piano della settimana arriva con SL-06a), AC-001.5
(login senza famiglia: messaggio, nessun dato, nessun account), AC-001.6 (consenso annullato).
SR-001 (Authorization Code + PKCE, scope minimi), SR-033 (`state`/`nonce` monouso, esito sul
server), SR-049 (nessun account persistente senza famiglia), SR-024/THR-010 (`returnTo` solo da
allow-list). THR-002, THR-005, THR-010. ADR-0004 rev. 2 punto 3 e rev. 3.

Contratto assunto (piano §4.3, ADR-0004 rev. 3), da confermare con il backend-developer:
- `GET /api/v1/session` anonimo risponde `200 {"authenticated": false, "notices": []}`, imposta
  `__Host-csrf` se manca e restituisce **una sola volta** `authOutcome: {code, params?}` letto
  dalla riga `auth_flow` del cookie `__Host-auth_flow`; poi cancella riga e cookie. L'esito
  compare anche nella forma anonima, perché un accesso non riuscito lascia anonimi.
- codici di esito: `not_member`, `auth_cancelled`, `auth_failed`.
- il callback risponde SEMPRE `302` verso `returnTo` o `/piano`, senza parametri nell'URL.
"""

import base64
import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from support.accounts import OUTSIDER, AlfaWorld, count
from support.auth_checks import assert_cookie, database_dump_text, hashes_of, leaks
from support.browser_sim import CALLBACK, FLOW, SESSION, Browser, location
from support.fake_oidc import FakeOidc
from support.owner import Owner

pytestmark = pytest.mark.integration

START = "/api/v1/auth/google/start"
FLOW_COLUMNS = (
    "handle_hash, purpose, session_id, return_to, state_hash, nonce_hash, code_verifier, "
    "created_at, expires_at"
)


def _flow_rows(owner: Owner) -> list[tuple[Any, ...]]:
    return owner.rows(f"select {FLOW_COLUMNS} from app.auth_flow")  # noqa: S608


# --- avvio del flusso ---------------------------------------------------------------------------


def test_ac_001_1_start_returns_the_google_redirect_with_pkce_state_and_nonce(
    browser: Browser, oidc: FakeOidc
) -> None:
    """SR-001: Authorization Code + PKCE S256, solo gli scope `openid email profile`."""
    started = browser.start_login()
    assert started.status_code == 200, started.text
    assert set(started.json()) == {"redirectUrl"}
    grant = oidc.authorize(started.json()["redirectUrl"], OUTSIDER)  # controlla client e URI
    params = grant.params
    assert params["response_type"] == "code"
    assert set(params["scope"].split()) == {"openid", "email", "profile"}
    assert params["code_challenge_method"] == "S256"
    assert params["prompt"] == "select_account", "AC-001.5: 'Usa un altro account Google'"
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", params["code_challenge"])
    assert len(params["state"]) >= 22, "state di almeno 128 bit"
    assert len(params["nonce"]) >= 22, "nonce di almeno 128 bit"
    assert params["state"] != params["nonce"]


def test_two_starts_never_share_state_nonce_challenge_or_flow_cookie(
    browser: Browser, oidc: FakeOidc, other_browser: Browser
) -> None:
    seen: list[tuple[str, ...]] = []
    for b in (browser, other_browser, browser):
        started = b.start_login()
        params = oidc.authorize(started.json()["redirectUrl"], OUTSIDER).params
        seen.append((params["state"], params["nonce"], params["code_challenge"], b.cookies[FLOW]))
    for position in range(4):
        values = [row[position] for row in seen]
        assert len(set(values)) == 3, f"valore ripetuto tra due avvii (colonna {position})"


def test_start_sets_a_host_prefixed_http_only_flow_cookie(browser: Browser) -> None:
    """ADR-0004: `__Host-auth_flow`, `SameSite=Lax` (deve arrivare dal ritorno di Google)."""
    browser.start_login()
    flow = [c for c in browser.last_cookies if c.name == FLOW]
    assert len(flow) == 1
    assert_cookie(flow[0], http_only=True, same_site="Lax", max_age_at_most=600)
    assert len(flow[0].value) >= 22


def test_start_persists_only_hashes_of_the_secrets_and_a_ten_minute_flow(
    browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    """05-data §4.1 `auth_flow`: hash di cookie, state e nonce; il verifier PKCE sì (va a."""
    started = browser.start_login("/piatti")
    params = oidc.authorize(started.json()["redirectUrl"], OUTSIDER).params
    (row,) = _flow_rows(owner)
    (
        handle_hash,
        purpose,
        session_id,
        return_to,
        state_hash,
        nonce_hash,
        verifier,
        created,
        expires,
    ) = row
    assert purpose == "login"
    assert session_id is None
    assert return_to == "/piatti"
    assert bytes(handle_hash) in hashes_of(browser.cookies[FLOW])
    assert bytes(state_hash) in hashes_of(params["state"])
    assert bytes(nonce_hash) in hashes_of(params["nonce"])
    assert 43 <= len(verifier) <= 128
    # PKCE: la sfida inviata a Google è l'hash S256 del verifier custodito dal server.
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge.decode() == params["code_challenge"]
    assert timedelta(0) < expires - created <= timedelta(minutes=10)
    assert abs(created - datetime.now(UTC)) < timedelta(minutes=5)
    dump = database_dump_text(owner)
    for secret in (params["state"], params["nonce"], browser.cookies[FLOW]):
        assert not leaks(dump, secret), "segreto del flusso in chiaro nel database"


def test_the_flow_never_carries_the_client_secret_to_the_browser(
    browser: Browser, oidc: FakeOidc
) -> None:
    started = browser.start_login()
    assert oidc.client_secret not in started.text
    assert oidc.client_secret not in started.headers.get("set-cookie", "")


# --- returnTo (THR-010) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "return_to", ["/piano", "/piano?settimana=2026-10-19", "/piatti", "/piatti?q=zuppa", "/altro"]
)
def test_allowed_return_paths_are_honoured_after_login(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, return_to: str
) -> None:
    response = browser.login(oidc, alfa.admin, return_to=return_to)
    assert location(response) == return_to


@pytest.mark.parametrize(
    "return_to",
    [
        "https://evil.example/piano",
        "http://evil.example",
        "//evil.example/piano",
        "/\\evil.example",
        "\\\\evil.example",
        "javascript:alert(1)",
        "data:text/html,x",
        "piano",
        "",
        "/",
        "/accedi",
        "/api/v1/auth/logout",
        "/piano#frammento",
        "/piano\r\nSet-Cookie: x=y",
        "/piano%0d%0aX: y",
        "/unknown",
        "/..//evil.example",
        "/piano@evil.example",
    ],
)
def test_ac_disallowed_return_paths_fall_back_to_the_plan(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner, return_to: str
) -> None:
    """THR-010, ADR-0004 rev. 2 punto 3: percorsi relativi di un'allow-list, altrimenti `/piano`.

    L'avvio non fallisce (nessun `422`: non si rivela quale valore è sbagliato) e il valore
    scartato non si conserva nel database.
    """
    started = browser.start_login(return_to)
    assert started.status_code == 200, started.text
    stored = [r[0] for r in owner.rows("select return_to from app.auth_flow")]
    assert stored in ([None], ["/piano"]), f"return_to non ammesso conservato: {stored}"
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    response = browser.get(grant.callback_path)
    assert location(response) == "/piano"
    assert "evil" not in response.headers["location"]


@pytest.mark.parametrize("return_to", ["/piano?q=" + "a" * 300, "/piatti/" + "a" * 5000])
def test_an_oversized_return_path_never_lands_anywhere_but_the_plan(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner, return_to: str
) -> None:
    """Oltre i 200 caratteri di `auth_flow.return_to`: o si scarta il valore (ritorno a `/piano`)
    o si rifiuta l'avvio con `422 string_too_long`; mai un `500` né un valore troncato."""
    started = browser.start_login(return_to)
    if started.status_code == 422:
        assert started.json()["code"] == "validation"
        assert "string_too_long" in {e["code"] for e in started.json()["errors"]}
        assert count(owner, "auth_flow") == 0
        return
    assert started.status_code == 200, started.text
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    assert location(browser.get(grant.callback_path)) == "/piano"


def test_a_start_without_return_to_lands_on_the_plan(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    assert location(browser.login(oidc, alfa.admin)) == "/piano"


# --- callback riuscito ------------------------------------------------------------------------


def test_ac_001_1_callback_logs_in_a_family_member_and_redirects_without_parameters(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    response = browser.login(oidc, alfa.admin)
    assert response.status_code == 302
    assert response.headers["location"] == "/piano", "nessun parametro d'esito nell'URL"
    names = {c.name: c for c in browser.last_cookies}
    assert SESSION in names
    assert not names[SESSION].deleted
    assert FLOW in names, "il cookie del flusso viene toccato al callback"
    assert names[FLOW].deleted, "il cookie del flusso si cancella al callback"
    assert count(owner, "session") == 1
    view = browser.session()
    body = view.json()
    assert view.status_code == 200
    assert body["authenticated"] is True
    assert body["account"]["displayName"] == "Alice Alfa"
    assert body["family"]["name"] == "Famiglia Alfa"
    assert body["person"] == {"id": str(alfa.admin_person), "role": "admin"}
    assert isinstance(body["csrfToken"], str)
    assert len(body["csrfToken"]) >= 22
    assert body["notices"] == []
    assert "authOutcome" not in body, "un accesso riuscito non ha esito (ADR-0004 rev. 3)"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", body["family"]["today"])
    assert view.headers["cache-control"] == "no-store", "risposta autenticata (piano §4.1)"
    assert response.headers["cache-control"] == "no-store", "il 302 che porta la sessione"


def test_a_member_logs_in_with_the_member_role(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    browser.login(oidc, alfa.member)
    body = browser.session().json()
    assert body["person"]["role"] == "member"
    assert body["account"]["displayName"] == "Mario Membro"


def test_session_view_never_exposes_email_sub_or_other_accounts(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    """THR-028, SR-014: la sessione porta nome e ruolo, non email né identificativo del provider."""
    browser.login(oidc, alfa.admin)
    text = browser.session().text
    for secret in (alfa.admin.email, alfa.admin.sub, alfa.member.email, alfa.member.sub):
        assert secret not in text
    assert "Mario Membro" not in text, "nessun dato di altri account nella sessione"


def test_the_callback_exchanges_the_code_server_side_with_pkce_and_the_client_secret(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    """THR-001/THR-015: il token arriva solo dal token endpoint; il secret non lascia il server."""
    browser.login(oidc, alfa.admin)
    posts = [e for e in oidc.exchanges if e.path.endswith("/token")]
    assert len(posts) == 1
    form = posts[0].form
    assert form["grant_type"] == "authorization_code"
    assert form["redirect_uri"] == oidc.redirect_uri
    assert re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", form["code_verifier"])
    secret_in_form = form.get("client_secret") == oidc.client_secret
    assert secret_in_form or (posts[0].authorization or "").lower().startswith("basic ")
    assert [e for e in oidc.exchanges if e.path.endswith("/jwks")], "chiavi lette da jwks_uri"


# --- AC-001.5: nessuna famiglia ---------------------------------------------------------------


def test_ac_001_5_login_without_a_family_shows_not_member_and_persists_nothing(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """SR-049: nessun account, sessione o persona; solo lo stato temporaneo del flusso."""
    accounts_before = count(owner, "account")
    response = browser.login(oidc, alfa.outsider)
    assert response.status_code == 302
    assert response.headers["location"] == "/piano"
    assert SESSION not in browser.cookies
    assert count(owner, "account") == accounts_before, "nessun account persistente (SR-049)"
    assert count(owner, "session") == 0
    assert count(owner, "person") == 2, "nessuna persona creata (solo Alice e Mario di Alfa)"
    assert (
        owner.scalar(
            "select count(*) from app.account where auth_subject = %s", (alfa.outsider.sub,)
        )
        == 0
    )

    first = browser.session()
    body = first.json()
    assert body["authenticated"] is False
    assert body["authOutcome"]["code"] == "not_member"
    assert set(body["authOutcome"]) <= {"code", "params"}
    assert body["notices"] == []
    for secret in (alfa.outsider.email, alfa.outsider.sub, "Famiglia Alfa", "Alice"):
        assert secret not in first.text, "l'esito non rivela né l'identità né altre famiglie"


def test_the_outcome_is_read_once_and_the_flow_state_is_deleted(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """ADR-0004 rev. 3 punto 3: `authOutcome` una sola volta; riga e cookie cancellati."""
    browser.login(oidc, alfa.outsider)
    first = browser.session()
    assert first.json()["authOutcome"]["code"] == "not_member"
    deleted = [c for c in browser.last_cookies if c.name == FLOW]
    assert deleted, "il cookie del flusso viene toccato alla lettura"
    assert deleted[0].deleted, "cookie del flusso cancellato alla lettura"
    assert count(owner, "auth_flow") == 0, "stato temporaneo cancellato (SR-049: entro 24 ore)"
    second = browser.session().json()
    assert "authOutcome" not in second
    assert second["authenticated"] is False


def test_the_outcome_needs_the_flow_cookie_of_the_same_browser(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    """Chi non ha il cookie del flusso non legge l'esito di un altro (nessuna informazione)."""
    browser.login(oidc, alfa.outsider)
    stranger = other_browser.session()
    assert "authOutcome" not in stranger.json()
    assert browser.session().json()["authOutcome"]["code"] == "not_member"


# --- AC-001.6: consenso annullato -------------------------------------------------------------


def test_ac_001_6_cancelled_consent_returns_a_generic_outcome_and_stays_anonymous(
    browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    started = browser.start_login()
    denied = oidc.deny(started.json()["redirectUrl"])
    response = browser.get(denied.callback_path)
    assert response.status_code == 302
    assert response.headers["location"] == "/piano"
    assert SESSION not in browser.cookies
    body = browser.session().json()
    assert body["authenticated"] is False
    assert body["authOutcome"]["code"] == "auth_cancelled"
    assert count(owner, "account") == 0
    assert count(owner, "session") == 0
    assert oidc.calls("/token") == 0, "nessun codice da scambiare"


# --- il callback non fallisce mai con un errore HTTP ------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?code=abc",
        "?state=abc",
        "?code=abc&state=abc",
        "?error=access_denied",
        "?error=access_denied&state=abc",
        "?error=server_error&error_description=x",
        "?code=" + "a" * 5000 + "&state=" + "b" * 5000,
        "?code=a&code=b&state=c&state=d",
        "?id_token=eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0.",
    ],
)
def test_callback_always_answers_302_without_a_session_when_the_flow_is_missing(
    browser: Browser, owner: Owner, query: str
) -> None:
    """Piano §4.3: sempre `302`; senza cookie e riga del flusso non nasce nessuna sessione."""
    response = browser.get(CALLBACK + query)
    assert response.status_code == 302, response.text
    assert response.headers["location"].startswith("/")
    assert SESSION not in browser.cookies
    assert count(owner, "session") == 0
    assert count(owner, "account") == 0


def test_callback_with_a_garbage_flow_cookie_is_a_plain_redirect(
    browser: Browser, owner: Owner
) -> None:
    browser.cookies[FLOW] = "x" * 43
    response = browser.get(CALLBACK + "?code=abc&state=abc")
    assert response.status_code == 302
    assert SESSION not in browser.cookies
    assert count(owner, "session") == 0


def test_an_expired_flow_is_rejected(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """Il flusso vale 10 minuti (05-data §4.1): oltre, il callback non apre sessioni."""
    started = browser.start_login()
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    owner.execute(
        "update app.auth_flow set created_at = created_at - interval '11 minutes', "
        "expires_at = expires_at - interval '11 minutes'"
    )
    response = browser.get(grant.callback_path)
    assert response.status_code == 302
    assert SESSION not in browser.cookies
    assert count(owner, "session") == 0


def test_a_successful_callback_consumes_the_flow_so_replay_gets_nothing(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """Monouso (SR-033, THR-002): lo stesso ritorno ripetuto non apre un'altra sessione."""
    started = browser.start_login()
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    first_cookie = browser.cookies[FLOW]
    assert browser.get(grant.callback_path).status_code == 302
    assert count(owner, "session") == 1
    browser.cookies[FLOW] = first_cookie  # il browser ripete il ritorno con lo stesso cookie
    replay = browser.get(grant.callback_path)
    assert replay.status_code == 302
    assert count(owner, "session") == 1, "nessuna seconda sessione dal ritorno ripetuto"
    assert oidc.calls("/token") == 1, "il codice non si scambia due volte"


def test_the_callback_rejects_other_methods(browser: Browser) -> None:
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        response = browser.request(method, CALLBACK, json={}, csrf=browser.anonymous_csrf())
        assert response.status_code in (404, 405), (method, response.status_code)
