"""Concorrenza della presenza del pasto (SL-06a; 08 §9, ADR-0008, ADR-0012, SR-070).

Invarianti (non si asserisce quale richiesta vince, solo i conteggi):
- due richieste con lo stesso `If-Match` sullo stesso pasto: ESATTAMENTE una `200`, l'altra `412`;
  una sola riga, versione +1, ESATTAMENTE un evento e un solo consumo del tetto;
- una rimozione e un'aggiunta opposte sulla stessa versione: una sola vince;
- pasti diversi dello stesso giorno insieme: tutti riescono, un evento ciascuno, il contatore a N
  esatti (nessun aggiornamento perso);
- la creazione della stessa riga `meal` da due richieste insieme non dà mai `500` (PK contesa);
- il tetto resta atomico: a `limite - k` con `k + m` richieste, `k` riescono e `m` danno `429`.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from httpx import Response

from support.dishes import Actor, Who, World, event_rows
from support.meals import T0, meal_rows, presence_url
from support.owner import Owner
from support.tracks import DAILY_LIMIT, local_day_start_utc, seed_tracked, tracked_count

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]
Login = Callable[[Who], Actor]
DAY = date(2026, 10, 24)


def _put(
    actor: Actor, meal_type: str, present: bool, version: int, slot: int = 0
) -> Callable[[], Response]:
    return lambda: actor.put(
        presence_url(DAY, meal_type, slot), {"present": present}, if_match=version
    )


def _race(calls: list[Callable[[], Response]]) -> list[Response]:
    barrier = threading.Barrier(len(calls))

    def go(call: Callable[[], Response]) -> Response:
        barrier.wait(timeout=20)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return [f.result(timeout=60) for f in [pool.submit(go, c) for c in calls]]


def test_two_removals_with_the_same_if_match_one_wins_and_one_event_is_written(
    meal_world: World, login: Login, owner: Owner
) -> None:
    planner, admin = login(meal_world.alfa.who("planner")), login(meal_world.alfa.who("admin"))
    responses = _race([_put(planner, "dinner", False, 0), _put(admin, "dinner", False, 0)])
    assert sorted(r.status_code for r in responses) == [200, 412], [r.text for r in responses]
    (row,) = meal_rows(owner, meal_world.alfa)
    assert (row["presence"], row["content_version"]) == ("removed", 1)
    assert len(event_rows(owner)) == 1
    assert tracked_count(owner, meal_world.alfa.id) == 1, "il perdente non consuma il tetto"


def test_a_removal_and_an_addition_on_the_same_version_cannot_both_apply(
    meal_world: World, login: Login, owner: Owner
) -> None:
    planner, admin = login(meal_world.alfa.who("planner")), login(meal_world.alfa.who("admin"))
    responses = _race([_put(planner, "snack", True, 0), _put(admin, "snack", False, 0)])
    assert sorted(r.status_code for r in responses) == [200, 412], [r.text for r in responses]
    (row,) = meal_rows(owner, meal_world.alfa)
    assert row["content_version"] == 1
    assert len(event_rows(owner)) == 1


def test_a_stale_write_racing_a_re_add_never_writes_on_the_new_meal(
    meal_world: World, login: Login, owner: Owner
) -> None:
    """Rimosso a versione 1; ora «aggiungi» (1) e «togli» ancora con la versione 1 insieme."""
    planner, admin = login(meal_world.alfa.who("planner")), login(meal_world.alfa.who("admin"))
    assert _put(planner, "dinner", False, 0)().status_code == 200
    responses = _race([_put(planner, "dinner", True, 1), _put(admin, "dinner", False, 1)])
    assert sorted(r.status_code for r in responses) == [200, 412], [r.text for r in responses]
    (row,) = meal_rows(owner, meal_world.alfa)
    assert row["content_version"] == 2
    assert len(event_rows(owner)) == 2


def test_six_different_meals_of_a_day_leave_exactly_six_events_and_count_six(
    meal_world: World, login: Login, owner: Owner
) -> None:
    actors = [login(meal_world.alfa.who("planner" if n % 2 else "admin")) for n in range(6)]
    calls = [
        _put(actors[0], "breakfast", True, 0),
        _put(actors[1], "lunch", False, 0),
        _put(actors[2], "snack", True, 0),
        _put(actors[3], "dinner", False, 0),
        _put(actors[4], "other", True, 0, 0),
        _put(actors[5], "other", True, 0, 1),
    ]
    responses = _race(calls)
    assert [r.status_code for r in responses] == [200] * 6, [r.text for r in responses]
    assert len(meal_rows(owner, meal_world.alfa)) == 6
    assert len(event_rows(owner)) == 6
    assert tracked_count(owner, meal_world.alfa.id) == 6, "nessun aggiornamento perso"


def test_two_creations_of_the_same_new_row_never_give_a_server_error(
    meal_world: World, login: Login, owner: Owner
) -> None:
    actors = [login(meal_world.alfa.who("planner")) for _ in range(4)]
    responses = _race([_put(a, "snack", True, 0) for a in actors])
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 412, 412, 412], [r.text for r in responses]
    assert len(meal_rows(owner, meal_world.alfa)) == 1


def test_the_daily_cap_is_atomic_for_presence_changes(
    meal_world: World, login: Login, owner: Owner
) -> None:
    start = local_day_start_utc(T0, "Europe/Rome")
    seed_tracked(owner, meal_world.alfa.id, DAILY_LIMIT - 2, start)
    actors = [login(meal_world.alfa.who("planner")) for _ in range(5)]
    meals = ["breakfast", "snack", "lunch", "dinner", "other"]
    responses = _race(
        [
            _put(a, m, m in {"breakfast", "snack", "other"}, 0)
            for a, m in zip(actors, meals, strict=True)
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 200, 429, 429, 429], [
        r.text for r in responses
    ]
    assert tracked_count(owner, meal_world.alfa.id) == DAILY_LIMIT
    assert len(event_rows(owner)) == 2
    assert len(meal_rows(owner, meal_world.alfa)) == 2, "le richieste respinte non lasciano righe"
