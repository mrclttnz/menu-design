"""SR-004: l'accesso non rivela se un account, un'email o un invito esistono (CR-SL03a-005).

Il callback risponde allo stesso modo per un `sub` sconosciuto, per un'identità non membro
(bootstrap scaduto, già riscattato da altri, email solo simile) e per un accesso manipolato
(email non verificata): stesso `302`, stesso `Location`, stesso corpo, stesse intestazioni (a meno
dei valori dei cookie) e stesso esito letto dalla sessione. Nulla dell'account, dell'email o
dell'invito compare nel messaggio o nel reindirizzamento. THR-002, THR-003.

Anche la corsa di due callback sullo stesso cookie del flusso (SR-033, INFO della revisione di
sicurezza): un solo callback può rivendicare il flusso.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from support.accounts import (
    AlfaWorld,
    count,
    make_account,
    make_bootstrap,
    make_family,
    make_person,
)
from support.browser_sim import FLOW, SESSION, Browser
from support.fake_oidc import FakeOidc, Identity
from support.owner import Owner

pytestmark = [pytest.mark.sec, pytest.mark.integration]

INVITED = "invitato.enum@example.test"


def _shape(browser: Browser, oidc: FakeOidc, who: Identity) -> dict[str, Any]:
    response = browser.login(oidc, who)
    headers = {k.lower(): v for k, v in response.headers.items()}
    headers.pop("set-cookie", None)
    outcome = browser.session()
    return {
        "status": response.status_code,
        "location": response.headers.get("location"),
        "body": response.text,
        "headers": headers,
        "has_session": SESSION in browser.cookies,
        "outcome": outcome.json().get("authOutcome"),
        "authenticated": outcome.json()["authenticated"],
    }


def test_sr_004_unknown_non_member_and_forged_logins_are_indistinguishable(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """SR-004: stesso 302, stesso Location, stesso corpo e stesso esito per ogni rifiuto."""
    other_family = make_family(owner, "Famiglia Segreta")
    make_bootstrap(
        owner, make_family(owner, "Famiglia Due"), "scaduto.enum@example.test", age_days=30
    )
    redeemed_family = make_family(owner, "Famiglia Tre")
    redeemed = make_bootstrap(owner, redeemed_family, "riscattato.enum@example.test")
    taker = make_person(
        owner, redeemed_family, make_account(owner, sub="sub-chi-ha-riscattato"), "admin"
    )
    owner.execute(
        "update app.family_bootstrap set redeemed_at = now(), redeemed_person_id = %s, "
        "email_sha256 = null where id = %s",
        (taker, redeemed),
    )
    make_bootstrap(owner, other_family, INVITED)
    # Un account esistente senza persona attiva (l'ex membro): non deve distinguersi.
    make_account(owner, sub="sub-ex-membro", email="ex.membro.enum@example.test")

    cases = {
        "sub sconosciuto": Identity(sub="sub-sconosciuto", email="nessuno.enum@example.test"),
        "bootstrap scaduto": Identity(sub="sub-scaduto", email="scaduto.enum@example.test"),
        "bootstrap riscattato": Identity(
            sub="sub-riscattato", email="riscattato.enum@example.test"
        ),
        "email alias dell'invito": Identity(sub="sub-alias", email="Invitato.Enum+x@example.test"),
        "account esistente senza famiglia": Identity(
            sub="sub-ex-membro", email="ex.membro.enum@example.test"
        ),
        "email invitata non verificata": Identity(
            sub="sub-falso", email=INVITED, email_verified=False
        ),
        "email non invitata non verificata": Identity(
            sub="sub-falso-3", email="mai.invitato.enum@example.test", email_verified=False
        ),
        "email_verified come stringa": Identity(
            sub="sub-falso-2", email=INVITED, email_verified="true"
        ),
    }
    shapes = {name: _shape(Browser(auth_client), oidc, who) for name, who in cases.items()}

    forged = {
        "email invitata non verificata",
        "email non invitata non verificata",
        "email_verified come stringa",
    }
    reference_name, reference = next(iter(shapes.items()))
    assert reference["status"] == 302
    assert reference["location"] == "/piano"
    assert reference["has_session"] is False
    assert reference["authenticated"] is False
    assert reference["outcome"]["code"] == "not_member"
    forged_outcomes = set()
    for name, shape in shapes.items():
        # Lo stesso 302, Location, corpo e intestazioni per tutti i rifiuti.
        common = {k: v for k, v in shape.items() if k != "outcome"}
        assert common == {k: v for k, v in reference.items() if k != "outcome"}, (
            f"'{name}' si distingue da '{reference_name}'"
        )
        if name in forged:
            forged_outcomes.add(str(shape["outcome"]))
        else:
            assert shape["outcome"] == reference["outcome"], f"esito di '{name}' diverso"
    # Un token manipolato ha un esito proprio, ma non dipende dall'esistenza dell'invito.
    assert len(forged_outcomes) == 1, f"esito manipolato dipende dall'invito: {forged_outcomes}"

    # Nessun dato di account, email, invito o famiglia nel messaggio né nel reindirizzamento.
    leaked = [
        *(w.email for w in cases.values()),
        *(w.sub for w in cases.values()),
        "Famiglia Segreta",
        "Famiglia Due",
        "Famiglia Tre",
        "Famiglia Alfa",
        str(other_family),
        str(redeemed),
        "bootstrap",
        "invito",
    ]
    text = str(reference)
    for value in leaked:
        assert value.lower() not in text.lower(), f"informazione rivelata: {value}"
    assert count(owner, "session") == 0
    assert (
        owner.scalar("select count(*) from app.account where auth_subject = 'sub-sconosciuto'") == 0
    )


def test_sr_033_two_callbacks_on_the_same_flow_handle_claim_it_only_once(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """Due callback in parallelo con lo stesso cookie del flusso: una sola sessione, un solo
    scambio del codice, nessun errore HTTP."""
    first = Browser(auth_client)
    started = first.start_login()
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    twin = Browser(auth_client, cookies={FLOW: first.cookies[FLOW]})
    barrier = threading.Barrier(2)

    def go(browser: Browser) -> int:
        barrier.wait(timeout=10)
        return int(browser.get(grant.callback_path).status_code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(go, [first, twin]))

    assert statuses == [302, 302]
    assert count(owner, "session") == 1, "un solo callback rivendica il flusso"
    assert [SESSION in b.cookies for b in (first, twin)].count(True) == 1
    assert oidc.calls("/token") == 1, "il codice si scambia una volta sola"
    assert count(owner, "auth_flow") == 0
