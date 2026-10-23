"""Riscatto del bootstrap sotto concorrenza (SL-03a; 08 §9, THR-003, SR-033).

Invariante: il bootstrap è monouso. Se più accessi con l'email giusta ma `sub` diversi arrivano
nello stesso istante, ESATTAMENTE uno diventa Amministratore; gli altri non ottengono sessione,
account né persona. Non si asserisce chi vince (l'ordine non è deterministico), solo l'invariante.
Anche lo stesso `sub` che completa il callback due volte in parallelo (doppio clic) crea un solo
account e una sola persona.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from support.accounts import count, make_bootstrap, make_family
from support.browser_sim import SESSION, Browser
from support.fake_oidc import FakeOidc, Identity
from support.owner import Owner

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]

EMAIL = "gestore.canary@example.test"
CONTENDERS = 5


def _race(browsers_and_paths: list[tuple[Browser, str]]) -> list[Response]:
    barrier = threading.Barrier(len(browsers_and_paths))

    def go(item: tuple[Browser, str]) -> Response:
        browser, path = item
        barrier.wait(timeout=10)
        return browser.get(path)

    with ThreadPoolExecutor(max_workers=len(browsers_and_paths)) as pool:
        return list(pool.map(go, browsers_and_paths))


def test_exactly_one_of_many_simultaneous_first_logins_redeems_the_bootstrap(
    auth_client: TestClient, oidc: FakeOidc, owner: Owner
) -> None:
    bootstrap = make_bootstrap(owner, make_family(owner, "Famiglia Gamma"), EMAIL)
    contenders = []
    for index in range(CONTENDERS):
        browser = Browser(auth_client)
        started = browser.start_login()
        identity = Identity(sub=f"sub-corsa-{index}", email=EMAIL, name=f"Concorrente {index}")
        grant = oidc.authorize(started.json()["redirectUrl"], identity)
        contenders.append((browser, grant.callback_path))

    results = _race(contenders)

    assert [r.status_code for r in results] == [302] * CONTENDERS, "nessun errore HTTP"
    winners = [b for b, _ in contenders if SESSION in b.cookies]
    assert len(winners) == 1, f"un solo vincitore, trovati {len(winners)}"
    assert winners[0].session().json()["person"]["role"] == "admin"
    assert count(owner, "account") == 1
    assert count(owner, "person") == 1
    assert count(owner, "session") == 1
    assert owner.scalar("select count(*) from app.person where role = 'admin'") == 1
    redeemed = owner.rows(
        "select redeemed_at is not null, redeemed_person_id is not null, email_sha256 is null "
        "from app.family_bootstrap where id = %s",
        (bootstrap,),
    )
    assert redeemed == [(True, True, True)]
    for browser, _ in contenders:
        if browser is not winners[0]:
            assert browser.session().json()["authenticated"] is False


def test_the_same_identity_completing_two_callbacks_at_once_creates_one_account(
    auth_client: TestClient, oidc: FakeOidc, owner: Owner
) -> None:
    """Doppio clic / due schede: un solo account e una sola persona per quel `sub`."""
    make_bootstrap(owner, make_family(owner, "Famiglia Gamma"), EMAIL)
    identity = Identity(sub="sub-doppio", email=EMAIL, name="Gestore Gamma")
    contenders = []
    for _ in range(2):
        browser = Browser(auth_client)
        started = browser.start_login()
        grant = oidc.authorize(started.json()["redirectUrl"], identity)
        contenders.append((browser, grant.callback_path))

    results = _race(contenders)

    assert [r.status_code for r in results] == [302, 302]
    assert count(owner, "account") == 1
    assert count(owner, "person") == 1
    logged = [b for b, _ in contenders if b.session().json()["authenticated"]]
    assert logged, "almeno uno dei due accessi riesce"
    assert count(owner, "session") == len(logged), "nessuna sessione orfana"


def test_simultaneous_logins_of_different_members_all_succeed_with_a_cold_jwks_cache(
    auth_client: TestClient, oidc: FakeOidc, owner: Owner
) -> None:
    """AC-001.1 sotto carico: il JWKS è freddo (client appena creato) e N callback arrivano
    insieme. Nessuno deve essere respinto per una corsa su cache/refresh delle chiavi
    (diagnosi dell'e2e parallelo: la causa era il provider finto, non l'app)."""
    from support.accounts import make_member

    family = make_family(owner, "Famiglia Delta")
    contenders = []
    for index in range(CONTENDERS + 3):
        sub, email = f"sub-membro-{index}", f"membro.{index}@example.test"
        make_member(owner, family, sub=sub, email=email, display_name=f"Membro {index}")
        browser = Browser(auth_client)
        started = browser.start_login()
        grant = oidc.authorize(started.json()["redirectUrl"], Identity(sub=sub, email=email))
        contenders.append((browser, grant.callback_path))

    results = _race(contenders)

    assert [r.status_code for r in results] == [302] * len(contenders)
    assert [SESSION in b.cookies for b, _ in contenders] == [True] * len(contenders)
