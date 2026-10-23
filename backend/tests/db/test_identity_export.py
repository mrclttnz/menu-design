"""Contributore di esportazione di `identity`, perimetro `self` (SL-03a; piano §2.2, OBJ-02).

05-data §9.3: `self` contiene «la propria riga `account` (comprese email, ...), le proprie sessioni
(dispositivo e date, senza IP)»; non contiene dati di altri né segreti. Il perimetro `family` non
riceve nulla da `identity` (i dati a livello di account degli altri membri sono esclusi, SR-072).
SR-014, SR-037, SR-047, THR-028.
"""

import importlib
import pkgutil
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from support.accounts import make_account, make_family, make_person
from support.ctx import make_ctx
from support.owner import Owner

SECRET_COLUMNS = {"token_hash", "csrf_token_hash", "ip_prefix", "auth_subject", "email_sha256"}


def _identity_contributors() -> list[Any]:
    import menu

    for info in pkgutil.walk_packages(menu.__path__, "menu."):
        if not info.name.endswith("__main__"):
            importlib.import_module(info.name)
    registry: Any = importlib.import_module("menu.common").export_contributors
    return [c for c in registry() if type(c).__module__.startswith("menu.identity")]


@pytest.fixture
def tenancy(app_url: str) -> Iterator[Any]:
    module: Any = importlib.import_module("menu.tenancy")
    module.init(app_url)
    try:
        yield module
    finally:
        module.dispose()


def test_identity_registers_one_contributor_for_account_and_session() -> None:
    found = _identity_contributors()
    assert len(found) == 1, "ci vuole esattamente un ExportContributor in menu.identity"
    assert set(found[0].tables) == {"account", "session"}


def test_self_scope_exports_the_own_account_row_and_own_sessions_only(
    owner: Owner, tenancy: Any
) -> None:
    family = make_family(owner)
    mine = make_account(owner, sub="sub-mia", email="mia.canary@example.test", display_name="Mia")
    theirs = make_account(
        owner, sub="sub-altrui", email="altrui.canary@example.test", display_name="CANARY-ALTRUI"
    )
    person = make_person(owner, family, mine, "admin")
    make_person(owner, family, theirs, "member")
    now = datetime.now(UTC)
    for account, label in ((mine, "Chrome · Android"), (theirs, "Firefox · Linux")):
        owner.execute(
            "insert into app.session (account_id, token_hash, csrf_token_hash, auth_time, "
            "device_label, ip_prefix) values (%s, %s, %s, %s, %s, '203.0.113.0/24')",
            (account, uuid4().bytes * 2, uuid4().bytes * 2, now - timedelta(hours=1), label),
        )
    contributor = _identity_contributors()[0]
    with tenancy.family_tx(make_ctx(family, mine, "admin")) as tx:
        payload = contributor.export_self(tx, mine, person)

    accounts, sessions = payload["account"], payload["session"]
    assert len(accounts) == 1
    assert accounts[0]["id"] == mine
    assert accounts[0]["email"] == "mia.canary@example.test", "la propria email c'è (05-data §9.3)"
    assert accounts[0]["display_name"] == "Mia"
    assert len(sessions) == 1
    assert sessions[0]["device_label"] == "Chrome · Android"
    blob = str(payload)
    assert "altrui" not in blob.lower()
    assert "CANARY-ALTRUI" not in blob
    assert "Firefox" not in blob, "le sessioni degli altri non escono (AC-047.3)"
    for column in SECRET_COLUMNS:
        assert all(column not in row for row in accounts + sessions), column
    assert "203.0.113" not in blob, "nessun IP, nemmeno troncato (05-data §9.3)"
    assert not any(
        isinstance(v, (bytes, memoryview)) for row in accounts + sessions for v in row.values()
    ), "nessun hash né dato binario nell'esportazione"


def test_family_scope_receives_nothing_from_identity(owner: Owner, tenancy: Any) -> None:
    """SR-072: l'Amministratore che esporta la famiglia non ottiene email né sessioni altrui."""
    family = make_family(owner)
    account = make_account(owner, email="admin.canary@example.test")
    make_person(owner, family, account, "admin")
    contributor = _identity_contributors()[0]
    with tenancy.family_tx(make_ctx(family, account, "admin")) as tx:
        payload = contributor.export_family(tx)
    assert all(not rows for rows in payload.values())
    assert "canary" not in str(payload)


def test_self_scope_of_an_account_without_sessions_still_returns_the_account_row(
    owner: Owner, tenancy: Any
) -> None:
    family = make_family(owner)
    account = make_account(owner)
    person = make_person(owner, family, account, "member")
    contributor = _identity_contributors()[0]
    with tenancy.family_tx(make_ctx(family, account, "member")) as tx:
        payload = contributor.export_self(tx, account, person)
    assert len(payload["account"]) == 1
    assert payload.get("session", []) == []
