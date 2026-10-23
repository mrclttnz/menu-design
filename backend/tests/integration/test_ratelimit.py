"""Limiti di frequenza con contatori condivisi e persistenti (SL-03b; ADR-0006).

US-001: AC-001.9 (più di 30 avvii di accesso dallo stesso IP in 15 minuti: `429` con
`Retry-After`). SR-003 (limiti sul login), SR-059 (avvio OIDC 30/IP/15 min; API autenticata
300/min per sessione, di cui 60 scritture), SR-070 (60 scritture/min per account sommando le
sessioni). THR-011 (stati temporanei massivi), THR-013 (sessioni moltiplicate), THR-103 (il
limiter fallisce chiuso). 08 §7.4.

Tutte le finestre si provano con l'orologio del DATABASE fermo a metà finestra (`frozen_now`,
08 §4.4): nessun test dipende da quando gira, né può spezzarsi su un cambio di minuto.
Per ogni rotta soggetta a limite si prova la richiesta dentro il limite (passa), quella oltre
(429) e la ripartenza nella finestra successiva.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from menu.identity.tokens import csrf_token_for
from support.accounts import AlfaWorld, count, security_events
from support.browser_sim import SESSION, Browser
from support.fake_oidc import FakeOidc
from support.owner import Owner
from support.ratelimit import PROBE_PREFIX, counters

pytestmark = pytest.mark.integration

READ = f"{PROBE_PREFIX}/read"
WRITE = f"{PROBE_PREFIX}/write"
T0 = datetime(2026, 10, 23, 12, 7, 30, tzinfo=UTC)  # a metà di una finestra da 1 e da 15 minuti
START_LIMIT, API_LIMIT, WRITE_LIMIT = 30, 300, 60
START_WAIT = 450  # 12:07:30 -> fine della finestra da 15 minuti alle 12:15:00

Factory = Callable[..., TestClient]


@pytest.fixture
def clock(frozen_now: Callable[[datetime], None]) -> Callable[[datetime], None]:
    frozen_now(T0)
    return frozen_now


def _assert_rate_limited(response: Response, retry_after: int = 30) -> int:
    """Contratto del 429 (ADR-0006, SR-004): intestazione, corpo generico; ritorna i secondi.

    Con l'orologio a 12:07:30 mancano 30 s alla fine di una finestra da 1 minuto e 450 s a quella
    da 15 minuti (CR-SL03b-004)."""
    assert response.status_code == 429, (response.status_code, response.text)
    assert response.headers["content-type"].startswith("application/problem+json")
    retry = int(response.headers["retry-after"])
    assert retry == retry_after, "attesa esatta fino alla fine della finestra (orologio fermo)"
    body = response.json()
    assert body["code"] == "rate_limited"
    assert body["status"] == 429
    assert body["params"]["retryAfterSeconds"] == retry, "UX: error.rateLimited usa questo valore"
    assert set(body) <= {"type", "title", "status", "code", "params"}
    return retry


def _login(browser: Browser, oidc: FakeOidc, identity: Any) -> str:
    """Accede SENZA chiamare `GET /session` e restituisce il token CSRF della sessione.

    Se `GET /session` contasse o no nei 300/min non è fissato dal piano: i test non dipendono
    da questa scelta, quindi non lo chiamano prima di riempire i contatori.
    """
    assert browser.login(oidc, identity).status_code == 302
    assert SESSION in browser.cookies
    return csrf_token_for(browser.cookies[SESSION])


# --- avvio dell'accesso: 30 per IP in 15 minuti (AC-001.9, SR-059, THR-011) ----------------------


def test_ac_001_9_the_31st_login_start_from_one_ip_gets_429_with_retry_after(
    app_factory: Factory, clock: Callable[[datetime], None], owner: Owner
) -> None:
    browser = Browser(app_factory())
    for number in range(1, START_LIMIT + 1):
        response = browser.start_login()
        assert response.status_code == 200, (number, response.text)
        assert response.json()["redirectUrl"]
    flows_before = count(owner, "auth_flow")
    limited = browser.start_login()
    _assert_rate_limited(limited, START_WAIT)
    assert "__Host-auth_flow" not in " ".join(limited.headers.get_list("set-cookie"))
    assert "redirectUrl" not in limited.text
    assert count(owner, "auth_flow") == flows_before, "il 429 non crea nessun auth_flow (THR-011)"


def test_the_login_start_limit_restarts_in_the_next_window(
    app_factory: Factory, clock: Callable[[datetime], None]
) -> None:
    browser = Browser(app_factory())
    for _ in range(START_LIMIT):
        assert browser.start_login().status_code == 200
    _assert_rate_limited(browser.start_login(), START_WAIT)
    clock(T0 + timedelta(minutes=1))
    # ancora nella stessa finestra di 15 minuti
    _assert_rate_limited(browser.start_login(), START_WAIT - 60)
    clock(T0 + timedelta(minutes=31))
    assert browser.start_login().status_code == 200, "dopo la finestra si riparte"


def test_a_429_is_logged_as_rate_limit_exceeded_without_personal_data(
    app_factory: Factory, clock: Callable[[datetime], None], owner: Owner
) -> None:
    """SR-020, SR-058: evento `rate_limit.exceeded`, esito `denied`, nessuna email né token."""
    browser = Browser(app_factory(hops="1"))
    headers = {"x-forwarded-for": "192.0.2.77, 203.0.113.9"}
    for _ in range(START_LIMIT):
        assert browser.start_login(headers=headers).status_code == 200
    assert not security_events(owner, "rate_limit.%"), "nessun evento prima del superamento"
    _assert_rate_limited(browser.start_login(headers=headers), START_WAIT)
    (event, *_) = security_events(owner, "rate_limit.%")
    assert event["event_type"] == "rate_limit.exceeded"
    assert event["outcome"] == "denied"
    assert event["actor_kind"] == "anonymous"
    assert event["actor_account_id"] is None
    ip = owner.scalar(
        "select host(ip) from app.security_event where event_type = 'rate_limit.exceeded' "
        "order by id limit 1"
    )
    assert ip == "203.0.113.9", "IP reale = ultima voce di X-Forwarded-For (THR-012)"
    assert "@" not in (event["details"] or "")
    assert "192.0.2.77" not in json.dumps(event, default=str)


# --- API autenticata: 300/min per sessione, di cui 60 scritture (SR-059) -------------------------


def test_the_301st_authenticated_request_in_a_minute_gets_429(
    app_factory: Factory,
    clock: Callable[[datetime], None],
    oidc: FakeOidc,
    alfa: AlfaWorld,
    rl_calls: list[str],
) -> None:
    browser = Browser(app_factory())
    _login(browser, oidc, alfa.admin)
    ok = [browser.get(READ).status_code for _ in range(API_LIMIT)]
    assert ok == [200] * API_LIMIT
    _assert_rate_limited(browser.get(READ))
    assert rl_calls.count("read") == API_LIMIT, "la richiesta oltre il limite non esegue l'handler"
    clock(T0 + timedelta(minutes=3))
    assert browser.get(READ).status_code == 200, "ripartenza nella finestra successiva"


def test_the_61st_write_in_a_minute_gets_429_and_is_not_executed(
    app_factory: Factory,
    clock: Callable[[datetime], None],
    oidc: FakeOidc,
    alfa: AlfaWorld,
    rl_calls: list[str],
) -> None:
    browser = Browser(app_factory())
    csrf = _login(browser, oidc, alfa.admin)
    for number in range(1, WRITE_LIMIT + 1):
        response = browser.post(WRITE, csrf=csrf)
        assert response.status_code == 200, (number, response.text)
    _assert_rate_limited(browser.post(WRITE, csrf=csrf))
    assert rl_calls.count("write") == WRITE_LIMIT
    assert browser.get(READ).status_code == 200, (
        "le letture non sono bloccate dal limite delle scritture"
    )


def test_the_60_writes_are_part_of_the_300_requests(
    app_factory: Factory,
    clock: Callable[[datetime], None],
    oidc: FakeOidc,
    alfa: AlfaWorld,
) -> None:
    """SR-059: «300 richieste al minuto per sessione, di cui al massimo 60 scritture»."""
    browser = Browser(app_factory())
    csrf = _login(browser, oidc, alfa.admin)
    for _ in range(WRITE_LIMIT):
        assert browser.post(WRITE, csrf=csrf).status_code == 200
    for number in range(API_LIMIT - WRITE_LIMIT):
        assert browser.get(READ).status_code == 200, number
    _assert_rate_limited(browser.get(READ))


def test_another_session_has_its_own_request_counters(
    app_factory: Factory,
    clock: Callable[[datetime], None],
    oidc: FakeOidc,
    alfa: AlfaWorld,
) -> None:
    client = app_factory()
    first, second = Browser(client), Browser(client)
    _login(first, oidc, alfa.admin)
    _login(second, oidc, alfa.admin)
    for _ in range(API_LIMIT):
        assert first.get(READ).status_code == 200
    _assert_rate_limited(first.get(READ))
    assert second.get(READ).status_code == 200, "un altro dispositivo non è toccato"


def test_sr_070_writes_of_all_sessions_of_an_account_add_up_to_60_per_minute(
    app_factory: Factory,
    clock: Callable[[datetime], None],
    oidc: FakeOidc,
    alfa: AlfaWorld,
    rl_calls: list[str],
) -> None:
    client = app_factory()
    first, second, other_account = Browser(client), Browser(client), Browser(client)
    csrf_first = _login(first, oidc, alfa.admin)
    csrf_second = _login(second, oidc, alfa.admin)
    csrf_other = _login(other_account, oidc, alfa.member)
    for _ in range(30):
        assert first.post(WRITE, csrf=csrf_first).status_code == 200
        assert second.post(WRITE, csrf=csrf_second).status_code == 200
    # Nessuna delle due sessioni ha superato le sue 60, ma l'account sì (THR-013, THR-100).
    _assert_rate_limited(second.post(WRITE, csrf=csrf_second))
    _assert_rate_limited(first.post(WRITE, csrf=csrf_first))
    assert rl_calls.count("write") == 60
    # Un altro account non è toccato (i contatori sono per account).
    assert other_account.post(WRITE, csrf=csrf_other).status_code == 200


def test_an_authenticated_429_is_logged_with_the_account(
    app_factory: Factory,
    clock: Callable[[datetime], None],
    oidc: FakeOidc,
    alfa: AlfaWorld,
    owner: Owner,
) -> None:
    browser = Browser(app_factory())
    csrf = _login(browser, oidc, alfa.admin)
    for _ in range(WRITE_LIMIT):
        assert browser.post(WRITE, csrf=csrf).status_code == 200
    _assert_rate_limited(browser.post(WRITE, csrf=csrf))
    events = security_events(owner, "rate_limit.%")
    assert events, "nessun evento rate_limit.exceeded"
    assert {e["event_type"] for e in events} == {"rate_limit.exceeded"}
    assert events[0]["actor_kind"] == "account"
    assert events[0]["actor_account_id"] == alfa.admin_account
    assert events[0]["outcome"] == "denied"


# --- contatori condivisi e persistenti (ADR-0006, SR-059) ----------------------------------------


def test_counters_survive_a_restart_of_the_service(
    app_factory: Factory, clock: Callable[[datetime], None], owner: Owner
) -> None:
    """Riavvio simulato: nuova app sullo stesso database. Nessuno stato resta in memoria."""
    first = Browser(app_factory())
    for _ in range(20):
        assert first.start_login().status_code == 200
    stored = counters(owner)
    assert stored, "i contatori stanno in rate_counter, non in memoria"
    second = Browser(app_factory())  # chiude la prima app e ne avvia un'altra
    for number in range(21, START_LIMIT + 1):
        assert second.start_login().status_code == 200, number
    _assert_rate_limited(second.start_login(), START_WAIT)


def test_the_counter_is_persisted_in_a_single_row_per_rule_and_window(
    app_factory: Factory, clock: Callable[[datetime], None], owner: Owner
) -> None:
    browser = Browser(app_factory(hops="1"))
    headers = {"x-forwarded-for": "203.0.113.9"}
    for _ in range(5):
        browser.start_login(headers=headers)
    rows = counters(owner)
    assert rows
    assert max(c for _, _, c in rows) == 5
    assert len({(k, w) for k, w, _ in rows}) == len(rows), "chiave e finestra sono univoche"
    assert all(len(k) == 32 for k, _, _ in rows)


def test_healthz_is_neither_limited_nor_counted(
    app_factory: Factory, clock: Callable[[datetime], None], owner: Owner
) -> None:
    """THR-106: `/healthz` deve misurare il database, non dipendere dai contatori."""
    client = app_factory()
    statuses = {client.get("/healthz").status_code for _ in range(API_LIMIT + 20)}
    assert statuses == {200}
    assert counters(owner) == []
