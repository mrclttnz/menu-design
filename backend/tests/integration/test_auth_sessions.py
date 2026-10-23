"""Sessioni opache lato server (SL-03a): cookie, hash, scadenze, logout, fixation, appartenenza.

US-001: AC-001.2 (riapro l'app, sono ancora autenticato), AC-001.3 (30 giorni di inattività oppure
90 dal login: devo autenticarmi di nuovo), AC-001.4 (logout: sessione invalidata sul server e
vecchio cookie rifiutato). SR-005 (cookie `__Host-`, HttpOnly, Secure, SameSite=Lax; rigenerata al
login; appartenenza riletta a ogni richiesta), SR-037 (≥ 128 bit da CSPRNG, solo hash sul server,
Path=/, scadenza mobile 30 giorni e assoluta 90). THR-005 (furto), THR-006 (fixation). ADR-0004:
`last_used_at` si aggiorna al massimo una volta all'ora.

Le scadenze si provano spostando i DATI con l'helper `owner` (08 §4.4), con un margine di un giorno.
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI

from menu.identity import SessionInfo, session_guard
from support.accounts import AlfaWorld, age_session, count, security_events, sessions
from support.auth_checks import assert_cookie, database_dump_text, hashes_of, leaks
from support.browser_sim import CSRF, FLOW, SESSION, UA_PHONE, Browser
from support.fake_oidc import FakeOidc
from support.owner import Owner

pytestmark = pytest.mark.integration

THIRTY_DAYS = 30 * 24 * 3600


def _login(browser: Browser, oidc: FakeOidc, identity: object, owner: Owner, account: UUID) -> UUID:
    response = browser.login(oidc, identity)  # type: ignore[arg-type]
    assert response.status_code == 302
    assert SESSION in browser.cookies
    rows = sessions(owner, account)
    return rows[-1][0]  # type: ignore[no-any-return]


# --- cookie e token (SR-005, SR-037, THR-005) -------------------------------------------------


def test_session_cookie_attributes(browser: Browser, oidc: FakeOidc, alfa: AlfaWorld) -> None:
    browser.login(oidc, alfa.admin)
    cookie = next(c for c in browser.last_cookies if c.name == SESSION)
    assert_cookie(cookie, http_only=True, same_site="Lax", max_age=THIRTY_DAYS)
    assert len(cookie.value) >= 43, "almeno 256 bit in base64url (≥ 128 bit richiesti da SR-037)"


def test_the_anonymous_csrf_cookie_is_readable_by_the_spa_and_strict(browser: Browser) -> None:
    """ADR-0004 rev. 3 punto 1: `__Host-csrf`, SameSite=Strict, Secure, Path=/, NON HttpOnly."""
    response = browser.session()
    assert response.status_code == 200
    cookie = next(c for c in browser.last_cookies if c.name == CSRF)
    assert_cookie(cookie, http_only=False, same_site="Strict")
    assert len(cookie.value) >= 22, "token casuale di almeno 128 bit"
    first = cookie.value
    browser.session()
    assert not [c for c in browser.last_cookies if c.name == CSRF], "impostato solo se manca"
    assert browser.cookies[CSRF] == first


def test_the_anonymous_session_view_has_the_contract_shape(browser: Browser) -> None:
    response = browser.session()
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "notices": []}


def test_only_a_hash_of_the_session_token_is_stored_and_no_secret_leaks_into_the_database(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """SR-037, THR-005: il database non contiene il token né il token CSRF in nessuna forma."""
    browser.login(oidc, alfa.admin)
    token = browser.cookies[SESSION]
    csrf_token = browser.session_csrf()
    ((_, _, token_hash, csrf_hash, *_),) = sessions(owner, alfa.admin_account)
    assert len(bytes(token_hash)) == 32
    assert len(bytes(csrf_hash)) == 32
    assert bytes(token_hash) in hashes_of(token), "token_hash = SHA-256 del token"
    assert bytes(csrf_hash) != bytes(token_hash)
    dump = database_dump_text(owner)
    for secret in (token, csrf_token, browser.cookies[CSRF]):
        assert not leaks(dump, secret), "segreto di sessione in chiaro nel database"
    assert csrf_token != token
    assert csrf_token != browser.cookies[CSRF]


def test_session_tokens_and_csrf_tokens_are_never_reused(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    browser.login(oidc, alfa.admin)
    other_browser.login(oidc, alfa.admin)
    assert browser.cookies[SESSION] != other_browser.cookies[SESSION]
    first = browser.session_csrf()
    assert browser.session_csrf() == first, "il token CSRF di una sessione è stabile"
    assert other_browser.session_csrf() != first, "un altro dispositivo ha un altro token"
    assert count(owner, "session") == 2


def test_the_device_label_is_derived_and_the_full_user_agent_is_not_kept(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """05-data §4.1: «lo user agent completo non si conserva» (SR-014, SR-051)."""
    browser.login(oidc, alfa.admin)
    ((*_, label, _),) = sessions(owner, alfa.admin_account)
    assert label is None or len(label) <= 80
    assert label != UA_PHONE
    assert "AppleWebKit" not in (label or "")
    assert "AppleWebKit" not in database_dump_text(owner)


def test_the_auth_time_is_recorded_for_the_session(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    browser.login(oidc, alfa.admin)
    ((_, _, _, _, created, used, auth_time, *_),) = sessions(owner, alfa.admin_account)
    assert abs(auth_time - datetime.now(UTC)) < timedelta(minutes=5)
    assert abs(created - datetime.now(UTC)) < timedelta(minutes=5)
    assert used >= created


# --- scadenze (AC-001.2, AC-001.3) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("created_days", "used_days", "alive"),
    [
        (2, 0.01, True),
        (60, 29, True),  # AC-001.2: usata da meno di 30 giorni
        (89, 1, True),  # login da meno di 90 giorni
        (60, 31, False),  # AC-001.3: 31 giorni di inattività
        (95, 31, False),
        (91, 0.001, False),  # AC-001.3: login a 91 giorni fa, anche se la uso ogni giorno
        (120, 1, False),
    ],
)
def test_ac_001_2_and_001_3_the_sliding_30_day_and_absolute_90_day_limits(
    browser: Browser,
    oidc: FakeOidc,
    alfa: AlfaWorld,
    owner: Owner,
    created_days: float,
    used_days: float,
    alive: bool,
) -> None:
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    age_session(owner, session, created_days=created_days, used_days=used_days)
    body = browser.session().json()
    assert body["authenticated"] is alive
    if not alive:
        refused = browser.post("/api/v1/auth/logout", {}, csrf=browser.anonymous_csrf())
        assert refused.status_code == 401, "la sessione scaduta non vale per nessuna rotta"
        assert refused.json()["code"] == "unauthenticated"


def test_ac_001_2_using_the_session_renews_the_sliding_window_at_most_hourly(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """ADR-0004: `last_used_at` aggiornato al massimo una volta all'ora."""
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    age_session(owner, session, created_days=40, used_days=29)  # inattiva da 29 giorni
    assert browser.session().json()["authenticated"] is True
    used = owner.scalar("select last_used_at from app.session where id = %s", (session,))
    assert abs(used - datetime.now(UTC)) < timedelta(minutes=5), "finestra mobile rinnovata"

    recent = datetime.now(UTC) - timedelta(minutes=10)
    owner.execute("update app.session set last_used_at = %s where id = %s", (recent, session))
    for _ in range(3):
        assert browser.session().json()["authenticated"] is True
    assert (
        owner.scalar("select last_used_at from app.session where id = %s", (session,)) == recent
    ), "entro l'ora non si riscrive"

    old = datetime.now(UTC) - timedelta(minutes=90)
    owner.execute("update app.session set last_used_at = %s where id = %s", (old, session))
    browser.session()
    assert owner.scalar("select last_used_at from app.session where id = %s", (session,)) > old


def test_renewal_does_not_extend_the_absolute_90_day_limit(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    age_session(owner, session, created_days=89, used_days=2)
    assert browser.session().json()["authenticated"] is True
    created = owner.scalar("select created_at from app.session where id = %s", (session,))
    assert datetime.now(UTC) - created > timedelta(days=88), "created_at non si sposta mai"


def _session_cookies(browser: Browser) -> list[str]:
    return [c.attrs.get("max-age", "") for c in browser.last_cookies if c.name == SESSION]


def _stale(owner: Owner, session: UUID, *, created_days: float) -> None:
    age_session(owner, session, created_days=created_days, used_days=2)


def test_ac_001_2_get_session_reissues_the_cookie_when_the_window_is_renewed(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    token = browser.cookies[SESSION]
    _stale(owner, session, created_days=10)
    assert browser.session().json()["authenticated"] is True
    cookie = next(c for c in browser.last_cookies if c.name == SESSION)
    assert cookie.value == token
    assert cookie.attrs["max-age"] == str(THIRTY_DAYS)
    assert cookie.flag("secure")
    assert cookie.flag("httponly")
    assert cookie.attrs["samesite"].lower() == "lax"
    assert cookie.attrs["path"] == "/"
    assert "domain" not in cookie.attrs
    browser.session()  # entro l'ora: nessuna rinnovo, nessun cookie
    assert _session_cookies(browser) == []


def test_ac_001_2_the_renewed_cookie_never_outlives_the_absolute_90_day_limit(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    _stale(owner, session, created_days=89)
    assert browser.session().json()["authenticated"] is True
    (max_age,) = _session_cookies(browser)
    assert 80_000 < int(max_age) <= 86_400, "al più il giorno che resta dei 90"


def _guarded_probe(browser: Browser) -> None:
    app = browser.client.app
    assert isinstance(app, FastAPI)

    def probe(_: Annotated[SessionInfo, Depends(session_guard)]) -> dict[str, bool]:
        return {"ok": True}

    app.add_api_route("/api/v1/_probe/guarded", probe, methods=["POST"])


def test_ac_001_2_session_guard_renews_the_cookie_for_every_guarded_route(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    token = browser.cookies[SESSION]
    csrf = browser.session_csrf()
    _guarded_probe(browser)
    _stale(owner, session, created_days=10)
    assert browser.post("/api/v1/_probe/guarded", {}, csrf=csrf).status_code == 200
    cookie = next(c for c in browser.last_cookies if c.name == SESSION)
    assert (cookie.value, cookie.attrs["max-age"]) == (token, str(THIRTY_DAYS))
    assert cookie.flag("httponly")
    assert cookie.flag("secure")

    browser.post("/api/v1/_probe/guarded", {}, csrf=csrf)
    assert _session_cookies(browser) == [], "entro l'ora non si ripete"

    _stale(owner, session, created_days=89)
    browser.post("/api/v1/_probe/guarded", {}, csrf=csrf)
    (max_age,) = _session_cookies(browser)
    assert 80_000 < int(max_age) <= 86_400


def test_ac_001_2_a_guarded_request_keeps_the_get_session_cookie_in_step(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """CR-SL03a-002: la riga rinnovata da una rotta protetta non lascia il cookie indietro."""
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    csrf = browser.session_csrf()
    _guarded_probe(browser)
    _stale(owner, session, created_days=10)
    browser.post("/api/v1/_probe/guarded", {}, csrf=csrf)
    assert _session_cookies(browser) == [str(THIRTY_DAYS)]


def test_logout_ends_up_with_the_session_cookie_deleted_even_if_it_was_renewed(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    csrf = browser.session_csrf()
    _stale(owner, session, created_days=10)
    assert browser.post("/api/v1/auth/logout", {}, csrf=csrf).status_code == 204
    assert SESSION not in browser.cookies


@pytest.mark.parametrize("value", ["x", "x" * 43, "x" * 5000, "%00", "../etc", "a b", "0123456789"])
def test_a_garbage_session_cookie_is_an_anonymous_visit_not_an_error(
    browser: Browser, value: str
) -> None:
    browser.cookies[SESSION] = value
    response = browser.session()
    assert response.status_code == 200
    assert response.json()["authenticated"] is False


# --- AC-001.4: logout -------------------------------------------------------------------------


def test_ac_001_4_logout_invalidates_the_session_on_the_server(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    old_cookie = browser.cookies[SESSION]
    response = browser.logout()
    assert response.status_code == 204
    assert response.content == b""
    gone = [c for c in browser.last_cookies if c.name == SESSION]
    assert gone, "il cookie di sessione viene toccato"
    assert gone[0].deleted, "il cookie viene cancellato"
    assert gone[0].flag("secure"), "la cancellazione vale per __Host- solo con Secure"
    assert gone[0].attrs.get("path") == "/"
    assert owner.scalar("select count(*) from app.session where id = %s", (session,)) == 0

    # Un attaccante che aveva rubato il cookie non entra più (AC-001.4, THR-005).
    thief = Browser(browser.client, cookies={SESSION: old_cookie})
    assert thief.session().json()["authenticated"] is False
    csrf = thief.anonymous_csrf()
    refused = thief.post("/api/v1/auth/logout", {}, csrf=csrf)
    assert refused.status_code == 401
    assert refused.json()["code"] == "unauthenticated"


def test_logout_removes_only_the_current_session(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    first = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    second = _login(other_browser, oidc, alfa.admin, owner, alfa.admin_account)
    assert first != second
    assert browser.logout().status_code == 204
    left = {row[0] for row in sessions(owner, alfa.admin_account)}
    assert left == {second}
    assert other_browser.session().json()["authenticated"] is True


def test_logout_writes_a_security_event_without_personal_data(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    browser.login(oidc, alfa.admin)
    browser.logout()
    (event,) = security_events(owner, "auth.logout")
    assert event["outcome"] == "success"
    assert event["actor_account_id"] == alfa.admin_account
    assert event["family_id"] == alfa.family
    assert alfa.admin.email not in str(event)
    assert alfa.admin.sub not in str(event)


def test_logout_without_a_session_is_401_problem_json(browser: Browser) -> None:
    csrf = browser.anonymous_csrf()
    response = browser.post("/api/v1/auth/logout", {}, csrf=csrf)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "unauthenticated"
    assert response.json()["status"] == 401


def test_a_second_logout_with_the_same_cookie_is_401(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    browser.login(oidc, alfa.admin)
    csrf = browser.session_csrf()
    cookie = browser.cookies[SESSION]
    assert browser.post("/api/v1/auth/logout", {}, csrf=csrf).status_code == 204
    browser.cookies[SESSION] = cookie  # il browser riprova con il vecchio cookie
    assert browser.post("/api/v1/auth/logout", {}, csrf=csrf).status_code == 401


# --- fixation (THR-006, SR-005) ---------------------------------------------------------------


def test_thr_006_login_replaces_the_session_of_a_pre_existing_cookie(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """Il browser ha già la sessione di Alice e accede come Mario: la vecchia viene cancellata
    e il nuovo token è diverso."""
    alice_session = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    alice_token = browser.cookies[SESSION]
    browser.login(oidc, alfa.member)
    assert owner.scalar("select count(*) from app.session where id = %s", (alice_session,)) == 0
    assert browser.cookies[SESSION] != alice_token
    assert browser.session().json()["account"]["displayName"] == "Mario Membro"
    stale = Browser(browser.client, cookies={SESSION: alice_token})
    assert stale.session().json()["authenticated"] is False, "il vecchio cookie non vale più"
    assert count(owner, "session") == 1


def test_thr_006_relogin_of_the_same_account_issues_a_fresh_token(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    before = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    token = browser.cookies[SESSION]
    after = _login(browser, oidc, alfa.admin, owner, alfa.admin_account)
    assert after != before
    assert browser.cookies[SESSION] != token
    assert count(owner, "session") == 1, "la sessione precedente di quel browser è stata sostituita"


def test_thr_006_a_session_value_chosen_by_an_attacker_is_never_adopted(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    """Fixation classica: l'aggressore pianta un cookie noto, la vittima accede."""
    planted = "attacker-chosen-session-token-value-0123456789abcdef"
    browser.cookies[SESSION] = planted
    browser.login(oidc, alfa.admin)
    assert browser.cookies[SESSION] != planted
    attacker = Browser(browser.client, cookies={SESSION: planted})
    assert attacker.session().json()["authenticated"] is False


# --- l'appartenenza si rilegge a ogni richiesta (SR-005) --------------------------------------


def test_a_role_change_is_visible_on_the_next_request(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    browser.login(oidc, alfa.member)
    assert browser.session().json()["person"]["role"] == "member"
    owner.execute("update app.person set role = 'planner' where id = %s", (alfa.member_person,))
    assert browser.session().json()["person"]["role"] == "planner"


def test_a_removed_person_has_no_family_on_the_next_request(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """SR-005, 08 §7.1: persona rimossa → `family: null` in sessione (la sessione resta)."""
    browser.login(oidc, alfa.member)
    owner.execute("delete from app.person where id = %s", (alfa.member_person,))
    body = browser.session().json()
    assert body["authenticated"] is True
    assert body["family"] is None
    assert body["person"] is None
    assert "Famiglia Alfa" not in str(body)


def test_the_session_does_not_depend_on_the_flow_cookie(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    browser.login(oidc, alfa.admin)
    browser.cookies.pop(FLOW, None)
    assert browser.session().json()["authenticated"] is True
    assert re.fullmatch(r"[\w-]+", browser.cookies[SESSION])


# --- IP del client (SR-051, THR-012) ---------------------------------------------------------


@pytest.fixture
def proxied_browser(auth_env: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[Browser]:
    """App dietro un proxy fidato (`TRUSTED_PROXY_HOPS=1`): l'IP è l'ultima voce di XFF."""
    from fastapi.testclient import TestClient

    from menu.app import create_app

    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    with TestClient(
        create_app(), base_url="https://testserver", raise_server_exceptions=False
    ) as c:
        yield Browser(c)


def test_the_session_keeps_a_truncated_ip_and_the_event_the_real_one(
    proxied_browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """05-data §4.1: `session.ip_prefix` già troncato (/24); `security_event.ip` completo per 90
    giorni. L'IP è quello dell'ultima voce di `X-Forwarded-For` (aggiunta dal proxy fidato), mai
    quello scritto dal client (THR-012)."""
    started = proxied_browser.start_login(headers={"x-forwarded-for": "198.51.100.77, 203.0.113.9"})
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    proxied_browser.get(
        grant.callback_path, headers={"x-forwarded-for": "198.51.100.77, 203.0.113.9"}
    )
    ((*_, ip_prefix),) = sessions(owner, alfa.admin_account)
    assert str(ip_prefix) == "203.0.113.0/24"
    (event,) = owner.rows("select host(ip) from app.security_event where event_type = 'auth.login'")
    assert event == ("203.0.113.9",)
    assert "198.51.100" not in database_dump_text(owner), "la voce falsificata non si conserva"
