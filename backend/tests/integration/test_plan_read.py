"""Leggere il piano: `GET /api/v1/plan?from=&to=` (SL-06a).

US-008: AC-008.1 (giorni da lunedì a domenica nel fuso della famiglia, pasti di default, oggi),
AC-008.3 (un pasto aggiunto a un solo giorno), AC-008.4 (un pasto di default tolto da un solo
giorno), AC-008.5 (intervallo scelto, e oltre 62 giorni rifiutato con l'indicazione del limite).
SR-060 (intervallo <= 62 giorni), SR-008 (famiglia dalla sessione), AC-003.3 (nessun pasto di
default: stato vuoto), AC-052.7 (due «Altro pasto» nello stesso giorno), 05-data §7.1.

Contratto (piano §4.2, §4.3): `PlanView = {from, to, today, timezone, days: [{date, meals:
[MealView]}], refs: {dishes, courses}}`; `MealView` ha `date`, `mealType`, `slot`, `name`,
`present`, `special`, `contentVersion`, `items`, `past`. `422 range_too_large {maxDays: 62}`,
`422 validation` con `errors[].code` in {`range_order`, `date_invalid`}.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pytest

from support.dishes import Actor, Who, World, error_fields, make_dish
from support.meals import (
    MAX_DAYS,
    MONDAY,
    PLAN,
    SUNDAY,
    T0,
    TODAY,
    add_item,
    days_of,
    iso,
    make_meal,
    meals_by_day,
    plan_query,
    set_defaults,
    set_frozen_through,
    set_timezone,
    week,
)
from support.owner import Owner

pytestmark = pytest.mark.integration
Login = Callable[[Who], Actor]


@pytest.fixture
def planner(meal_world: World, login: Login) -> Actor:
    return login(meal_world.alfa.who("planner"))


# --- AC-008.1: la settimana corrente, da lunedì, nel fuso della famiglia --------------------------


def test_ac_008_1_the_default_view_is_the_current_week_monday_to_sunday_with_default_meals(
    meal_world: World, planner: Actor
) -> None:
    response = planner.get(PLAN)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["from"], body["to"]) == (iso(MONDAY), iso(SUNDAY))
    assert body["today"] == iso(TODAY)
    assert body["timezone"] == "Europe/Rome"
    assert [d["date"] for d in body["days"]] == [iso(d) for d in week()]
    for day in body["days"]:
        assert [(m["mealType"], m["slot"]) for m in day["meals"]] == [("lunch", 0), ("dinner", 0)]
        for meal in day["meals"]:
            assert meal["date"] == day["date"]
            assert meal["present"] is True
            assert meal["items"] == []
            assert meal["contentVersion"] == 0, "pasto di default mai scritto: versione 0"
            assert meal["special"] is None


def test_ac_008_1_meals_of_a_day_come_in_the_order_of_the_day_not_of_insertion(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    set_defaults(owner, meal_world.alfa, ("dinner", "breakfast", "snack", "lunch", "other"))
    got = meals_by_day(planner.get(PLAN))
    expected = [("breakfast", 0), ("lunch", 0), ("snack", 0), ("dinner", 0), ("other", 0)]
    assert all(meals == expected for meals in got.values()), got


def test_ac_008_1_past_days_are_flagged_and_today_and_the_future_are_not(
    meal_world: World, planner: Actor
) -> None:
    flags = {d["date"]: {m["past"] for m in d["meals"]} for d in planner.get(PLAN).json()["days"]}
    assert flags[iso(date(2026, 10, 22))] == {True}
    assert flags[iso(TODAY)] == {False}, "oggi non è passato"
    assert flags[iso(date(2026, 10, 24))] == {False}


def test_ac_008_1_the_week_starts_on_monday_for_every_day_of_the_week(
    meal_world: World, planner: Actor, frozen_now: Callable[[datetime], None]
) -> None:
    """Ogni giorno della settimana dà lo stesso lunedì (nessun errore di «uno» ai bordi)."""
    for offset in range(7):
        now = T0 + timedelta(days=offset)  # da venerdì 23 a giovedì 29, a mezzogiorno
        frozen_now(now)
        local = now.astimezone(ZoneInfo("Europe/Rome")).date()
        monday = local - timedelta(days=local.weekday())
        body = planner.get(PLAN).json()
        assert (body["from"], body["to"]) == (iso(monday), iso(monday + timedelta(days=6))), offset
        assert body["today"] == iso(local)


def test_the_week_follows_the_family_timezone_not_utc_when_now_utc_is_shifted(
    meal_world: World, planner: Actor, owner: Owner, frozen_now: Callable[[datetime], None]
) -> None:
    """Domenica 2026-10-25 23:30 UTC è già lunedì 26 a Roma (fine dell'ora legale, UTC+1)."""
    frozen_now(datetime(2026, 10, 25, 23, 30, tzinfo=UTC))
    body = planner.get(PLAN).json()
    assert body["today"] == "2026-10-26"
    assert (body["from"], body["to"]) == ("2026-10-26", "2026-11-01")


def test_the_week_follows_the_family_timezone_in_the_other_direction(
    meal_world: World, planner: Actor, owner: Owner, frozen_now: Callable[[datetime], None]
) -> None:
    """Lunedì 2026-10-26 01:30 UTC è ancora domenica 25 a New York (UTC-4 -> UTC-5 il 1 nov)."""
    set_timezone(owner, meal_world.alfa, "America/New_York")
    frozen_now(datetime(2026, 10, 26, 1, 30, tzinfo=UTC))
    body = planner.get(PLAN).json()
    assert body["timezone"] == "America/New_York"
    assert body["today"] == "2026-10-25"
    assert (body["from"], body["to"]) == (iso(MONDAY), iso(SUNDAY))


def test_a_week_with_a_daylight_saving_change_still_has_seven_days(
    meal_world: World, planner: Actor
) -> None:
    got = days_of(planner.get(plan_query("2026-10-24", "2026-10-26")))
    assert [d["date"] for d in got] == ["2026-10-24", "2026-10-25", "2026-10-26"]


# --- AC-008.5: intervallo scelto e limite di 62 giorni (SR-060) -----------------------------------


def test_ac_008_5_a_range_from_the_1st_to_the_10th_shows_those_ten_days(
    meal_world: World, planner: Actor
) -> None:
    body = planner.get(plan_query("2026-11-01", "2026-11-10")).json()
    assert [d["date"] for d in body["days"]] == [f"2026-11-{n:02d}" for n in range(1, 11)]
    assert (body["from"], body["to"]) == ("2026-11-01", "2026-11-10")
    assert body["today"] == iso(TODAY), (
        "`today` è sempre quello della famiglia, non dell'intervallo"
    )


def test_a_single_day_range_is_accepted(meal_world: World, planner: Actor) -> None:
    got = days_of(planner.get(plan_query("2026-10-23", "2026-10-23")))
    assert [d["date"] for d in got] == ["2026-10-23"]


def test_sr_060_62_days_are_accepted(meal_world: World, planner: Actor) -> None:
    start = date(2026, 10, 1)
    got = days_of(planner.get(plan_query(start, start + timedelta(days=MAX_DAYS - 1))))
    assert len(got) == MAX_DAYS


@pytest.mark.parametrize("extra", [0, 1, 400])
def test_ac_008_5_and_sr_060_63_days_or_more_are_refused_with_the_limit(
    extra: int, meal_world: World, planner: Actor, owner: Owner
) -> None:
    start = date(2026, 10, 1)
    refused = planner.get(plan_query(start, start + timedelta(days=MAX_DAYS + extra)))
    assert refused.status_code == 422, refused.text
    problem = refused.json()
    assert problem["code"] == "range_too_large"
    assert problem["params"] == {"maxDays": MAX_DAYS}
    assert refused.headers["content-type"].startswith("application/problem+json")


def test_a_huge_range_is_refused_before_anything_is_computed(
    meal_world: World, planner: Actor
) -> None:
    refused = planner.get(plan_query("0001-01-01", "9999-12-31"))
    assert refused.status_code == 422
    assert refused.json()["code"] == "range_too_large"


def test_the_62_day_limit_counts_days_inclusive_across_a_leap_year_boundary(
    meal_world: World, planner: Actor
) -> None:
    ok = planner.get(plan_query("2027-12-31", "2028-02-29"))  # 61 giorni (2028 è bisestile)
    assert ok.status_code == 200
    assert len(ok.json()["days"]) == 61
    assert planner.get(plan_query("2028-01-01", "2028-03-03")).status_code == 422  # 63 giorni


def test_range_order_the_end_before_the_start_is_a_validation_error(
    meal_world: World, planner: Actor
) -> None:
    refused = planner.get(plan_query("2026-10-10", "2026-10-09"))
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["code"] == "validation"
    assert "range_order" in error_fields(refused).values()
    assert {e["field"] for e in body["errors"]} <= {"from", "to"}


@pytest.mark.parametrize(
    "bad",
    [
        "2026-02-30",
        "2026-13-01",
        "2026-00-10",
        "26-10-01",
        "2026-10-1",
        "20261001",
        "2026/10/01",
        "01-10-2026",
        "abc",
        "",
        "2026-10-01T00:00:00Z",
        "2026-10-01 ",
        "99999-01-01",
        "'; drop table app.meal; --",
        "%00",
    ],
)
@pytest.mark.parametrize("which", ["from", "to"])
def test_date_invalid_for_malformed_dates_and_never_a_server_error(
    which: str, bad: str, meal_world: World, planner: Actor, owner: Owner
) -> None:
    good = "2026-10-20"
    params = {"from": good, "to": "2026-10-22"} | {which: bad}
    refused = planner.get(PLAN + "?" + urlencode(params))
    assert refused.status_code == 422, (bad, refused.status_code, refused.text)
    assert refused.json()["code"] == "validation"
    assert "date_invalid" in error_fields(refused).values()
    assert owner.scalar("select count(*) from app.meal") == 0


def test_repeated_or_unknown_query_parameters_do_not_change_the_family_or_fail(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    make_meal(owner, meal_world.beta, date(2026, 10, 20), "lunch", name=None)
    extra = urlencode({"familyId": str(meal_world.beta.id), "family_id": str(meal_world.beta.id)})
    response = planner.get(PLAN + "?" + extra)
    assert response.status_code in {200, 422}, response.text
    if response.status_code == 200:
        assert response.json()["timezone"] == "Europe/Rome"


# --- AC-008.3 e AC-008.4: pasti aggiunti o tolti in un solo giorno -------------------------------


def test_ac_008_3_a_snack_added_to_one_day_appears_only_on_that_day(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    make_meal(owner, meal_world.alfa, date(2026, 10, 21), "snack", presence="added")
    got = meals_by_day(planner.get(PLAN))
    with_snack = [d for d, meals in got.items() if ("snack", 0) in meals]
    assert with_snack == ["2026-10-21"]
    assert got["2026-10-21"] == [("lunch", 0), ("snack", 0), ("dinner", 0)]


def test_ac_008_4_a_default_meal_removed_from_one_day_disappears_only_from_that_day(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    make_meal(owner, meal_world.alfa, date(2026, 10, 24), "dinner", presence="removed")
    got = meals_by_day(planner.get(PLAN))
    without_dinner = [d for d, meals in got.items() if ("dinner", 0) not in meals]
    assert without_dinner == ["2026-10-24"]
    assert got["2026-10-24"] == [("lunch", 0)]


def test_an_inherit_row_of_a_default_type_is_shown_and_of_a_non_default_type_is_hidden(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    make_meal(owner, meal_world.alfa, date(2026, 10, 24), "lunch", presence="inherit")
    make_meal(owner, meal_world.alfa, date(2026, 10, 24), "snack", presence="inherit")
    assert meals_by_day(planner.get(plan_query("2026-10-24", "2026-10-24"))) == {
        "2026-10-24": [("lunch", 0), ("dinner", 0)]
    }


def test_frozen_days_show_only_the_added_rows_not_the_defaults(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    """05-data §7.1: fino a `frozen_through` contano solo le righe `added`."""
    set_frozen_through(owner, meal_world.alfa, date(2026, 10, 21))
    make_meal(owner, meal_world.alfa, date(2026, 10, 20), "lunch", presence="added")
    make_meal(owner, meal_world.alfa, date(2026, 10, 21), "dinner", presence="removed")
    got = meals_by_day(planner.get(plan_query("2026-10-19", "2026-10-23")))
    assert got["2026-10-19"] == []
    assert got["2026-10-20"] == [("lunch", 0)]
    assert got["2026-10-21"] == []
    assert got["2026-10-22"] == [("lunch", 0), ("dinner", 0)], "il giorno dopo il congelamento"


def test_ac_052_7_two_other_meals_of_the_same_day_are_both_listed_in_slot_order(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    day = date(2026, 10, 24)
    make_meal(owner, meal_world.alfa, day, "other", 1, presence="added", name="Dopocena")
    make_meal(owner, meal_world.alfa, day, "other", 0, presence="added", name="Aperitivo")
    meals = days_of(planner.get(plan_query(day, day)))[0]["meals"]
    others = [(m["slot"], m["name"]) for m in meals if m["mealType"] == "other"]
    assert others == [(0, "Aperitivo"), (1, "Dopocena")]
    assert [m["mealType"] for m in meals] == ["lunch", "dinner", "other", "other"]


def test_other_meal_with_slot_above_zero_exists_only_when_added(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    day = date(2026, 10, 24)
    make_meal(owner, meal_world.alfa, day, "other", 2, presence="removed", name="Tolto")
    assert ("other", 2) not in meals_by_day(planner.get(plan_query(day, day)))[iso(day)]


# --- AC-003.3: nessun pasto di default -> stato vuoto ---------------------------------------------


def test_an_empty_plan_has_seven_days_and_no_meals_when_the_family_has_no_default_meals(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    set_defaults(owner, meal_world.alfa, ())
    response = planner.get(PLAN)
    assert response.status_code == 200
    body = response.json()
    assert [d["date"] for d in body["days"]] == [iso(d) for d in week()]
    assert all(d["meals"] == [] for d in body["days"])
    assert body["refs"]["dishes"] == {}


def test_an_added_meal_is_still_shown_when_the_family_has_no_default_meals(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    set_defaults(owner, meal_world.alfa, ())
    make_meal(owner, meal_world.alfa, date(2026, 10, 22), "dinner", presence="added")
    got = meals_by_day(planner.get(PLAN))
    assert [d for d, meals in got.items() if meals] == ["2026-10-22"]


# --- contenuto dei pasti e riferimenti (lettura) --------------------------------------------------


def test_meal_content_is_read_with_items_in_position_order_and_refs_to_dishes_and_courses(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    ceci = make_dish(owner, fam, "Pasta e ceci", courses=("first",), status="tested")
    frittata = make_dish(owner, fam, "Frittata di zucchine", courses=("second",))
    day = date(2026, 10, 20)
    make_meal(owner, fam, day, "dinner", content_version=3, modified_by="admin", special=None)
    add_item(owner, fam, day, "dinner", dish=frittata, course="second", position=1)
    add_item(owner, fam, day, "dinner", dish=ceci, course="first", position=0)
    add_item(owner, fam, day, "dinner", text="Pane e olio", position=2)
    meal = next(
        m
        for m in days_of(planner.get(plan_query(day, day)))[0]["meals"]
        if m["mealType"] == "dinner"
    )
    assert meal["contentVersion"] == 3
    assert meal["contentModifiedBy"] == str(fam.who("admin").person), "ID, mai il nome"
    assert [(i["position"], i["kind"]) for i in meal["items"]] == [
        (0, "dish"),
        (1, "dish"),
        (2, "free_text"),
    ]
    assert meal["items"][0]["dishId"] == str(ceci)
    assert meal["items"][0]["courseId"] == str(fam.courses["first"])
    assert meal["items"][0]["notCooked"] is False
    assert meal["items"][2]["freeText"] == "Pane e olio"
    assert "freeText" not in meal["items"][0], "chiavi senza valore omesse, non null"
    assert "dishId" not in meal["items"][2]
    assert "courseId" not in meal["items"][2]
    refs = planner.get(plan_query(day, day)).json()["refs"]
    assert refs["dishes"][str(ceci)] == {
        "name": "Pasta e ceci",
        "status": "tested",
        "archived": False,
    }
    assert refs["dishes"][str(frittata)]["name"] == "Frittata di zucchine"
    assert str(fam.courses["first"]) in refs["courses"]
    assert refs["courses"][str(fam.courses["first"])]["baseCode"] == "first"


def test_a_removed_meal_does_not_show_its_content_in_the_plan(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    """Il contenuto resta nella riga, ma «non conta perché il pasto non c'è» (05-data §4.2)."""
    fam = meal_world.alfa
    day = date(2026, 10, 21)
    make_meal(owner, fam, day, "dinner", presence="removed", content_version=2)
    add_item(owner, fam, day, "dinner", text="CANARY-ALFA-RIMOSSO")
    response = planner.get(plan_query(day, day))
    assert "CANARY-ALFA-RIMOSSO" not in response.text
    assert ("dinner", 0) not in meals_by_day(response)[iso(day)]


def test_special_state_and_name_are_part_of_the_meal_view(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    day = date(2026, 10, 22)
    make_meal(owner, meal_world.alfa, day, "lunch", special="restaurant", content_version=1)
    make_meal(owner, meal_world.alfa, day, "other", 0, name="Aperitivo", content_version=1)
    meals = {m["mealType"]: m for m in days_of(planner.get(plan_query(day, day)))[0]["meals"]}
    assert meals["lunch"]["special"] == "restaurant"
    assert meals["other"]["name"] == "Aperitivo"
    assert meals["dinner"]["special"] is None


def test_the_plan_of_62_days_with_content_answers_in_one_request(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    """NFR-002 (misura vera nel notturno): qui solo che 62 giorni pieni siano corretti."""
    fam = meal_world.alfa
    dish = make_dish(owner, fam, "Pasta e ceci")
    start = date(2026, 10, 19)
    for n in range(0, 62, 6):
        day = start + timedelta(days=n)
        make_meal(owner, fam, day, "lunch", content_version=1)
        add_item(owner, fam, day, "lunch", dish=dish)
    response = planner.get(plan_query(start, start + timedelta(days=61)))
    assert response.status_code == 200
    assert len(response.json()["days"]) == 62
    assert sum(len(m["items"]) for d in response.json()["days"] for m in d["meals"]) == 11


# --- ruoli e accesso ------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["admin", "planner", "member"])
def test_every_family_role_can_read_the_plan(role: str, meal_world: World, login: Login) -> None:
    actor = login(meal_world.alfa.who(role))
    assert actor.get(PLAN).status_code == 200


def test_the_plan_is_read_only_there_is_no_write_method_on_it(
    meal_world: World, planner: Actor
) -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = planner.browser.request(method, PLAN, json={}, csrf=planner.csrf)
        assert response.status_code in {404, 405}, (method, response.status_code)
