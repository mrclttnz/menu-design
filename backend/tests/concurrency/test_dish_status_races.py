"""Concorrenza del cambio di stato e del tetto giornaliero (SL-05; 08 §9, ADR-0008, ADR-0012).

Invarianti (non si asserisce quale richiesta vince, solo i conteggi):
- due cambi di stato con lo stesso `If-Match`: ESATTAMENTE una `200`, l'altra `412`; versione +1 ed
  ESATTAMENTE un evento (nessun evento per chi perde, AC-049.4);
- N cambi di stato su piatti diversi insieme: N eventi e il contatore `tracked_family` a N
  esatti, senza aggiornamenti persi (08 §7.4, «il conteggio finale è esattamente N»);
- famiglia a `limite - k` e `k + m` richieste insieme: esattamente `k` riescono e `m` danno `429`
  (il tetto è atomico: nessuna scrittura oltre il limite per effetto della corsa).
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import Response

from support.accounts import security_events
from support.dishes import Actor, Who, World, dish_row, event_rows, make_dish
from support.owner import Owner
from support.tracks import (
    DAILY_LIMIT,
    local_day_start_utc,
    seed_tracked,
    set_timezone,
    tracked_count,
)

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]
Login = Callable[[Who], Actor]
T0 = datetime(2026, 10, 23, 12, 7, 30, tzinfo=UTC)


def _flip(
    actor: Actor, dish: UUID, status: str = "tested", version: int = 1
) -> Callable[[], Response]:
    return lambda: actor.post(f"/api/v1/dishes/{dish}/status", {"status": status}, if_match=version)


def _race(calls: list[Callable[[], Response]]) -> list[Response]:
    barrier = threading.Barrier(len(calls))

    def go(call: Callable[[], Response]) -> Response:
        barrier.wait(timeout=20)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return [f.result(timeout=60) for f in [pool.submit(go, c) for c in calls]]


def test_two_status_changes_with_the_same_if_match_one_wins_and_one_event_is_written(
    world: World, login: Login, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    planner, admin = login(world.alfa.who("planner")), login(world.alfa.who("admin"))
    responses = _race([_flip(planner, dish), _flip(admin, dish)])
    assert sorted(r.status_code for r in responses) == [200, 412], [r.text for r in responses]
    row = dish_row(owner, dish)
    assert row is not None
    assert (row[1], row[4]) == ("tested", 2)
    (event,) = event_rows(owner)
    assert event["actor_role"] in {"planner", "admin"}
    assert tracked_count(owner, world.alfa.id) == 1, "il perdente non consuma il tetto"


def test_two_opposite_status_changes_cannot_both_apply_to_the_same_version(
    world: World, login: Login, owner: Owner
) -> None:
    """Uno verso «collaudato» e uno verso «da provare» sulla stessa versione: una sola vince."""
    dish = make_dish(owner, world.alfa, "Pasta e ceci", status="to_try")
    planner, admin = login(world.alfa.who("planner")), login(world.alfa.who("admin"))
    responses = _race([_flip(planner, dish, "tested"), _flip(admin, dish, "to_try")])
    assert sorted(r.status_code for r in responses) == [200, 412], [r.text for r in responses]
    row = dish_row(owner, dish)
    assert row is not None
    assert row[4] == 2
    assert len(event_rows(owner)) == 1, "un evento per ogni versione avanzata, mai di più"


def test_eight_status_changes_on_different_dishes_leave_exactly_eight_events_and_count_eight(
    world: World, login: Login, owner: Owner
) -> None:
    dishes = [make_dish(owner, world.alfa, f"Piatto {n}") for n in range(8)]
    actors = [login(world.alfa.who("planner" if n % 2 else "admin")) for n in range(8)]
    responses = _race([_flip(a, d) for a, d in zip(actors, dishes, strict=True)])
    assert [r.status_code for r in responses] == [200] * 8, [r.text for r in responses]
    assert len(event_rows(owner)) == 8
    assert {e["dish_id"] for e in event_rows(owner)} == set(dishes)
    assert tracked_count(owner, world.alfa.id) == 8, "nessun aggiornamento perso del contatore"


def test_the_daily_cap_is_atomic_under_a_race(
    world: World, login: Login, frozen_now: Callable[[datetime], None], owner: Owner
) -> None:
    """Tetto a `limite - 3` e 8 richieste insieme: esattamente 3 riescono e 5 danno 429."""
    frozen_now(T0)
    set_timezone(owner, world.alfa, "Europe/Rome")
    seed_tracked(owner, world.alfa.id, DAILY_LIMIT - 3, local_day_start_utc(T0, "Europe/Rome"))
    dishes = [make_dish(owner, world.alfa, f"Piatto {n}") for n in range(8)]
    actors = [login(world.alfa.who("planner" if n % 2 else "admin")) for n in range(8)]
    responses = _race([_flip(a, d) for a, d in zip(actors, dishes, strict=True)])
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 200, 200, 429, 429, 429, 429, 429], codes
    assert len(event_rows(owner)) == 3, "esattamente tre eventi: nessuna scrittura oltre il tetto"
    changed = [d for d in dishes if (dish_row(owner, d) or ("", ""))[1] == "tested"]
    assert len(changed) == 3


def test_more_writes_than_pool_connections_at_the_cap_all_get_429_and_other_families_are_served(
    world: World, login: Login, frozen_now: Callable[[datetime], None], owner: Owner
) -> None:
    """SEC-SL05-001, CR-SL05-002: a 429 non tiene mai due connessioni del pool (10 per istanza).

    Famiglia al tetto e 16 scritture insieme (più del pool): tutte `429` rapidamente, un'altra
    famiglia legge ancora (`200`) mentre la corsa è in corso, e l'allarme è uno solo.
    """
    frozen_now(T0)
    set_timezone(owner, world.alfa, "Europe/Rome")
    seed_tracked(owner, world.alfa.id, DAILY_LIMIT, local_day_start_utc(T0, "Europe/Rome"))
    count = 16
    dishes = [make_dish(owner, world.alfa, f"Piatto {n}") for n in range(count)]
    actors = [login(world.alfa.who("planner" if n % 2 else "admin")) for n in range(count)]
    beta = login(world.beta.who("planner"))
    calls = [_flip(a, d) for a, d in zip(actors, dishes, strict=True)]
    calls.append(lambda: beta.get("/api/v1/dishes"))
    responses = _race(calls)
    assert [r.status_code for r in responses[:count]] == [429] * count, [
        (r.status_code, r.text) for r in responses[:count]
    ]
    assert responses[count].status_code == 200, "un'altra famiglia non resta in coda"
    assert len(security_events(owner, "rate_limit.%")) == 1, "un solo allarme per finestra"
    assert event_rows(owner) == []
