"""Il contributore di export di `history` copre `change_event` (SL-05; 05-data §9.3, OBJ-02).

Piano SL-05: «contributore di `history`». Perimetro `family`: gli eventi della famiglia del
contesto e di nessun'altra; solo identificativi (SR-047), nessuna colonna vietata (SR-072).
L'inventario «ogni tabella di famiglia ha un contributore» è in `test_export_inventory.py`
(si accende da solo quando la migrazione 0008 crea la tabella).
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


def _event(owner: Owner, world: World, which: str, dish: Any) -> None:
    fam = world.fam(which)
    owner.execute(
        "insert into app.change_event (family_id, actor_kind, actor_person_id, actor_role, "
        "unit_type, op, dish_id, before, after) values (%s, 'person', %s, 'planner', 'dish', "
        """'status_change', %s, '{"st":"to_try"}', '{"v":1,"st":"tested"}')""",
        (fam.id, fam.who("planner").person, dish),
    )


def _family_payload(tenancy: Any, world: World, which: str) -> dict[str, list[dict[str, Any]]]:
    fam = world.fam(which)
    ctx = make_ctx(fam.id, fam.who("admin").account, "admin")
    merged: dict[str, list[dict[str, Any]]] = {}
    for c in _contributors():
        with tenancy.family_tx(ctx) as tx:
            for table, rows in c.export_family(tx).items():
                merged.setdefault(table, []).extend(rows)
    return merged


def test_history_declares_change_event() -> None:
    declared = set()
    for c in _contributors():
        if type(c).__module__.startswith("menu.history"):
            declared |= set(c.tables)
    assert "change_event" in declared


def test_family_export_has_the_events_of_this_family_only(
    tenancy: Any, owner: Owner, world: World
) -> None:
    mine = make_dish(owner, world.alfa, "Pasta e ceci")
    theirs = make_dish(owner, world.beta, "CANARY-BETA-DISH-1")
    _event(owner, world, "alfa", mine)
    _event(owner, world, "beta", theirs)
    payload = _family_payload(tenancy, world, "alfa")
    rows = payload["change_event"]
    assert [str(r["dish_id"]) for r in rows] == [str(mine)]
    assert str(rows[0]["actor_person_id"]) == str(world.alfa.who("planner").person)
    assert forbidden_columns_in(payload) == []
    blob = str(payload["change_event"])
    assert str(theirs) not in blob
    assert str(world.beta.id) not in blob
    assert "@" not in blob, "nessuna email negli eventi esportati (SR-047)"
    assert "Pasta e ceci" not in blob, "il nome del piatto non è nell'evento"


def _insert(owner: Owner, family: Any, actor: Any, subject: Any, dish: Any) -> None:
    unit, op, state = ("membership", "role_change", '{"r":"planner"}')
    if subject is None:
        unit, op, state = ("dish", "status_change", '{"st":"tested"}')
    owner.execute(
        "insert into app.change_event (family_id, actor_kind, actor_person_id, actor_role, "
        "unit_type, op, subject_person_id, dish_id, before, after) "
        "values (%s, 'person', %s, 'planner', %s, %s, %s, %s, null, "
        "(%s::jsonb || '{\"v\":1}'::jsonb))",
        (family, actor, unit, op, subject, dish, state),
    )


def test_self_export_has_events_authored_or_about_the_person_only(
    tenancy: Any, owner: Owner, world: World
) -> None:
    """CR-SL05-007: perimetro `self` = autore O soggetto; `person_id=None` non esporta nulla."""
    alfa = world.alfa
    p1, p2 = alfa.who("planner").person, alfa.who("admin").person
    dish = make_dish(owner, alfa, "Pasta e ceci")
    _insert(owner, alfa.id, p1, None, dish)  # autore P1
    _insert(owner, alfa.id, p2, p1, None)  # soggetto P1, autore P2
    _insert(owner, alfa.id, p2, None, dish)  # né autore né soggetto
    _insert(
        owner,
        world.beta.id,
        world.beta.who("planner").person,
        None,
        make_dish(owner, world.beta, "X"),
    )
    ctx = make_ctx(alfa.id, alfa.who("planner").account, "planner")
    exporters = [c for c in _contributors() if type(c).__module__.startswith("menu.history")]
    assert len(exporters) == 1
    with tenancy.family_tx(ctx) as tx:
        mine = exporters[0].export_self(tx, alfa.who("planner").account, p1)
        nobody = exporters[0].export_self(tx, alfa.who("planner").account, None)
    rows = mine["change_event"]
    assert sorted((str(r["actor_person_id"]), str(r["subject_person_id"])) for r in rows) == sorted(
        [(str(p1), "None"), (str(p2), str(p1))]
    )
    assert nobody == {}
