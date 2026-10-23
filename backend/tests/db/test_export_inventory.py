"""Inventario degli `ExportContributor` contro le tabelle reali e perimetro dei dati esportati
(plan §2.2, OBJ-02; 08 §6.8; 05-data §9.3; SR-072). SL-02.

Nota di collocazione: il piano cita `tests/tools/export_inventory`, ma `make test-unit` esegue
`tests/tools` senza database; il confronto con il catalogo vive quindi in `tests/db`, la parte
pura in `tests/unit/test_export_inventory_logic.py`.
"""

import importlib
import pkgutil
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from menu.common import email_sha256
from support.accounts import make_account
from support.ctx import make_ctx
from support.export_inventory import (
    NOT_EXPORTED,
    export_inventory_problems,
    forbidden_columns_in,
)
from support.inventory import family_tables
from support.owner import Owner

CANARY_EMAIL = "canary.export@example.test"


def _contributors() -> list[Any]:
    import menu

    for info in pkgutil.walk_packages(menu.__path__, "menu."):
        if not info.name.endswith("__main__"):
            importlib.import_module(info.name)
    registry: Any = importlib.import_module("menu.common").export_contributors
    return list(registry())


def _label(index: int, contributor: Any) -> str:
    return f"{type(contributor).__module__}.{type(contributor).__qualname__}#{index}"


def test_every_family_table_has_exactly_one_export_contributor(
    catalog: psycopg.Connection,
) -> None:
    declared = {_label(i, c): set(c.tables) for i, c in enumerate(_contributors())}
    assert declared, "nessun ExportContributor registrato"
    assert export_inventory_problems(declared, family_tables(catalog), NOT_EXPORTED) == []


def test_exclusions_are_family_tables_that_exist(catalog: psycopg.Connection) -> None:
    assert set(NOT_EXPORTED) <= set(family_tables(catalog))


# --- perimetro dei dati prodotti (SR-072) ---------------------------------------------------------


@pytest.fixture
def tenancy(app_url: str) -> Iterator[Any]:
    module: Any = importlib.import_module("menu.tenancy")
    module.init(app_url)
    try:
        yield module
    finally:
        module.dispose()


class World:
    def __init__(self, owner: Owner) -> None:
        self.alfa, self.beta = uuid4(), uuid4()
        for family, name in ((self.alfa, "Famiglia Alfa"), (self.beta, "CANARY-BETA-FAMIGLIA")):
            owner.execute(
                "insert into app.family (id, name, frozen_through) values (%s, %s, '2026-01-01')",
                (family, name),
            )
            for code in ("starter", "first"):
                owner.execute(
                    "insert into app.course (family_id, base_code) values (%s, %s)", (family, code)
                )
            owner.execute("insert into app.family_default_meal values (%s, 'lunch')", (family,))
            owner.execute(
                "insert into app.family_bootstrap (family_id, email_sha256, created_at, "
                "expires_at) values (%s, %s, '2026-10-01T00:00:00Z', '2026-10-08T00:00:00Z')",
                (family, email_sha256(CANARY_EMAIL)),
            )
        self.admin_account, self.member_account = uuid4(), uuid4()
        self.admin, self.member, self.beta_person = uuid4(), uuid4(), uuid4()
        for pid, family, account, role in (
            (self.admin, self.alfa, self.admin_account, "admin"),
            (self.member, self.alfa, self.member_account, "member"),
            (self.beta_person, self.beta, uuid4(), "admin"),
        ):
            make_account(owner, account_id=account)  # SL-03a: FK person.account_id
            owner.execute(
                "insert into app.person (id, family_id, kind, status, account_id, role, "
                "joined_on) values (%s, %s, 'account', 'active', %s, %s, '2026-01-01')",
                (pid, family, account, role),
            )


@pytest.fixture
def world(owner: Owner) -> World:
    return World(owner)


def _merge(parts: list[dict[str, list[dict[str, Any]]]]) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for part in parts:
        for table, rows in part.items():
            merged.setdefault(table, []).extend(rows)
    return merged


def test_family_scope_contains_family_content_and_nothing_excluded(
    tenancy: Any, world: World
) -> None:
    contributors = _contributors()
    ctx = make_ctx(world.alfa, world.admin_account, "admin")
    parts = []
    for c in contributors:
        with tenancy.family_tx(ctx) as tx:
            part = c.export_family(tx)
        assert set(part) <= set(c.tables), "un contributore produce solo le proprie tabelle"
        parts.append(part)
    payload = _merge(parts)

    assert [r["name"] for r in payload["family"]] == ["Famiglia Alfa"]
    assert len(payload["course"]) == 2
    assert len(payload["family_default_meal"]) == 1
    assert len(payload["person"]) == 2, "entrambe le persone della famiglia"
    assert "family_bootstrap" not in payload, "hash dell'email del Gestore mai esportato"
    assert forbidden_columns_in(payload) == []
    blob = str(payload).lower()
    assert "canary-beta" not in blob, "nessun dato di un'altra famiglia"
    assert str(world.beta_person) not in blob
    assert "canary.export" not in blob
    assert email_sha256(CANARY_EMAIL).hex() not in blob


def test_self_scope_contains_only_the_requesters_person(tenancy: Any, world: World) -> None:
    ctx = make_ctx(world.alfa, world.admin_account, "admin")
    parts = []
    for c in _contributors():
        with tenancy.family_tx(ctx) as tx:
            part = c.export_self(tx, world.admin_account, world.admin)
        assert set(part) <= set(c.tables)
        parts.append(part)
    payload = _merge(parts)
    blob = str(payload)
    assert str(world.admin) in blob, "la propria persona è nel perimetro `self`"
    assert str(world.member) not in blob, "nessuna persona di altri (SR-072)"
    assert str(world.member_account) not in blob
    assert "CANARY-BETA" not in blob
    # SL-03a: il perimetro `self` comprende la PROPRIA riga `account` (email compresa, 05-data
    # §9.3); il resto resta soggetto all'elenco delle colonne escluse. La riga `account` e le
    # sessioni sono provate a parte in `test_identity_export.py`.
    assert (
        forbidden_columns_in({t: r for t, r in payload.items() if t not in {"account", "session"}})
        == []
    )
    assert "family_bootstrap" not in payload


def test_self_scope_without_a_person_returns_no_person_rows(tenancy: Any, world: World) -> None:
    """Account senza persona in questa famiglia (profilo non collegato, `person_id=None`)."""
    ctx = make_ctx(world.alfa, uuid4(), "member")
    parts = []
    for c in _contributors():
        with tenancy.family_tx(ctx) as tx:
            parts.append(c.export_self(tx, uuid4(), None))
    assert _merge(parts).get("person", []) == []


def test_contributors_read_nothing_without_the_family_context(tenancy: Any, world: World) -> None:
    """La RLS vale anche per l'export: contesto di una famiglia vuota → nessuna riga di Alfa."""
    ctx = make_ctx(uuid4(), world.admin_account, "admin")
    parts = []
    for c in _contributors():
        with tenancy.family_tx(ctx) as tx:
            parts.append(c.export_family(tx))
    payload = _merge(parts)
    assert str(world.alfa) not in str(payload)
    assert all(not rows for rows in payload.values())
