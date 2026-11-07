"""Leggere un pasto: `GET /api/v1/meals/{date}/{mealType}/{slot}` (SL-06a).

US-008 AC-008.7 (lettura, autorizzazione), SR-008 (famiglia dalla sessione), ADR-0008/ADR-0009
(`ETag` = versione del contenuto, slot sempre nel percorso, `404` per uno slot non valido per il
tipo), 05-data §4.2 (`0` per un'unità mai scritta).
"""

from collections.abc import Callable
from datetime import date

import pytest

from support.dishes import Actor, Who, World, etag, make_dish
from support.meals import (
    TODAY,
    YESTERDAY,
    add_item,
    iso,
    make_meal,
    meal_rows,
    meal_url,
)
from support.owner import Owner

pytestmark = pytest.mark.integration
Login = Callable[[Who], Actor]


@pytest.fixture
def planner(meal_world: World, login: Login) -> Actor:
    return login(meal_world.alfa.who("planner"))


def test_a_default_meal_never_written_has_version_zero_and_a_zero_etag(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    response = planner.get(meal_url(TODAY, "dinner", 0))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert etag(response) == '"0"'
    body = response.json()
    assert (body["date"], body["mealType"], body["slot"]) == (iso(TODAY), "dinner", 0)
    assert body["present"] is True
    assert body["contentVersion"] == 0
    assert body["items"] == []
    assert body["special"] is None
    assert body["name"] is None
    assert body["past"] is False
    assert meal_rows(owner, meal_world.alfa) == [], "una lettura non crea la riga"


def test_the_etag_is_the_content_version_of_the_meal(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    make_meal(owner, meal_world.alfa, TODAY, "lunch", content_version=7, modified_by="admin")
    response = planner.get(meal_url(TODAY, "lunch"))
    assert etag(response) == '"7"'
    assert response.json()["contentVersion"] == 7
    assert response.json()["contentModifiedBy"] == str(meal_world.alfa.who("admin").person)


def test_a_meal_that_is_not_a_default_and_has_no_row_is_absent_but_addable_at_version_zero(
    meal_world: World, planner: Actor
) -> None:
    response = planner.get(meal_url(TODAY, "snack"))
    assert response.status_code == 200, response.text
    assert response.json()["present"] is False
    assert etag(response) == '"0"'


def test_a_removed_meal_is_absent_and_keeps_its_version(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    make_meal(owner, meal_world.alfa, TODAY, "dinner", presence="removed", content_version=2)
    response = planner.get(meal_url(TODAY, "dinner"))
    assert response.status_code == 200
    assert response.json()["present"] is False
    assert etag(response) == '"2"'


def test_a_removed_meal_never_shows_the_content_left_in_its_row(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    """Gap found in SL-06a mode C (mutant M11b): the plan view had this check, the meal read not.

    A removed meal keeps items, special state and name in the row (05-data §4.2), but «non conta
    perché il pasto non c'è»: GET of the single meal must show none of it.
    """
    fam = meal_world.alfa
    dish = make_dish(owner, fam, "Pasta e ceci")
    make_meal(owner, fam, TODAY, "dinner", presence="removed", special="restaurant",
              content_version=3)  # fmt: skip
    add_item(owner, fam, TODAY, "dinner", dish=dish, position=0)
    add_item(owner, fam, TODAY, "dinner", text="CANARY-ALFA-TOLTO", position=1)
    make_meal(owner, fam, TODAY, "other", 2, presence="removed", name="CANARY-NOME-TOLTO")
    for url in (meal_url(TODAY, "dinner"), meal_url(TODAY, "other", 2)):
        response = planner.get(url)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["present"] is False
        assert body["items"] == []
        assert body["special"] is None
        assert body["name"] is None
        assert "CANARY" not in response.text
        assert str(dish) not in response.text


def test_a_meal_with_items_returns_them_in_position_order(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    dish = make_dish(owner, fam, "Pasta e ceci")
    make_meal(owner, fam, TODAY, "lunch", content_version=2)
    add_item(owner, fam, TODAY, "lunch", text="Pane", position=1)
    add_item(owner, fam, TODAY, "lunch", dish=dish, course="first", position=0)
    items = planner.get(meal_url(TODAY, "lunch")).json()["items"]
    assert [i["kind"] for i in items] == ["dish", "free_text"]
    assert items[0]["dishId"] == str(dish)


def test_a_past_day_is_flagged_past(meal_world: World, planner: Actor) -> None:
    assert planner.get(meal_url(YESTERDAY, "lunch")).json()["past"] is True


@pytest.mark.parametrize(("meal_type", "slot"), [("lunch", 1), ("dinner", 4), ("breakfast", 2)])
def test_a_slot_above_zero_is_404_for_the_standard_types(
    meal_type: str, slot: int, meal_world: World, planner: Actor
) -> None:
    response = planner.get(meal_url(TODAY, meal_type, slot))
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize("slot", [0, 1, 2, 3, 4])
def test_other_meals_have_five_valid_slots(slot: int, meal_world: World, planner: Actor) -> None:
    assert planner.get(meal_url(TODAY, "other", slot)).status_code == 200


@pytest.mark.parametrize("slot", [5, 9, -1, 100, 32768, 99999999999])
def test_other_meals_with_a_slot_outside_0_to_4_are_404_or_422_never_500(
    slot: int, meal_world: World, planner: Actor
) -> None:
    response = planner.get(meal_url(TODAY, "other", slot))
    assert response.status_code in {404, 422}, (slot, response.status_code, response.text)


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/meals/{TODAY}/brunch/0",
        f"/api/v1/meals/{TODAY}/LUNCH/0",
        f"/api/v1/meals/{TODAY}/lunch/x",
        f"/api/v1/meals/{TODAY}/lunch/",
        "/api/v1/meals/2026-02-30/lunch/0",
        "/api/v1/meals/not-a-date/lunch/0",
        "/api/v1/meals/2026-10-23/%00/0",
        "/api/v1/meals/2026-10-23/lunch/0%00",
        f"/api/v1/meals/{TODAY}/cena/0",
        "/api/v1/meals/0000-01-01/lunch/0",
        "/api/v1/meals/10000-01-01/lunch/0",
    ],
)
def test_malformed_keys_are_refused_without_a_server_error_or_a_write(
    path: str, meal_world: World, planner: Actor, owner: Owner
) -> None:
    response = planner.get(path)
    assert response.status_code in {404, 422}, (path, response.status_code, response.text)
    assert meal_rows(owner, meal_world.alfa) == []


def test_there_is_no_slotless_meal_path(meal_world: World, planner: Actor) -> None:
    """ADR-0009: lo slot c'è sempre nel percorso."""
    assert planner.get(f"/api/v1/meals/{TODAY}/lunch").status_code in {404, 405}


@pytest.mark.parametrize("role", ["admin", "planner", "member"])
def test_every_family_role_can_read_a_meal(role: str, meal_world: World, login: Login) -> None:
    assert login(meal_world.alfa.who(role)).get(meal_url(TODAY)).status_code == 200


def test_a_far_future_day_is_a_valid_empty_meal(meal_world: World, planner: Actor) -> None:
    far = date(2030, 1, 7)
    response = planner.get(meal_url(far, "dinner"))
    assert response.status_code == 200, response.text
    assert response.json()["present"] is True, "dinner è un pasto di default"
    assert etag(response) == '"0"'
