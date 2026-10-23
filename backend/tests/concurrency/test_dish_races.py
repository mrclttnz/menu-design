"""Concorrenza dell'archivio piatti (SL-04; 08 §9, SR-060, ADR-0008).

Invarianti (non si asserisce quale richiesta vince, solo i conteggi):
- famiglia con 1.999 piatti e N creazioni insieme: ESATTAMENTE una `201`, le altre
  `409 quota_exceeded {quota: dishes}`; mai più di 2.000 piatti (quota atomica, lock famiglia);
- due `PUT` con lo stesso `If-Match`: una `200`, l'altra `412`; versione +1, nessuna perdita.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID

import pytest
from httpx import Response

from support.dishes import (
    DISH_QUOTA,
    Actor,
    Who,
    World,
    bulk_dishes,
    dish_count,
    dish_row,
    make_dish,
    payload,
)
from support.owner import Owner

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]
Login = Callable[[Who], Actor]


def _create(actor: Actor, world: World, n: int) -> Callable[[], Response]:
    return lambda: actor.post("/api/v1/dishes", payload(world.alfa, f"Gara {n}"))


def _update(actor: Actor, world: World, dish: UUID, name: str) -> Callable[[], Response]:
    return lambda: actor.put(f"/api/v1/dishes/{dish}", payload(world.alfa, name), if_match=1)


def _race(calls: list[Callable[[], Response]]) -> list[Response]:
    barrier = threading.Barrier(len(calls))

    def go(call: Callable[[], Response]) -> Response:
        barrier.wait(timeout=20)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return [f.result(timeout=60) for f in [pool.submit(go, c) for c in calls]]


def test_two_creations_at_1999_dishes_let_exactly_one_through(
    world: World, login: Login, owner: Owner
) -> None:
    bulk_dishes(owner, world.alfa, DISH_QUOTA - 1)
    assert dish_count(owner, world.alfa) == 1999
    actors = [login(world.alfa.who("planner")), login(world.alfa.who("admin"))]
    responses = _race([_create(a, world, n) for n, a in enumerate(actors)])
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 409], [r.text for r in responses]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["code"] == "quota_exceeded"
    assert loser.json()["params"]["quota"] == "dishes"
    assert loser.json()["params"]["limit"] == DISH_QUOTA, (
        "UX: validation.limit_reached usa il limite"
    )
    assert dish_count(owner, world.alfa) == DISH_QUOTA


def test_six_contenders_at_1998_dishes_leave_exactly_two_winners(
    world: World, login: Login, owner: Owner
) -> None:
    bulk_dishes(owner, world.alfa, DISH_QUOTA - 2)
    actors = [
        login(world.alfa.who(r))
        for r in ("planner", "admin", "planner", "admin", "planner", "admin")
    ]
    responses = _race([_create(a, world, n) for n, a in enumerate(actors)])
    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 201, 409, 409, 409, 409], codes
    assert dish_count(owner, world.alfa) == DISH_QUOTA


def test_the_2001st_dish_is_refused_and_nothing_is_written(
    world: World, login: Login, owner: Owner
) -> None:
    bulk_dishes(owner, world.alfa, DISH_QUOTA)
    planner = login(world.alfa.who("planner"))
    refused = planner.post("/api/v1/dishes", payload(world.alfa, "Uno di troppo"))
    assert refused.status_code == 409
    assert refused.json()["code"] == "quota_exceeded"
    assert dish_count(owner, world.alfa) == DISH_QUOTA
    still_ok = planner.get("/api/v1/dishes")
    assert still_ok.status_code == 200, "la famiglia piena legge e cerca normalmente"


def test_archived_dishes_count_towards_the_quota(world: World, login: Login, owner: Owner) -> None:
    """ASM-034: «≤ 2.000 piatti per famiglia»; un piatto archiviato occupa ancora un posto."""
    bulk_dishes(owner, world.alfa, DISH_QUOTA - 1)
    owner.execute(
        "update app.dish set ever_planned = true, archived_at = app.now_utc() "
        "where id in (select id from app.dish where family_id = %s limit 500)",
        (world.alfa.id,),
    )
    planner = login(world.alfa.who("planner"))
    assert planner.post("/api/v1/dishes", payload(world.alfa, "L'ultimo")).status_code == 201
    assert planner.post("/api/v1/dishes", payload(world.alfa, "Troppo")).status_code == 409


def test_the_quota_is_per_family(world: World, login: Login, owner: Owner) -> None:
    bulk_dishes(owner, world.beta, DISH_QUOTA)
    planner = login(world.alfa.who("planner"))
    assert (
        planner.post("/api/v1/dishes", payload(world.alfa, "Il primo di Alfa")).status_code == 201
    )


def test_two_puts_with_the_same_if_match_one_wins_one_gets_412(
    world: World, login: Login, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    planner, admin = login(world.alfa.who("planner")), login(world.alfa.who("admin"))
    responses = _race(
        [
            _update(planner, world, dish, "Dal pianificatore"),
            _update(admin, world, dish, "Dall'amministratore"),
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 412], [r.text for r in responses]
    winner = next(r for r in responses if r.status_code == 200)
    row = dish_row(owner, dish)
    assert row is not None
    assert row[4] == 2, "una sola scrittura riuscita: versione 2"
    assert row[0] == winner.json()["name"], (
        "nessuna perdita silenziosa: resta il nome del vincitore"
    )
    loser = next(r for r in responses if r.status_code == 412)
    assert loser.json()["code"] == "conflict"


def test_many_puts_with_the_same_version_have_a_single_winner(
    world: World, login: Login, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    actors: list[Actor] = [
        login(world.alfa.who(r)) for r in ("planner", "admin", "planner", "admin")
    ]
    responses = _race([_update(a, world, dish, f"Voce {n}") for n, a in enumerate(actors)])
    codes: list[Any] = sorted(r.status_code for r in responses)
    assert codes == [200, 412, 412, 412], codes
    row = dish_row(owner, dish)
    assert row is not None
    assert row[4] == 2
