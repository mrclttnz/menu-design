"""Account, bootstrap e identità (SL-03a): chi diventa chi al primo login e ai successivi.

US-001 AC-001.8 (stesso `sub`, email cambiata), US-002 AC-002.1 (il primo login con l'email del
bootstrap crea l'Amministratore, legato al `sub`), AC-002.4 (bootstrap scaduto: nessun
Amministratore, messaggio di AC-001.5). SR-033 (l'account è la coppia (provider, `sub`); il
bootstrap si lega all'email solo fino al primo login), SR-014 (minimizzazione), SR-049, SR-054
(il nome visualizzato poi lo cambia l'utente). THR-003 (email diversa per punto o `+`),
THR-028. ADR-0004 (bootstrap con `email_sha256`), ADR-0011.
"""

import os
import re
import subprocess
import sys
from typing import Any
from uuid import UUID

import pytest

from menu.common import email_sha256
from support import pg
from support.accounts import (
    AlfaWorld,
    count,
    make_bootstrap,
    make_family,
    make_member,
    security_events,
)
from support.auth_checks import database_dump_text
from support.browser_sim import SESSION, Browser
from support.fake_oidc import FakeOidc, Identity
from support.owner import Owner
from support.paths import BACKEND

pytestmark = pytest.mark.integration

GESTORE_EMAIL = "gestore.canary@example.test"
GESTORE = Identity(sub="sub-gestore", email=GESTORE_EMAIL, name="Gestore Gamma")


def _account(owner: Owner, sub: str) -> tuple[Any, ...]:
    rows = owner.rows(
        "select id, auth_provider, auth_subject, email, email_sha256, display_name, "
        "email_verified_at from app.account where auth_subject = %s",
        (sub,),
    )
    assert len(rows) == 1, f"attesa una riga per {sub}, trovate {len(rows)}"
    return rows[0]


def _outcome(browser: Browser) -> str | None:
    body = browser.session().json()
    assert body["authenticated"] is False
    outcome = body.get("authOutcome")
    return None if outcome is None else str(outcome["code"])


# --- AC-001.8 e SR-033: l'identità è il `sub`, non l'email ---------------------------------------


def test_ac_001_8_same_sub_with_a_changed_email_finds_the_same_account_and_updates_it(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    changed = Identity(sub=alfa.admin.sub, email="alice.nuova@example.test", name="Alice Alfa")
    browser.login(oidc, changed)
    body = browser.session().json()
    assert body["authenticated"] is True
    assert body["person"]["id"] == str(alfa.admin_person)
    assert body["family"]["name"] == "Famiglia Alfa"
    account = _account(owner, alfa.admin.sub)
    assert account[0] == alfa.admin_account, "stesso account, non un secondo"
    assert account[3] == "alice.nuova@example.test", "email aggiornata a ogni login (05-data §4.1)"
    assert bytes(account[4]) == email_sha256("alice.nuova@example.test"), "hash aggiornato (I-03)"
    assert count(owner, "account") == 2
    assert count(owner, "person") == 2


def test_the_email_hash_uses_the_single_normalisation_of_the_service(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """ADR-0011: `menu.common.email_sha256` (strip + lower) per servizio e console."""
    mixed = Identity(sub=alfa.admin.sub, email="Alice.Alfa@Example.TEST", name="Alice Alfa")
    browser.login(oidc, mixed)
    assert bytes(_account(owner, alfa.admin.sub)[4]) == email_sha256("alice.alfa@example.test")


def test_a_different_sub_with_the_email_of_an_existing_account_is_a_different_identity(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """SR-033, 05-data §4.1: l'email non è identità (Google riassegna gli indirizzi). Chi arriva
    con un altro `sub` e l'email di Alice non entra nell'account di Alice né nella sua famiglia."""
    impostor = Identity(sub="sub-impostore", email=alfa.admin.email, name="Alice Alfa")
    browser.login(oidc, impostor)
    assert SESSION not in browser.cookies
    assert _outcome(browser) == "not_member"
    assert count(owner, "account") == 2
    assert count(owner, "session") == 0
    assert _account(owner, alfa.admin.sub)[0] == alfa.admin_account
    assert (
        owner.scalar("select count(*) from app.account where auth_subject = 'sub-impostore'") == 0
    )


def test_the_display_name_is_proposed_by_google_once_and_then_belongs_to_the_user(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    """SR-054, 05-data §4.1: «proposto da Google alla creazione, poi solo modificabile»."""
    make_bootstrap(owner, make_family(owner, "Famiglia Gamma"), GESTORE_EMAIL)
    browser.login(oidc, GESTORE)
    assert _account(owner, GESTORE.sub)[5] == "Gestore Gamma"
    owner.execute(
        "update app.account set display_name = 'Nome scelto' where auth_subject = %s",
        (GESTORE.sub,),
    )
    renamed = Identity(sub=GESTORE.sub, email=GESTORE_EMAIL, name="Nome di Google cambiato")
    other_browser.login(oidc, renamed)
    assert _account(owner, GESTORE.sub)[5] == "Nome scelto"
    assert other_browser.session().json()["account"]["displayName"] == "Nome scelto"


@pytest.mark.parametrize(
    ("name", "check"),
    [
        ("N" * 100, lambda n: 1 <= len(n) <= 60),
        (None, lambda n: n.strip() != "" and len(n) <= 60),
        ("   ", lambda n: n.strip() != "" and len(n) <= 60),
        ("", lambda n: n.strip() != "" and len(n) <= 60),
        ("Zoë 🍝 Ünïcode", lambda n: n.strip() != ""),
    ],
    ids=["troppo-lungo", "assente", "solo-spazi", "vuoto", "unicode"],
)
def test_a_missing_or_unusable_google_name_still_yields_a_valid_display_name(
    browser: Browser, oidc: FakeOidc, owner: Owner, name: str | None, check: Any
) -> None:
    """Il `CHECK` di `display_name` (1..60, non vuoto) non deve far fallire il primo accesso."""
    make_bootstrap(owner, make_family(owner), GESTORE_EMAIL)
    browser.login(oidc, Identity(sub="sub-n", email=GESTORE_EMAIL, name=name))
    assert browser.session().json()["authenticated"] is True
    assert check(_account(owner, "sub-n")[5])


def test_only_the_fields_of_sr_014_are_stored_from_google(
    browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    """SR-014: nome, email, `sub`; niente foto, lingua, dominio, cognome (minimizzazione)."""
    make_bootstrap(owner, make_family(owner), GESTORE_EMAIL)
    extra = {
        "picture": "https://example.test/XTRA-PICTURE.png",
        "locale": "XTRA-LOCALE",
        "given_name": "XTRA-GIVEN",
        "family_name": "XTRA-FAMILYNAME",
        "hd": "xtra-hosted-domain.example.test",
        "at_hash": "XTRA-ATHASH",
        "profile": "https://example.test/XTRA-PROFILE",
    }
    browser.login(oidc, Identity(sub="sub-min", email=GESTORE_EMAIL, extra=extra))
    assert browser.session().json()["authenticated"] is True
    dump = database_dump_text(owner)
    assert "XTRA-" not in dump
    assert "xtra-hosted-domain" not in dump


# --- AC-002.1: riscatto del bootstrap ---------------------------------------------------------


def test_ac_002_1_first_login_with_the_bootstrap_email_creates_the_administrator(
    browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    family = make_family(owner, "Famiglia Gamma")
    bootstrap = make_bootstrap(owner, family, GESTORE_EMAIL)
    response = browser.login(oidc, GESTORE)
    assert response.status_code == 302
    assert response.headers["location"] == "/piano"

    body = browser.session().json()
    assert body["authenticated"] is True
    assert body["person"]["role"] == "admin"
    assert body["family"]["name"] == "Famiglia Gamma"
    assert body["account"]["displayName"] == "Gestore Gamma"

    account = _account(owner, GESTORE.sub)
    assert account[1] == "google"
    assert account[3] == GESTORE_EMAIL
    assert bytes(account[4]) == email_sha256(GESTORE_EMAIL)
    assert account[6] is not None, "email_verified_at valorizzato (email verificata da Google)"
    persons = owner.rows("select id, family_id, kind, status, role, account_id from app.person")
    assert len(persons) == 1
    person = persons[0]
    assert person[1:] == (family, "account", "active", "admin", account[0])
    redeemed = owner.rows(
        "select redeemed_at is not null, redeemed_person_id, email_sha256 "
        "from app.family_bootstrap where id = %s",
        (bootstrap,),
    )
    assert redeemed == [(True, person[0], None)], "riscattato, con l'hash dell'email cancellato"
    assert count(owner, "session") == 1


def test_ac_002_1_redemption_leaves_a_security_log_entry_for_the_login(
    browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    """SR-020: accessi riusciti nel registro, con attore e famiglia; nessun dato personale."""
    family = make_family(owner, "Famiglia Gamma")
    make_bootstrap(owner, family, GESTORE_EMAIL)
    browser.login(oidc, GESTORE)
    account = _account(owner, GESTORE.sub)[0]
    logins = security_events(owner, "auth.login")
    assert len(logins) == 1
    event = logins[0]
    assert event["outcome"] == "success"
    assert event["actor_kind"] == "account"
    assert event["actor_account_id"] == account
    assert event["family_id"] == family
    assert event["actor_role"] == "admin"
    blob = str(event).lower()
    assert GESTORE_EMAIL not in blob
    assert GESTORE.sub not in blob
    assert "gestore gamma" not in blob


def test_the_bootstrap_is_single_use_a_second_sub_with_the_same_email_gets_nothing(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    """SR-033: «il bootstrap si lega all'email solo fino al primo login, poi al `sub`»."""
    make_bootstrap(owner, make_family(owner, "Famiglia Gamma"), GESTORE_EMAIL)
    browser.login(oidc, GESTORE)
    late = Identity(sub="sub-secondo", email=GESTORE_EMAIL, name="Secondo Arrivato")
    other_browser.login(oidc, late)
    assert SESSION not in other_browser.cookies
    assert _outcome(other_browser) == "not_member"
    assert count(owner, "account") == 1
    assert count(owner, "person") == 1


def test_the_redeemer_logs_in_again_from_another_device_by_sub_only(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    make_bootstrap(owner, make_family(owner, "Famiglia Gamma"), GESTORE_EMAIL)
    browser.login(oidc, GESTORE)
    again = Identity(sub=GESTORE.sub, email="gestore.nuovo@example.test", name="Gestore Gamma")
    other_browser.login(oidc, again)
    assert other_browser.session().json()["person"]["role"] == "admin"
    assert count(owner, "account") == 1
    assert count(owner, "person") == 1
    assert count(owner, "session") == 2, "due dispositivi, due sessioni"


def test_ac_002_4_an_expired_bootstrap_does_not_make_an_administrator(
    browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    family = make_family(owner, "Famiglia Gamma")
    bootstrap = make_bootstrap(owner, family, GESTORE_EMAIL, age_days=8)
    browser.login(oidc, GESTORE)
    assert SESSION not in browser.cookies
    assert _outcome(browser) == "not_member", "il messaggio di AC-001.5"
    assert count(owner, "account") == 0
    assert count(owner, "person") == 0
    assert count(owner, "session") == 0
    still = owner.scalar(
        "select redeemed_at is null from app.family_bootstrap where id = %s", (bootstrap,)
    )
    assert still is True


def test_a_bootstrap_just_inside_seven_days_still_works(
    browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    make_bootstrap(owner, make_family(owner), GESTORE_EMAIL, age_days=6.9)
    browser.login(oidc, GESTORE)
    assert browser.session().json()["person"]["role"] == "admin"


@pytest.mark.parametrize(
    "email",
    [
        "gestore.canary+casa@example.test",
        "gestorecanary@example.test",
        "gestore.canary@example.test.evil.example",
        "gestore.canary@sub.example.test",
        "x.gestore.canary@example.test",
    ],
)
def test_thr_003_alias_and_look_alike_emails_do_not_redeem_the_bootstrap(
    browser: Browser, oidc: FakeOidc, owner: Owner, email: str
) -> None:
    """THR-003: confronto esatto con `lower(btrim())`, senza togliere punti né suffissi `+`."""
    bootstrap = make_bootstrap(owner, make_family(owner), GESTORE_EMAIL)
    browser.login(oidc, Identity(sub="sub-alias", email=email))
    assert SESSION not in browser.cookies
    assert _outcome(browser) == "not_member"
    assert count(owner, "account") == 0
    assert count(owner, "person") == 0
    assert owner.scalar(
        "select redeemed_at is null from app.family_bootstrap where id = %s", (bootstrap,)
    )


def test_the_bootstrap_email_matches_regardless_of_case(
    browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    make_bootstrap(owner, make_family(owner), GESTORE_EMAIL)
    browser.login(oidc, Identity(sub="sub-case", email="Gestore.Canary@EXAMPLE.test"))
    assert browser.session().json()["person"]["role"] == "admin"


def test_an_unverified_email_never_redeems_and_the_real_owner_can_still_do_it(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    """AC-001.7 + THR-003: `email_verified=false` con l'email giusta non toglie il bootstrap al
    suo vero destinatario."""
    make_bootstrap(owner, make_family(owner), GESTORE_EMAIL)
    liar = Identity(sub="sub-bugiardo", email=GESTORE_EMAIL, email_verified=False)
    browser.login(oidc, liar)
    assert SESSION not in browser.cookies
    assert count(owner, "account") == 0
    other_browser.login(oidc, GESTORE)
    assert other_browser.session().json()["person"]["role"] == "admin"


def test_each_bootstrap_only_serves_its_own_email(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, owner: Owner
) -> None:
    gamma, delta = make_family(owner, "Famiglia Gamma"), make_family(owner, "Famiglia Delta")
    make_bootstrap(owner, gamma, GESTORE_EMAIL)
    make_bootstrap(owner, delta, "delta.canary@example.test")
    browser.login(oidc, GESTORE)
    other_browser.login(oidc, Identity(sub="sub-delta", email="delta.canary@example.test"))
    assert browser.session().json()["family"]["name"] == "Famiglia Gamma"
    assert other_browser.session().json()["family"]["name"] == "Famiglia Delta"


def test_an_existing_member_stays_in_their_family_and_never_redeems_another_bootstrap(
    browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """ASM-050: una famiglia per account. Il login di un membro non consuma il bootstrap di altri
    nemmeno se l'email coincide."""
    gamma = make_family(owner, "Famiglia Gamma")
    bootstrap = make_bootstrap(owner, gamma, alfa.member.email)
    browser.login(oidc, alfa.member)
    body = browser.session().json()
    assert body["family"]["name"] == "Famiglia Alfa"
    assert body["person"]["role"] == "member"
    assert owner.scalar("select count(*) from app.person where family_id = %s", (gamma,)) == 0
    assert owner.scalar(
        "select redeemed_at is null from app.family_bootstrap where id = %s", (bootstrap,)
    )


# --- AC-002.1 end-to-end: dal comando della console al primo accesso --------------------------


def test_ac_002_1_end_to_end_from_the_console_command_to_the_first_login(
    browser: Browser, oidc: FakeOidc, owner: Owner, worker_db: str
) -> None:
    """Il Gestore crea la famiglia dalla console (SL-02) e il primo login la riscatta (SL-03a)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "APP_ENV": "test",
        "DATABASE_URL_CONSOLE": pg.cluster().role_url("menu_console", worker_db, sqlalchemy=True),
    }
    done = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-I",
            "-m",
            "menu",
            "console",
            "family",
            "bootstrap",
            "--name",
            "Famiglia Console",
            "--email-sha256",
            email_sha256(GESTORE_EMAIL).hex(),
        ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    family = UUID(re.findall(r"[0-9a-f-]{36}", done.stdout)[0])

    browser.login(oidc, GESTORE)
    body = browser.session().json()
    assert body["authenticated"] is True
    assert body["family"]["id"] == str(family)
    assert body["family"]["name"] == "Famiglia Console"
    assert body["person"]["role"] == "admin"
    kinds = [e["event_type"] for e in security_events(owner)]
    assert "console.family_bootstrap" in kinds
    assert "auth.login" in kinds


def test_two_members_of_other_families_do_not_see_each_other_in_the_session(
    browser: Browser, other_browser: Browser, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """THR-028: la sessione di Mario non porta dati dell'altra famiglia né degli altri account."""
    beta = make_family(owner, "CANARY-FAMIGLIA-BETA")
    make_member(
        owner,
        beta,
        sub="sub-beta",
        email="beta.canary@example.test",
        role="admin",
        display_name="Beta Admin",
    )
    browser.login(oidc, alfa.member)
    other_browser.login(oidc, Identity(sub="sub-beta", email="beta.canary@example.test"))
    assert "CANARY" not in browser.session().text
    assert "Famiglia Alfa" not in other_browser.session().text
    assert "Mario" not in other_browser.session().text
