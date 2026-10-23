"""Il contributore di export di `catalog` copre i piatti (SL-04; 05-data §9.3, SR-072, OBJ-02).

Perimetro `family`: portate, piatti e fonti della famiglia del contesto e nessun dato di altre
famiglie. Perimetro `self`: nessuna riga dei piatti (non appartengono a una persona: il perimetro
`self` contiene solo gusti, settimane, presenze, eventi e visite della propria persona).
L'inventario «ogni tabella di famiglia ha un contributore» è in `test_export_inventory.py`.
"""

import importlib
import pkgutil
from collections.abc import Iterator
from typing import Any

import pytest

from support.ctx import make_ctx
from support.dishes import World, make_dish
from support.export_inventory import forbidden_columns_in
from support.owner import Owner


def _contributors() -> list[Any]:
    import menu

    for info in pkgutil.walk_packages(menu.__path__, "menu."):
        if not info.name.endswith("__main__"):
            importlib.import_module(info.name)
    registry: Any = importlib.import_module("menu.common").export_contributors
    return list(registry())


@pytest.fixture
def tenancy(app_url: str) -> Iterator[Any]:
    module: Any = importlib.import_module("menu.tenancy")
    module.init(app_url)
    try:
        yield module
    finally:
        module.dispose()


def _family_payload(
    tenancy: Any, world: World, which: str = "alfa"
) -> dict[str, list[dict[str, Any]]]:
    fam = world.fam(which)
    ctx = make_ctx(fam.id, fam.who("admin").account, "admin")
    merged: dict[str, list[dict[str, Any]]] = {}
    for c in _contributors():
        with tenancy.family_tx(ctx) as tx:
            for table, rows in c.export_family(tx).items():
                merged.setdefault(table, []).extend(rows)
    return merged


def test_catalog_declares_the_dish_tables() -> None:
    declared = set()
    for c in _contributors():
        if type(c).__module__.startswith("menu.catalog"):
            declared |= set(c.tables)
    assert {"course", "dish", "dish_course", "dish_source"} <= declared


def test_family_export_has_dishes_courses_and_sources_of_this_family_only(
    tenancy: Any, owner: Owner, world: World
) -> None:
    make_dish(
        owner,
        world.alfa,
        "CANARY-ALFA-DISH-1",
        courses=("first", "second"),
        notes="CANARY-ALFA-NOTE",
        sources=({"kind": "link", "reference": "https://ricette.example.test/a"},),
    )
    make_dish(
        owner,
        world.beta,
        "CANARY-BETA-DISH-1",
        sources=({"kind": "other", "reference": "CANARY-BETA-SRC"},),
    )
    payload = _family_payload(tenancy, world)
    assert [r["name"] for r in payload["dish"]] == ["CANARY-ALFA-DISH-1"]
    assert len(payload["dish_course"]) == 2
    assert [r["reference"] for r in payload["dish_source"]] == ["https://ricette.example.test/a"]
    assert forbidden_columns_in(payload) == []
    blob = str(payload)
    assert "CANARY-BETA" not in blob, "nessun dato di un'altra famiglia"
    assert str(world.beta.id) not in blob


def test_family_export_keeps_archived_dishes(tenancy: Any, owner: Owner, world: World) -> None:
    """Il perimetro `family` contiene l'intero archivio, archiviati compresi (SR-017/SR-072)."""
    make_dish(owner, world.alfa, "Lasagne", archived=True)
    payload = _family_payload(tenancy, world)
    assert [r["name"] for r in payload["dish"]] == ["Lasagne"]


def test_self_export_has_no_dish_rows(tenancy: Any, owner: Owner, world: World) -> None:
    make_dish(owner, world.alfa, "Frittata")
    who = world.alfa.who("planner")
    ctx = make_ctx(world.alfa.id, who.account, "planner")
    for c in _contributors():
        with tenancy.family_tx(ctx) as tx:
            part = c.export_self(tx, who.account, who.person)
        assert not set(part) & {"dish", "dish_course", "dish_source"}


def test_export_without_family_context_reads_no_dish(
    tenancy: Any, owner: Owner, world: World
) -> None:
    make_dish(owner, world.alfa, "CANARY-ALFA-DISH-1")
    ctx = make_ctx(world.beta.id, world.beta.who("admin").account, "admin")
    payload: dict[str, list[dict[str, Any]]] = {}
    for c in _contributors():
        with tenancy.family_tx(ctx) as tx:
            for table, rows in c.export_family(tx).items():
                payload.setdefault(table, []).extend(rows)
    assert payload.get("dish", []) == []
    assert "CANARY-ALFA" not in str(payload)
