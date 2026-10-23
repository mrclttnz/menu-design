"""Sicurezza dei limiti di frequenza (SL-03b): IP, chiavi HMAC, fail closed, 429 generici.

THR-012 (X-Forwarded-For falsificato), THR-011 (avvii massivi), THR-103 (il limiter fallisce
chiuso), THR-013. SR-059, SR-004 (nessuna informazione sull'identità limitata), SR-051 e ADR-0006
(chiavi = HMAC-SHA-256 con pepper: nessun IP, email, sessione o account in chiaro nel database).
SEC-SL00a-005: `TRUSTED_PROXY_HOPS` non ha più un valore predefinito.
"""

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from menu.identity.tokens import csrf_token_for
from support.accounts import AlfaWorld, count, security_events
from support.auth_checks import hashes_of, leaks
from support.browser_sim import SESSION, Browser
from support.fake_oidc import FakeOidc
from support.owner import Owner
from support.ratelimit import (
    IP_OTHER,
    IP_REAL,
    PEPPER_A,
    PEPPER_B,
    PROBE_PREFIX,
    counter_keys,
    counter_writes_denied,
    rate_counter_text,
)

pytestmark = [pytest.mark.sec, pytest.mark.integration]

Factory = Callable[..., TestClient]
T0 = datetime(2026, 10, 23, 12, 7, 30, tzinfo=UTC)
LIMIT = 30


@pytest.fixture
def clock(frozen_now: Callable[[datetime], None]) -> None:
    frozen_now(T0)


def _xff(forged: str, real: str = IP_REAL) -> dict[str, str]:
    return {"x-forwarded-for": f"{forged}, {real}"}


# --- THR-012: l'IP è l'ULTIMA voce, mai quelle scelte dal client ---------------------------------


def test_thr_012_a_forged_x_forwarded_for_does_not_evade_the_per_ip_limit(
    app_factory: Factory, clock: None
) -> None:
    """Un bot che cambia la voce di sinistra a ogni richiesta resta un solo IP."""
    browser = Browser(app_factory(hops="1"))
    for number in range(LIMIT):
        response = browser.start_login(headers=_xff(f"192.0.2.{number + 1}"))
        assert response.status_code == 200, number
    limited = browser.start_login(headers=_xff("192.0.2.200"))
    assert limited.status_code == 429


def test_thr_012_the_limit_is_per_ip_another_real_ip_is_not_limited(
    app_factory: Factory, clock: None
) -> None:
    browser = Browser(app_factory(hops="1"))
    for _ in range(LIMIT):
        assert browser.start_login(headers=_xff("192.0.2.1")).status_code == 200
    assert browser.start_login(headers=_xff("192.0.2.1")).status_code == 429
    # Stessa voce di sinistra, altro IP reale: non è bloccato (altrimenti il limite sarebbe globale,
    # SEC-SL00a-005).
    assert browser.start_login(headers=_xff("192.0.2.1", IP_OTHER)).status_code == 200
    assert browser.start_login(headers={"x-forwarded-for": IP_OTHER}).status_code == 200


def test_thr_012_with_zero_hops_the_header_is_ignored_entirely(
    app_factory: Factory, clock: None
) -> None:
    """Senza proxy fidato l'header non vale nulla: cento IP dichiarati contano come uno solo."""
    browser = Browser(app_factory(hops="0"))
    for number in range(LIMIT):
        assert (
            browser.start_login(headers={"x-forwarded-for": f"192.0.2.{number}"}).status_code == 200
        )
    assert browser.start_login(headers={"x-forwarded-for": "192.0.2.250"}).status_code == 429


def test_thr_012_an_invalid_last_entry_is_never_trusted_as_a_fresh_identity(
    app_factory: Factory, clock: None
) -> None:
    """Voce non valida (testo qualunque): le richieste non diventano 'tutte diverse'."""
    browser = Browser(app_factory(hops="1"))
    statuses = [
        browser.start_login(headers={"x-forwarded-for": f"x{n}-<script>"}).status_code
        for n in range(LIMIT + 1)
    ]
    assert statuses[:LIMIT] == [200] * LIMIT
    assert statuses[LIMIT] == 429


def test_the_429_event_records_the_real_ip_not_the_forged_one(
    app_factory: Factory, clock: None, owner: Owner
) -> None:
    browser = Browser(app_factory(hops="1"))
    for _ in range(LIMIT):
        browser.start_login(headers=_xff("192.0.2.66"))
    assert browser.start_login(headers=_xff("192.0.2.66")).status_code == 429
    ips = owner.rows(
        "select host(ip) from app.security_event where event_type = 'rate_limit.exceeded'"
    )
    assert ips
    assert {r[0] for r in ips} == {IP_REAL}


# --- SEC-SL00a-005: nessun valore predefinito per TRUSTED_PROXY_HOPS ----------------------------


def test_startup_is_refused_when_trusted_proxy_hops_is_not_set(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from menu.app import create_app

    monkeypatch.delenv("TRUSTED_PROXY_HOPS")
    with pytest.raises(Exception, match=r"(?i)trusted_proxy_hops"), TestClient(create_app()):
        pass


# --- ADR-0006: chiavi HMAC con pepper, nessun identificativo in chiaro ---------------------------


def test_keys_are_peppered_hmacs_never_raw_identifiers(
    app_factory: Factory, clock: None, owner: Owner
) -> None:
    browser = Browser(app_factory(hops="1"))
    browser.start_login(headers=_xff("192.0.2.1"))
    keys = counter_keys(owner)
    assert keys
    assert all(len(k) == 32 for k in keys), "HMAC-SHA-256 = 32 byte"
    dump = rate_counter_text(owner)
    for ip in (IP_REAL, "192.0.2.1", "203.0.113", "192.0.2"):
        assert not leaks(dump, ip), f"IP in chiaro nel database: {ip}"
    unkeyed = hashes_of(IP_REAL) | {hashlib.sha256(IP_REAL.encode() + b"|").digest()}
    assert not keys & unkeyed, "la chiave non è un hash senza pepper dell'IP"
    assert not keys & {hashlib.sha256(PEPPER_A.encode() + IP_REAL.encode()).digest()}
    assert not keys & {hmac.new(PEPPER_A.encode(), IP_REAL.encode(), "sha256").digest()}, (
        "serve anche il nome della regola: lo stesso IP in due regole non condivide la chiave"
    )


def test_the_key_depends_on_the_pepper_and_is_stable_across_restarts(
    app_factory: Factory, clock: None, owner: Owner
) -> None:
    def one_start_keys(pepper: str) -> set[bytes]:
        owner.execute("truncate app.rate_counter")
        Browser(app_factory(hops="1", pepper=pepper)).start_login(headers=_xff("192.0.2.1"))
        return counter_keys(owner)

    first = one_start_keys(PEPPER_A)
    assert first
    assert one_start_keys(PEPPER_A) == first, "stesso pepper: i contatori sopravvivono al riavvio"
    assert not one_start_keys(PEPPER_B) & first, (
        "un altro pepper dà altre chiavi (staging ≠ produzione)"
    )


def test_session_account_and_family_identifiers_are_not_stored_in_clear_in_counters(
    app_factory: Factory,
    clock: None,
    oidc: FakeOidc,
    alfa: AlfaWorld,
    owner: Owner,
) -> None:
    browser = Browser(app_factory())
    assert browser.login(oidc, alfa.admin).status_code == 302
    token = browser.cookies[SESSION]
    csrf = csrf_token_for(token)
    assert browser.get(f"{PROBE_PREFIX}/read").status_code == 200
    assert browser.post(f"{PROBE_PREFIX}/write", csrf=csrf).status_code == 200
    session_id = owner.scalar("select id from app.session")
    dump = rate_counter_text(owner)
    secrets: list[Any] = [token, csrf, str(session_id), str(alfa.admin_account), str(alfa.family)]
    secrets += [alfa.admin.email, "alfa.admin"]
    for secret in secrets:
        assert not leaks(dump, str(secret)), f"dato in chiaro in rate_counter: {secret!r}"
    for raw in (UUID(str(session_id)).bytes, alfa.admin_account.bytes, alfa.family.bytes):
        assert raw.hex() not in dump
    assert len(counter_keys(owner)) >= 2, "almeno una chiave per la sessione e una per l'account"


# --- 429 generico (SR-004) -----------------------------------------------------------------------


def test_the_429_body_and_headers_reveal_nothing_about_who_is_limited(
    app_factory: Factory, clock: None
) -> None:
    browser = Browser(app_factory(hops="1"))
    for _ in range(LIMIT):
        browser.start_login(headers=_xff("192.0.2.1"))
    limited = browser.start_login(headers=_xff("192.0.2.1"))
    assert limited.status_code == 429
    text = limited.text + str(dict(limited.headers))
    for needle in (IP_REAL, "192.0.2.1", "rate_counter", "google", PEPPER_A):
        assert needle not in text, needle
    assert limited.headers["cache-control"] == "no-store"
    assert limited.headers["x-content-type-options"] == "nosniff"


# --- THR-103: fail closed ----------------------------------------------------------------------


def test_thr_103_when_counters_cannot_be_written_the_request_is_denied_with_503(
    app_factory: Factory, clock: None, owner: Owner
) -> None:
    browser = Browser(app_factory())
    csrf = browser.anonymous_csrf()
    with counter_writes_denied(owner):
        response = browser.post("/api/v1/auth/google/start", {"purpose": "login"}, csrf=csrf)
    assert response.status_code == 503, response.text
    assert "redirectUrl" not in response.text
    assert "__Host-auth_flow" not in " ".join(response.headers.get_list("set-cookie"))
    assert count(owner, "auth_flow") == 0, "la richiesta negata non ha effetti"
    for needle in ("rate_counter", "permission", "psycopg", "sqlalchemy", "menu_app", "denied for"):
        assert needle not in response.text.lower()
    # Tornato il database, il servizio riparte senza intervento.
    assert (
        browser.post("/api/v1/auth/google/start", {"purpose": "login"}, csrf=csrf).status_code
        == 200
    )


def test_thr_103_an_authenticated_write_is_not_executed_when_counters_fail(
    app_factory: Factory,
    clock: None,
    oidc: FakeOidc,
    alfa: AlfaWorld,
    owner: Owner,
    rl_calls: list[str],
) -> None:
    browser = Browser(app_factory())
    assert browser.login(oidc, alfa.admin).status_code == 302
    csrf = csrf_token_for(browser.cookies[SESSION])
    with counter_writes_denied(owner):
        write = browser.post(f"{PROBE_PREFIX}/write", csrf=csrf)
        read = browser.get(f"{PROBE_PREFIX}/read")
    assert write.status_code == 503
    assert read.status_code == 503
    assert rl_calls == [], "nessun handler eseguito con il limiter in errore"
    assert browser.get(f"{PROBE_PREFIX}/read").status_code == 200


def test_thr_103_a_failing_limiter_is_logged_without_leaking_connection_details(
    app_factory: Factory, clock: None, owner: Owner, capsys: pytest.CaptureFixture[str]
) -> None:
    browser = Browser(app_factory())
    csrf = browser.anonymous_csrf()
    with counter_writes_denied(owner):
        browser.post("/api/v1/auth/google/start", {"purpose": "login"}, csrf=csrf)
    out = capsys.readouterr()
    logged = out.out + out.err
    assert "DATABASE_URL" not in logged
    assert "sslmode" not in logged
    assert PEPPER_A not in logged


def test_the_pepper_never_appears_in_responses_or_logs(
    app_factory: Factory, clock: None, capsys: pytest.CaptureFixture[str]
) -> None:
    browser = Browser(app_factory())
    response = browser.start_login()
    out = capsys.readouterr()
    assert PEPPER_A not in response.text + str(dict(response.headers)) + out.out + out.err


def test_security_events_of_a_429_reach_the_log_without_the_full_ip(
    app_factory: Factory, clock: None, owner: Owner, capsys: pytest.CaptureFixture[str]
) -> None:
    """SR-051: il log strutturato porta il prefisso, il registro l'IP completo per 90 giorni."""
    browser = Browser(app_factory(hops="1"))
    for _ in range(LIMIT + 1):
        browser.start_login(headers=_xff("192.0.2.1"))
    out = capsys.readouterr()
    lines = [line for line in (out.out + out.err).splitlines() if "rate_limit.exceeded" in line]
    assert lines, "nessuna riga di log per rate_limit.exceeded"
    assert all(IP_REAL not in line for line in lines)
    assert security_events(owner, "rate_limit.%")


# --- SEC-SL03b-001: IPv6 per /64, IPv4-mappato come IPv4 ------------------------------------------


def test_sec_sl03b_001_addresses_in_one_ipv6_64_share_the_per_ip_limit(
    app_factory: Factory, clock: None
) -> None:
    browser = Browser(app_factory(hops="1"))
    codes = [
        browser.start_login(headers={"x-forwarded-for": f"2001:db8:1:2::{n:x}"}).status_code
        for n in range(1, 41)
    ]
    assert codes == [200] * LIMIT + [429] * 10


def test_sec_sl03b_001_different_ipv6_64_prefixes_are_independent(
    app_factory: Factory, clock: None
) -> None:
    browser = Browser(app_factory(hops="1"))
    for n in range(LIMIT):
        assert browser.start_login(headers={"x-forwarded-for": f"2001:db8:1:2::{n + 1:x}"})
    assert browser.start_login(headers={"x-forwarded-for": "2001:db8:1:2::ffff"}).status_code == 429
    assert browser.start_login(headers={"x-forwarded-for": "2001:db8:1:3::1"}).status_code == 200


def test_sec_sl03b_001_an_ipv4_mapped_address_counts_as_the_ipv4(
    app_factory: Factory, clock: None
) -> None:
    browser = Browser(app_factory(hops="1"))
    for _ in range(LIMIT):
        assert browser.start_login(headers={"x-forwarded-for": IP_REAL}).status_code == 200
    mapped = {"x-forwarded-for": f"::ffff:{IP_REAL}"}
    assert browser.start_login(headers=mapped).status_code == 429


def test_sec_sl03b_001_the_event_keeps_the_real_ipv6_address(
    app_factory: Factory, clock: None, owner: Owner
) -> None:
    browser = Browser(app_factory(hops="1"))
    real = "2001:db8:1:2::7"
    for _ in range(LIMIT):
        browser.start_login(headers={"x-forwarded-for": real})
    assert browser.start_login(headers={"x-forwarded-for": real}).status_code == 429
    ip = owner.scalar(
        "select host(ip) from app.security_event where event_type = 'rate_limit.exceeded' "
        "order by id limit 1"
    )
    assert ip == real


# --- SEC-SL03b-002: il logout non conta nelle scritture ---------------------------------------


def test_sec_sl03b_002_logout_still_works_after_60_writes_in_the_minute(
    app_factory: Factory, clock: None, oidc: FakeOidc, alfa: AlfaWorld
) -> None:
    browser = Browser(app_factory())
    assert browser.login(oidc, alfa.admin).status_code == 302
    csrf = csrf_token_for(browser.cookies[SESSION])
    for _ in range(60):
        assert browser.post(f"{PROBE_PREFIX}/write", csrf=csrf).status_code == 200
    assert browser.post(f"{PROBE_PREFIX}/write", csrf=csrf).status_code == 429
    assert browser.logout(csrf).status_code == 204
