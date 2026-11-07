"""Il contributore di export di `planning` copre `meal` e `meal_item` (SL-06a; 05-data §9.3).

Piano SL-06a: «contributore di `planning`». Perimetro `family`: i pasti e le voci della famiglia del
contesto e di nessun'altra, comprese le righe `removed` (il contenuto resta nella riga, 05-data
§4.2); nessuna colonna vietata (SR-072). Perimetro `self`: i pasti appartengono alla famiglia, non a
una persona (le presenze personali arrivano con `attendance`, SL-14): nessuna riga.
L'inventario «ogni tabella di famiglia ha un contributore» è in `test_export_inventory.py`.
"""

import importlib
import pkgutil
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest

from support.ctx import make_ctx
from support.dishes import World, make_dish
from support.export_inventory import forbidden_columns_in
from support.meals import add_item, make_meal
from support.owner import Owner

DAY = date(2026, 10, 24)


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


def _planning() -> Any:
    found = [c for c in _contributors() if type(c).__module__.startswith("menu.planning")]
    assert len(found) == 1, "ci vuole esattamente un ExportContributor in menu.planning"
    return found[0]


def test_planning_declares_meal_and_meal_item() -> None:
    assert _planning().tables == frozenset({"meal", "meal_item"})


def test_family_export_has_the_meals_and_items_of_this_family_only(
    tenancy: Any, owner: Owner, world: World
) -> None:
    mine, theirs = world.alfa, world.beta
    dish = make_dish(owner, mine, "Pasta e ceci")
    make_meal(owner, mine, DAY, "dinner", content_version=2, guests=2, guests_note="Zia Rita")
    add_item(owner, mine, DAY, "dinner", dish=dish)
    add_item(owner, mine, DAY, "dinner", text="Pane", position=1)
    make_meal(owner, mine, DAY, "lunch", presence="removed", content_version=1)
    other_dish = make_dish(owner, theirs, "CANARY-BETA-DISH")
    make_meal(owner, theirs, DAY, "dinner", guests_note="CANARY-BETA-OSPITI", guests=1)
    add_item(owner, theirs, DAY, "dinner", dish=other_dish)

    ctx = make_ctx(mine.id, mine.who("admin").account, "admin")
    with tenancy.family_tx(ctx) as tx:
        payload = _planning().export_family(tx)
    assert set(payload) <= {"meal", "meal_item"}
    meals = payload["meal"]
    assert sorted((m["meal_type"], m["presence"]) for m in meals) == [
        ("dinner", "added"),
        ("lunch", "removed"),
    ]
    assert len(payload["meal_item"]) == 2
    assert {str(i["family_id"]) for i in payload["meal_item"]} == {str(mine.id)}
    blob = str(payload)
    assert "CANARY-BETA" not in blob
    assert str(theirs.id) not in blob
    assert str(other_dish) not in blob
    assert forbidden_columns_in(payload) == []
    assert "Zia Rita" in blob, "le note degli ospiti sono contenuto della famiglia (05-data §10)"


def test_the_self_export_has_no_meals(tenancy: Any, owner: Owner, world: World) -> None:
    alfa = world.alfa
    make_meal(owner, alfa, DAY, "dinner", modified_by="planner")
    ctx = make_ctx(alfa.id, alfa.who("planner").account, "planner")
    with tenancy.family_tx(ctx) as tx:
        mine = _planning().export_self(tx, alfa.who("planner").account, alfa.who("planner").person)
    assert mine == {} or all(rows == [] for rows in mine.values())
