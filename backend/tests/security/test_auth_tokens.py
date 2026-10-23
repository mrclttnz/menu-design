"""Token ID manipolati, `state` e flusso: il callback non si lascia ingannare (SL-03a).

SR-033: «firma RS256 con le chiavi di Google, `iss`, `aud`, `exp`, `nonce`, `state`,
`email_verified=true`; l'account è la coppia (provider, `sub`)». AC-001.7 (`email_verified=false`,
`aud` o `nonce` non validi: login rifiutato). THR-001 (un test per claim: altra chiave, `alg=none`,
`alg=HS256` con la chiave pubblica come segreto, `iss`, `aud`, `exp`, `nonce` ripetuto o assente,
`email_verified=false`, `kid` sconosciuto con refresh del JWKS una sola volta), THR-002 (login CSRF:
`state` di un altro flusso o cookie mancante), THR-003, ADR-0004 (RS256 fisso, JWKS in cache,
refresh su `kid` sconosciuto, token solo dal token endpoint).

Ogni caso usa un'identità che AVREBBE successo se il token fosse valido (un bootstrap in attesa
della sua email): il rifiuto è quindi dovuto al token, non all'assenza di famiglia. L'esito per
la SPA è `auth_failed`, il callback risponde comunque `302`, nessuna sessione, nessun account.
"""

import time
from collections.abc import Callable
from typing import Any

import pytest

from support.accounts import count, make_bootstrap, make_family, security_events
from support.browser_sim import CALLBACK, FLOW, SESSION, Browser
from support.fake_oidc import OMIT, FakeOidc, Identity, TokenOptions, get_key
from support.owner import Owner

pytestmark = [pytest.mark.sec, pytest.mark.integration]

EMAIL = "gestore.canary@example.test"
TARGET = Identity(sub="sub-gestore", email=EMAIL, name="Gestore Gamma")

Claims = Callable[[FakeOidc], dict[str, Any]]


def _past() -> int:
    return int(time.time()) - 3600


CLAIM_CASES: dict[str, Claims] = {
    "aud-di-un-altro-client": lambda o: {"aud": "altro-client.apps.example.test"},
    "aud-assente": lambda o: {"aud": OMIT},
    "aud-elenco-senza-il-nostro-client": lambda o: {"aud": ["a.example.test", "b.example.test"]},
    "azp-di-un-altro-client": lambda o: {"azp": "altro-client.apps.example.test"},
    "iss-di-un-altro-emittente": lambda o: {"iss": "https://evil.example"},
    "iss-con-barra-finale": lambda o: {"iss": o.issuer + "/"},
    "iss-google-dichiarato-da-uno-stub": lambda o: {"iss": "https://accounts.google.com"},
    "iss-assente": lambda o: {"iss": OMIT},
    "exp-scaduto": lambda o: {"exp": _past()},
    "exp-assente": lambda o: {"exp": OMIT},
    "nonce-di-un-altro-flusso": lambda o: {"nonce": "nonce-di-un-altro-flusso-0123456789"},
    "nonce-assente": lambda o: {"nonce": OMIT},
    "nonce-vuoto": lambda o: {"nonce": ""},
    "email_verified-false": lambda o: {"email_verified": False},
    "email_verified-stringa-true": lambda o: {"email_verified": "true"},
    "email_verified-assente": lambda o: {"email_verified": OMIT},
    "email_verified-null": lambda o: {"email_verified": None},
    "sub-assente": lambda o: {"sub": OMIT},
    "sub-vuoto": lambda o: {"sub": ""},
    "sub-numerico": lambda o: {"sub": 1234567890},
    "email-assente": lambda o: {"email": OMIT},
    "email-vuota": lambda o: {"email": ""},
}

OPTION_CASES: dict[str, Callable[[], TokenOptions]] = {
    "firmato-con-un-altra-chiave-stesso-kid": lambda: TokenOptions(
        key="other", kid=get_key("primary").kid
    ),
    "firmato-con-un-altra-chiave-altro-kid": lambda: TokenOptions(key="other"),
    "alg-none": lambda: TokenOptions(alg="none"),
    "alg-HS256-con-la-chiave-pubblica-come-segreto": lambda: TokenOptions(alg="HS256"),
    "alg-RS384-firmato-bene": lambda: TokenOptions(alg="RS384"),
    "kid-sconosciuto": lambda: TokenOptions(kid="chiave-mai-pubblicata"),
    "kid-sconosciuto-e-chiave-non-pubblicata": lambda: TokenOptions(key="rotated"),
    "payload-modificato-dopo-la-firma": lambda: TokenOptions(
        edit_payload_after_signing={"email": EMAIL, "sub": "sub-vittima"}
    ),
}


@pytest.fixture
def pending(owner: Owner) -> None:
    """Un bootstrap in attesa per l'email dell'identità sotto prova."""
    make_bootstrap(owner, make_family(owner, "Famiglia Gamma"), EMAIL)


def _assert_refused(browser: Browser, owner: Owner, response: Any) -> None:
    assert response.status_code == 302, "il callback risponde sempre 302 (nessun 4xx/5xx)"
    assert response.headers["location"] == "/piano"
    assert SESSION not in browser.cookies, "nessuna sessione"
    assert count(owner, "session") == 0
    assert count(owner, "account") == 0
    assert count(owner, "person") == 0
    assert owner.scalar("select count(*) from app.family_bootstrap where redeemed_at is null") == 1
    body = browser.session().json()
    assert body["authenticated"] is False
    assert body["authOutcome"]["code"] == "auth_failed", body


@pytest.mark.parametrize("case", sorted(CLAIM_CASES))
def test_ac_001_7_and_thr_001_a_manipulated_claim_is_rejected(
    browser: Browser, oidc: FakeOidc, owner: Owner, pending: None, case: str
) -> None:
    """Un test per claim: il token resta firmato bene, cambia una sola claim."""
    response = browser.login(oidc, TARGET, claims=CLAIM_CASES[case](oidc))
    _assert_refused(browser, owner, response)


@pytest.mark.parametrize("case", sorted(OPTION_CASES))
def test_thr_001_a_forged_or_unsupported_signature_is_rejected(
    browser: Browser, oidc: FakeOidc, owner: Owner, pending: None, case: str
) -> None:
    response = browser.login(oidc, TARGET, options=OPTION_CASES[case]())
    _assert_refused(browser, owner, response)


def test_the_unmanipulated_token_of_the_same_identity_is_accepted(
    browser: Browser, oidc: FakeOidc, owner: Owner, pending: None
) -> None:
    """Controllo dei controlli: gli stessi dati con un token valido entrano. Senza questo, i test
    qui sopra potrebbero passare per qualunque altro motivo."""
    assert browser.login(oidc, TARGET).status_code == 302
    assert browser.session().json()["person"]["role"] == "admin"
    assert count(owner, "session") == 1


def test_a_token_valid_for_two_more_minutes_is_accepted(
    browser: Browser, oidc: FakeOidc, owner: Owner, pending: None
) -> None:
    browser.login(oidc, TARGET, claims={"exp": int(time.time()) + 120})
    assert browser.session().json()["authenticated"] is True


# --- chiavi: cache e refresh del JWKS (THR-001) -----------------------------------------------


def test_the_jwks_is_cached_across_logins(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, owner: Owner, alfa: Any
) -> None:
    browser.login(oidc, alfa.admin)
    other_browser.login(oidc, alfa.member)
    assert oidc.calls("/jwks") == 1, "le chiavi di Google non si rileggono a ogni accesso"


def test_an_unknown_kid_refreshes_the_jwks_a_bounded_number_of_times(
    browser: Browser, oidc: FakeOidc, owner: Owner, alfa: Any, pending: None
) -> None:
    """«Refresh del JWKS su `kid` sconosciuto, limitato nel tempo»: un aggressore che invia token
    con `kid` casuali non trasforma l'app in un generatore di richieste verso Google."""
    browser.login(oidc, alfa.admin)  # riempie la cache
    assert oidc.calls("/jwks") == 1
    for attempt in range(6):
        attacker = Browser(browser.client)
        attacker.login(oidc, TARGET, options=TokenOptions(kid=f"kid-casuale-{attempt}"))
        assert SESSION not in attacker.cookies
    assert oidc.calls("/jwks") <= 2, "al più un refresh in questa finestra di tempo"


def test_a_rotated_key_is_picked_up_with_one_refresh(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, alfa: Any, pending: None
) -> None:
    browser.login(oidc, alfa.admin)
    assert oidc.calls("/jwks") == 1
    oidc.published.append("rotated")
    other_browser.login(oidc, TARGET, options=TokenOptions(key="rotated"))
    assert other_browser.session().json()["authenticated"] is True
    assert oidc.calls("/jwks") == 2


# --- il token arriva solo dal token endpoint (THR-001) ----------------------------------------


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"error": "invalid_grant"}),
        (401, {"error": "invalid_client"}),
        (500, {"error": "server_error"}),
        (503, "<html>Service Unavailable</html>"),
        (200, "non è json"),
        (200, {"access_token": "x", "token_type": "Bearer"}),
        (200, {"id_token": 12345, "token_type": "Bearer"}),
        (200, {"id_token": "", "token_type": "Bearer"}),
        (200, {"id_token": "a.b", "token_type": "Bearer"}),
        (200, {"id_token": "not-a-jwt", "token_type": "Bearer"}),
    ],
)
def test_token_endpoint_failures_and_malformed_responses_end_in_a_refused_login(
    browser: Browser, oidc: FakeOidc, owner: Owner, pending: None, status: int, body: Any
) -> None:
    oidc.token_override = (status, body)
    response = browser.login(oidc, TARGET)
    _assert_refused(browser, owner, response)


def test_a_token_end_point_that_returns_no_id_token_is_refused(
    browser: Browser, oidc: FakeOidc, owner: Owner, pending: None
) -> None:
    oidc.omit_id_token = True
    _assert_refused(browser, owner, browser.login(oidc, TARGET))


def test_an_id_token_in_the_browser_request_is_never_trusted(
    browser: Browser, oidc: FakeOidc, owner: Owner, pending: None
) -> None:
    """Niente flusso implicito: anche un token ben firmato nei parametri del callback è ignorato."""
    started = browser.start_login()
    grant = oidc.authorize(started.json()["redirectUrl"], TARGET)
    now = int(time.time())
    forged = oidc.encode(
        {
            "iss": oidc.issuer,
            "aud": oidc.client_id,
            "azp": oidc.client_id,
            "sub": TARGET.sub,
            "email": EMAIL,
            "email_verified": True,
            "nonce": grant.params["nonce"],
            "iat": now,
            "exp": now + 3600,
        }
    )
    response = browser.get(f"{CALLBACK}?state={grant.state}&id_token={forged}&access_token=x")
    assert response.status_code == 302
    assert SESSION not in browser.cookies
    assert count(owner, "session") == 0
    assert count(owner, "account") == 0


def test_a_manipulated_login_is_logged_as_a_failure_without_personal_data(
    browser: Browser, oidc: FakeOidc, owner: Owner, pending: None
) -> None:
    """SR-020: login falliti nel registro, con esito `failure`; mai email, `sub` o token."""
    browser.login(oidc, TARGET, claims={"email_verified": False})
    events = security_events(owner, "auth.login")
    assert len(events) == 1
    event = events[0]
    assert event["outcome"] == "failure"
    assert event["actor_kind"] == "anonymous"
    assert event["actor_account_id"] is None
    blob = str(event).lower()
    assert EMAIL not in blob
    assert TARGET.sub not in blob
    assert "gestore gamma" not in blob


# --- THR-002: login CSRF e iniezione del codice -----------------------------------------------


def test_thr_002_a_code_and_state_from_the_attackers_flow_do_not_log_the_victim_in(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, owner: Owner, alfa: Any
) -> None:
    """L'aggressore avvia il flusso nel PROPRIO browser, dà il consenso e fa aprire il suo
    callback alla vittima. La vittima non ha il suo cookie di flusso: nessuna sessione, e il
    codice non viene nemmeno scambiato."""
    started = other_browser.start_login()
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    victim = browser
    response = victim.get(grant.callback_path)
    assert response.status_code == 302
    assert SESSION not in victim.cookies
    assert count(owner, "session") == 0
    assert oidc.calls("/token") == 0, "senza cookie e riga corrispondenti il codice non si scambia"


def test_thr_002_a_state_from_another_flow_is_refused_even_with_the_victims_own_cookie(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, owner: Owner, alfa: Any
) -> None:
    attacker_start = other_browser.start_login()
    attacker_grant = oidc.authorize(attacker_start.json()["redirectUrl"], alfa.admin)
    browser.start_login()  # la vittima ha un flusso proprio in corso
    assert FLOW in browser.cookies
    response = browser.get(attacker_grant.callback_path)
    assert response.status_code == 302
    assert SESSION not in browser.cookies
    assert count(owner, "session") == 0
    assert oidc.calls("/token") == 0


def test_thr_002_the_attackers_callback_still_works_in_the_attackers_own_browser(
    other_browser: Browser, oidc: FakeOidc, owner: Owner, alfa: Any
) -> None:
    """Controllo dei controlli: stesso codice e stato, ma nel browser che ha il cookie giusto."""
    started = other_browser.start_login()
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    assert other_browser.get(grant.callback_path).status_code == 302
    assert other_browser.session().json()["authenticated"] is True


@pytest.mark.parametrize(
    "mutation", ["senza-state", "state-vuoto", "state-alterato", "state-doppio"]
)
def test_thr_002_a_missing_or_altered_state_is_refused_before_the_code_exchange(
    browser: Browser, oidc: FakeOidc, owner: Owner, alfa: Any, mutation: str
) -> None:
    started = browser.start_login()
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    state = grant.state
    query = {
        "senza-state": f"code={grant.code}",
        "state-vuoto": f"code={grant.code}&state=",
        "state-alterato": f"code={grant.code}&state={state[:-1]}{'A' if state[-1] != 'A' else 'B'}",
        "state-doppio": f"code={grant.code}&state={state}&state=altro",
    }[mutation]
    response = browser.get(f"{CALLBACK}?{query}")
    assert response.status_code == 302
    assert SESSION not in browser.cookies
    assert count(owner, "session") == 0
    assert oidc.calls("/token") == 0


def test_thr_002_a_flow_cookie_value_not_matching_any_row_is_refused(
    browser: Browser, oidc: FakeOidc, owner: Owner, alfa: Any
) -> None:
    started = browser.start_login()
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    browser.cookies[FLOW] = "A" * len(browser.cookies[FLOW])
    assert browser.get(grant.callback_path).status_code == 302
    assert SESSION not in browser.cookies
    assert count(owner, "session") == 0
    assert oidc.calls("/token") == 0
