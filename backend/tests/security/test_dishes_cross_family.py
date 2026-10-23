"""Isolamento tra famiglie dell'archivio piatti (SL-04): IDOR/BOLA e riferimenti nel corpo.

SR-008 (famiglia dalla membership), SR-041 (ogni identificativo nel corpo o nei parametri si
verifica nella stessa transazione della scrittura), THR-020, THR-021, THR-070. Per ogni operazione
con un identificativo ci sono un test marcato `cross_family("<operationId>")` (helper
`assert_cross_family`: 404 mai 403, corpo identico a un identificativo inesistente, evento
`access.cross_family`, nessun canarino, nessuna scrittura) e l'inventario che impedisce di
dimenticarne uno.
"""

import re
from collections.abc import Callable
from uuid import uuid4

import pytest

from support.accounts import security_events
from support.crossfamily import assert_cross_family
from support.dishes import (
    Actor,
    Who,
    World,
    dish_count,
    family_state_hash,
    make_dish,
    names,
    payload,
)
from support.matrix import MATRIX
from support.owner import Owner
from support.paths import BACKEND

pytestmark = [pytest.mark.sec, pytest.mark.integration]
Login = Callable[[Who], Actor]


# --- inventario: ogni operazione con identificativi ha il suo test cross_family -------------------


def test_every_catalog_operation_with_identifiers_has_a_cross_family_test() -> None:
    """08 §6.2: la differenza non vuota fa fallire (letta dai sorgenti, indipendente da -k)."""
    marked: set[str] = set()
    for path in (BACKEND / "tests").rglob("test_*.py"):
        marked |= set(re.findall(r'cross_family\("([a-z_.]+)"\)', path.read_text(encoding="utf-8")))
    needed = {op for op, row in MATRIX.items() if row["cross_family"] != "none"}
    assert needed >= {
        "catalog.dish.list",
        "catalog.dish.create",
        "catalog.dish.read",
        "catalog.dish.update",
    }
    assert needed - marked == set(), (
        f"operazioni senza test cross_family: {sorted(needed - marked)}"
    )


# --- identificativo nel percorso ------------------------------------------------------------------


@pytest.mark.cross_family("catalog.dish.read")
@pytest.mark.parametrize(("attacker", "victim"), [("alfa", "beta"), ("beta", "alfa")])
def test_reading_a_dish_of_another_family_is_404(
    attacker: str, victim: str, world: World, login: Login, owner: Owner
) -> None:
    a, v = world.fam(attacker), world.fam(victim)
    target = make_dish(owner, v, f"{v.canary}-DISH-1", notes=f"{v.canary}-NOTE")
    actor = login(a.who("planner"))
    assert_cross_family(
        owner=owner,
        attacker=actor,
        attacker_fam=a,
        victim=v,
        send_foreign=lambda: actor.get(f"/api/v1/dishes/{target}"),
        send_missing=lambda: actor.get(f"/api/v1/dishes/{uuid4()}"),
        victim_ids=(str(target),),
    )


@pytest.mark.cross_family("catalog.dish.update")
@pytest.mark.parametrize(("attacker", "victim"), [("alfa", "beta"), ("beta", "alfa")])
def test_updating_a_dish_of_another_family_is_404_and_changes_nothing(
    attacker: str, victim: str, world: World, login: Login, owner: Owner
) -> None:
    a, v = world.fam(attacker), world.fam(victim)
    target = make_dish(owner, v, f"{v.canary}-DISH-1")
    actor = login(a.who("admin"))
    assert_cross_family(
        owner=owner,
        attacker=actor,
        attacker_fam=a,
        victim=v,
        send_foreign=lambda: actor.put(f"/api/v1/dishes/{target}", payload(a, "Preso"), if_match=1),
        send_missing=lambda: actor.put(
            f"/api/v1/dishes/{uuid4()}", payload(a, "Preso"), if_match=1
        ),
        victim_ids=(str(target),),
    )


@pytest.mark.cross_family("catalog.dish.update")
def test_updating_a_foreign_dish_with_a_wrong_version_is_still_404_not_412(
    world: World, login: Login, owner: Owner
) -> None:
    """Un 412 rivelerebbe l'esistenza e la versione del piatto altrui."""
    target = make_dish(owner, world.beta, "CANARY-BETA-DISH-1")
    actor = login(world.alfa.who("planner"))
    response = actor.put(f"/api/v1/dishes/{target}", payload(world.alfa), if_match=99)
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# --- identificativi nel corpo (THR-021, SR-041) ---------------------------------------------------


@pytest.mark.cross_family("catalog.dish.create")
@pytest.mark.parametrize("mixed", [False, True])
def test_creating_with_a_course_of_another_family_is_404_and_writes_nothing(
    mixed: bool, world: World, login: Login, owner: Owner
) -> None:
    """Anche con una portata valida accanto a quella estranea: tutto o niente."""
    actor = login(world.alfa.who("planner"))
    foreign = str(world.beta.courses["first"])
    mine = str(world.alfa.courses["first"])
    course_ids = [mine, foreign] if mixed else [foreign]
    assert_cross_family(
        owner=owner,
        attacker=actor,
        attacker_fam=world.alfa,
        victim=world.beta,
        send_foreign=lambda: actor.post(
            "/api/v1/dishes", payload(world.alfa, courseIds=course_ids)
        ),
        send_missing=lambda: actor.post(
            "/api/v1/dishes",
            payload(world.alfa, courseIds=[mine, str(uuid4())] if mixed else [str(uuid4())]),
        ),
        victim_ids=(foreign,),
    )
    assert dish_count(owner, world.alfa) == 0, "nessuna scrittura parziale"
    assert dish_count(owner, world.beta) == 0


@pytest.mark.cross_family("catalog.dish.update")
def test_updating_my_dish_with_a_course_of_another_family_is_404_and_keeps_the_dish(
    world: World, login: Login, owner: Owner
) -> None:
    mine = make_dish(owner, world.alfa, "Pasta e ceci", courses=("first",))
    actor = login(world.alfa.who("planner"))
    foreign = str(world.beta.courses["first"])
    before = family_state_hash(owner, world.alfa)
    assert_cross_family(
        owner=owner,
        attacker=actor,
        attacker_fam=world.alfa,
        victim=world.beta,
        send_foreign=lambda: actor.put(
            f"/api/v1/dishes/{mine}",
            payload(world.alfa, "Cambiato", courseIds=[foreign]),
            if_match=1,
        ),
        send_missing=lambda: actor.put(
            f"/api/v1/dishes/{mine}",
            payload(world.alfa, "Cambiato", courseIds=[str(uuid4())]),
            if_match=1,
        ),
        victim_ids=(foreign,),
    )
    assert family_state_hash(owner, world.alfa) == before, "il piatto non cambia, versione compresa"


# --- identificativi nei parametri -----------------------------------------------------------------


@pytest.mark.cross_family("catalog.dish.list")
def test_filtering_the_list_by_a_course_of_another_family_is_404(
    world: World, login: Login, owner: Owner
) -> None:
    make_dish(owner, world.beta, "CANARY-BETA-DISH-1", courses=("first",))
    actor = login(world.alfa.who("planner"))
    foreign = world.beta.courses["first"]
    assert_cross_family(
        owner=owner,
        attacker=actor,
        attacker_fam=world.alfa,
        victim=world.beta,
        send_foreign=lambda: actor.get(f"/api/v1/dishes?courseId={foreign}"),
        send_missing=lambda: actor.get(f"/api/v1/dishes?courseId={uuid4()}"),
        victim_ids=(str(foreign),),
    )


# --- niente ha attraversato il confine ------------------------------------------------------------


def test_lists_and_searches_show_only_the_callers_family(
    world: World, login: Login, owner: Owner
) -> None:
    make_dish(owner, world.alfa, "Pasta e ceci", courses=("first",))
    make_dish(owner, world.alfa, "CANARY-ALFA-DISH-1", archived=True)
    make_dish(owner, world.beta, "Pasta e ceci beta", courses=("first",))
    make_dish(owner, world.beta, "CANARY-BETA-DISH-1", archived=True)
    alfa = login(world.alfa.who("planner"))
    beta = login(world.beta.who("planner"))
    for query in ("", "?q=pasta", "?q=canary&archived=true", "?archived=true"):
        assert "beta" not in " ".join(names(alfa.get("/api/v1/dishes" + query))).lower()
        assert "CANARY-ALFA" not in " ".join(names(beta.get("/api/v1/dishes" + query)))
    courses = {c["id"] for c in alfa.get("/api/v1/courses").json()["items"]}
    assert courses == {str(i) for i in world.alfa.courses.values()}


def test_no_cross_family_event_for_a_lawful_request(
    world: World, login: Login, owner: Owner
) -> None:
    mine = make_dish(owner, world.alfa, "Pasta e ceci")
    actor = login(world.alfa.who("planner"))
    assert actor.get(f"/api/v1/dishes/{mine}").status_code == 200
    assert actor.get("/api/v1/dishes").status_code == 200
    assert security_events(owner, "access.%") == []
