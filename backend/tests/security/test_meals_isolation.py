"""Isolamento tra famiglie del piano (SL-06a): SR-008, THR-020, THR-105, AC-008.7.

Il pasto si indirizza per (data, tipo, slot) e la famiglia viene SEMPRE dalla sessione: nessun
identificativo di una risorsa altrui compare nel percorso, quindi la richiesta di un account di
Alfa per «lo stesso pasto» di Beta riguarda il pasto di Alfa, mai quello di Beta. Si prova che i
dati di Beta non attraversano il confine in nessuna direzione, né in lettura né in scrittura, e che
nessun parametro del client sceglie la famiglia. Il piano chiede `404` ed evento
`access.cross_family` per «pasto di altra famiglia» (AC-008.7): senza identificativi nel percorso
non c'è una rotta che possa produrlo (rapporto, N-2); qui si verifica ciò che è verificabile.
"""

from collections.abc import Callable
from datetime import date

import psycopg
import pytest

from support.accounts import security_events
from support.dishes import Actor, Who, World, event_rows, make_dish
from support.meals import (
    PLAN,
    add_item,
    iso,
    make_meal,
    meal_row,
    meal_url,
    meals_by_day,
    plan_query,
    planning_state,
    presence_url,
    set_defaults,
)
from support.owner import Owner
from support.tracks import tracked_count

pytestmark = [pytest.mark.sec, pytest.mark.integration]
Login = Callable[[Who], Actor]
DAY = date(2026, 10, 24)


def _victim_content(owner: Owner, world: World, which: str) -> str:
    fam = world.fam(which)
    dish = make_dish(owner, fam, f"{fam.canary}-DISH")
    make_meal(owner, fam, DAY, "dinner", content_version=4, modified_by="admin",
              guests=2, guests_note=f"{fam.canary}-OSPITI")  # fmt: skip
    add_item(owner, fam, DAY, "dinner", dish=dish, position=0)
    add_item(owner, fam, DAY, "dinner", text=f"{fam.canary}-LIBERA", position=1)
    make_meal(owner, fam, DAY, "other", 1, name=f"{fam.canary}-NOME", content_version=1)
    return fam.canary


@pytest.mark.parametrize(("attacker", "victim"), [("alfa", "beta"), ("beta", "alfa")])
def test_the_plan_and_the_meals_of_another_family_never_appear(
    attacker: str, victim: str, meal_world: World, login: Login, owner: Owner
) -> None:
    canary = _victim_content(owner, meal_world, victim)
    v = meal_world.fam(victim)
    actor = login(meal_world.fam(attacker).who("planner"))
    set_defaults(owner, v, ("breakfast", "lunch", "snack", "dinner"))
    for response in (
        actor.get(PLAN),
        actor.get(plan_query("2026-10-19", "2026-12-19")),
        actor.get(meal_url(DAY, "dinner")),
        actor.get(meal_url(DAY, "other", 1)),
    ):
        assert response.status_code == 200, response.text
        assert canary not in response.text
        assert str(v.id) not in response.text
        assert "CANARY" not in response.text.replace(meal_world.fam(attacker).canary, "")
    assert meals_by_day(actor.get(PLAN))[iso(DAY)] == [("lunch", 0), ("dinner", 0)]
    mine = actor.get(meal_url(DAY, "dinner")).json()
    assert mine["items"] == []
    assert mine["contentVersion"] == 0
    assert actor.get(plan_query(DAY, DAY)).json()["refs"]["dishes"] == {}


@pytest.mark.parametrize(("attacker", "victim"), [("alfa", "beta"), ("beta", "alfa")])
def test_changing_the_same_meal_key_changes_only_the_own_family(
    attacker: str, victim: str, meal_world: World, login: Login, owner: Owner
) -> None:
    _victim_content(owner, meal_world, victim)
    a, v = meal_world.fam(attacker), meal_world.fam(victim)
    actor = login(a.who("planner"))
    before_victim = planning_state(owner, v)
    victim_events = len(event_rows(owner))
    # La versione del pasto della vittima è 4: se la richiesta lo riguardasse, `If-Match: "4"`
    # riuscirebbe e `"0"` darebbe 412. Vale il contrario: è il pasto dell'attore (mai scritto).
    stale = actor.put(presence_url(DAY, "dinner"), {"present": False}, if_match=4)
    assert stale.status_code == 412, stale.text
    assert stale.json()["params"]["current"]["contentVersion"] == 0
    assert v.canary not in stale.text
    done = actor.put(presence_url(DAY, "dinner"), {"present": False}, if_match=0)
    assert done.status_code == 200, done.text
    assert planning_state(owner, v) == before_victim, "la famiglia della vittima non cambia"
    assert meal_row(owner, a, DAY, "dinner") is not None
    events = event_rows(owner)[victim_events:]
    assert [e["family_id"] for e in events] == [a.id]
    assert tracked_count(owner, v.id) == 0
    assert tracked_count(owner, a.id) == 1


def test_the_only_security_events_of_these_requests_are_none(
    meal_world: World, login: Login, owner: Owner
) -> None:
    """Nessun identificativo estraneo: nessun accesso negato, nessun evento cross_family."""
    _victim_content(owner, meal_world, "beta")
    actor = login(meal_world.alfa.who("planner"))
    assert actor.get(PLAN).status_code == 200
    assert actor.get(meal_url(DAY, "dinner")).status_code == 200
    assert security_events(owner, "access.%") == []


@pytest.mark.parametrize("attacker_role", ["admin", "planner", "member"])
def test_no_client_parameter_chooses_the_family(
    attacker_role: str, meal_world: World, login: Login, owner: Owner
) -> None:
    beta = meal_world.beta
    _victim_content(owner, meal_world, "beta")
    actor = login(meal_world.alfa.who(attacker_role))
    headers = {
        "X-Family-Id": str(beta.id),
        "X-Forwarded-Family": str(beta.id),
        "Family-Id": str(beta.id),
    }
    got = actor.browser.request("GET", meal_url(DAY, "dinner"), headers=headers)
    assert got.status_code == 200
    assert beta.canary not in got.text
    assert got.json()["contentVersion"] == 0
    q = f"?familyId={beta.id}&family_id={beta.id}&family={beta.id}"
    got = actor.get(meal_url(DAY, "dinner") + q)
    assert got.status_code in {200, 422}
    assert beta.canary not in got.text


def test_the_body_cannot_carry_a_family_and_the_write_is_refused_whole(
    meal_world: World, login: Login, owner: Owner
) -> None:
    beta = meal_world.beta
    actor = login(meal_world.alfa.who("planner"))
    state_beta = planning_state(owner, beta)
    state_alfa = planning_state(owner, meal_world.alfa)
    refused = actor.put(
        presence_url(DAY, "dinner"), {"present": False, "familyId": str(beta.id)}, if_match=0
    )
    assert refused.status_code == 422
    assert planning_state(owner, beta) == state_beta
    assert planning_state(owner, meal_world.alfa) == state_alfa
    assert event_rows(owner) == []


def test_the_row_level_security_hides_the_other_family_even_to_the_application_role(
    meal_world: World, owner: Owner, connect_app: Callable[..., psycopg.Connection]
) -> None:
    """Rete sotto l'applicazione: con il contesto di Alfa `menu_app` non vede i pasti di Beta."""
    _victim_content(owner, meal_world, "beta")
    set_defaults(owner, meal_world.beta, ("breakfast", "lunch", "snack", "dinner"))
    make_meal(owner, meal_world.alfa, DAY, "lunch")
    with connect_app() as conn:
        conn.autocommit = False
        conn.execute("select set_config('app.family_id', %s, true)", (str(meal_world.alfa.id),))
        families = {r[0] for r in conn.execute("select family_id from app.meal")}
        items = conn.execute("select count(*) from app.meal_item").fetchone()
        types = {
            (r[0], r[1])
            for r in conn.execute(
                "select meal_type, meal_slot from app.effective_meals(%s, %s)", (DAY, DAY)
            )
        }
    assert families == {meal_world.alfa.id}
    assert items == (0,)
    assert types == {("lunch", 0), ("dinner", 0)}, "i default e le righe di Beta non compaiono"
