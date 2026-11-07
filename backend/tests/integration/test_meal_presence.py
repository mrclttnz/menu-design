"""Aggiungere o togliere un pasto: `PUT /api/v1/meals/{date}/{mealType}/{slot}/presence`.

SL-06a. US-008: AC-008.3 (la Merenda aggiunta compare solo in quel giorno), AC-008.4 (un pasto di
default tolto sparisce solo da quel giorno). 05-data §4.2 (rimozione e nuova aggiunta: la riga si
riusa, il contenuto si svuota, le versioni crescono; la riga `inherit` nascosta si riaccende senza
svuotarla), ADR-0008 (`If-Match`, `412`, `428`, `422`), ADR-0012 / FR-061 (un evento `meal_content`
nella stessa transazione), SR-070 (la scrittura è tracciata: consuma il tetto giornaliero),
SR-024 (corpo `{present: boolean}` e nient'altro), AC-049.4 (un'operazione fallita non lascia
eventi). Il Membro riceve `403`: `tests/security/test_meals_access.py`.

Contratto assunto (piano §4.3): corpo `{present: boolean}`, `If-Match: "<contentVersion>"` (`0` per
un pasto mai scritto), risposta `200 MealView` con `ETag`. Evento: `unit_type='meal_content'`,
chiave (data, tipo, slot), `after = {"v": 1, "pr": <presence>, ...}` e `before` con il `pr` di
prima (`inherit` per un pasto di default senza riga).
"""

import contextlib
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from support.dishes import (
    Actor,
    Who,
    World,
    error_fields,
    etag,
    event_rows,
    event_text,
    make_dish,
)
from support.meals import (
    T0,
    TODAY,
    add_item,
    iso,
    item_rows,
    make_meal,
    meal_row,
    meal_rows,
    meals_by_day,
    plan_query,
    planning_state,
    presence_url,
    set_defaults,
)
from support.owner import Owner
from support.tracks import assert_tracks, local_day_start_utc, tracked_count

pytestmark = pytest.mark.integration
Login = Callable[[Who], Actor]
OP = "meal.presence.write"
DAY = date(2026, 10, 24)  # sabato, dopo `frozen_through`


@pytest.fixture
def planner(meal_world: World, login: Login) -> Actor:
    return login(meal_world.alfa.who("planner"))


def put(
    actor: Actor, meal_type: str, present: Any, version: Any, *, slot: int = 0, day: Any = DAY
) -> Any:
    return actor.put(presence_url(day, meal_type, slot), {"present": present}, if_match=version)


@contextlib.contextmanager
def events_not_insertable(owner: Owner) -> Iterator[None]:
    owner.execute("revoke insert on app.change_event from menu_app")
    try:
        yield
    finally:
        owner.execute("grant select, insert on app.change_event to menu_app")


# --- AC-008.4: togliere un pasto di default da un solo giorno -------------------------------------


@pytest.mark.tracks("meal.presence.write")
def test_ac_008_4_removing_a_default_meal_records_one_event_and_hides_it_only_that_day(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    done = assert_tracks(
        owner=owner,
        fam=fam,
        happy=lambda: put(planner, "dinner", False, 0),
        expected=[
            {
                "unit_type": "meal_content",
                "meal_date": DAY,
                "meal_type": "dinner",
                "meal_slot": 0,
                "actor_kind": "person",
                "actor_person_id": fam.who("planner").person,
                "actor_role": "planner",
                "occurred_at": T0,
                "subject_person_id": None,
                "dish_id": None,
            }
        ],
        failing=[
            ("412 versione vecchia", lambda: put(planner, "dinner", False, 9), 412),
            (
                "428 senza If-Match",
                lambda: planner.put(presence_url(DAY, "dinner"), {"present": False}),
                428,
            ),
            ("422 If-Match malformato", lambda: put(planner, "dinner", False, "abc"), 422),
            (
                "422 corpo vuoto",
                lambda: planner.put(presence_url(DAY, "dinner"), {}, if_match=0),
                422,
            ),
            ("422 present non booleano", lambda: put(planner, "dinner", "false", 0), 422),
            ("404 slot non valido", lambda: put(planner, "dinner", False, 0, slot=1), 404),
        ],
        window_start=local_day_start_utc(T0, "Europe/Rome"),
    )
    assert done.headers["cache-control"] == "no-store"
    assert etag(done) == '"1"'
    body = done.json()
    assert (body["date"], body["mealType"], body["slot"]) == (iso(DAY), "dinner", 0)
    assert body["present"] is False
    assert body["contentVersion"] == 1

    (event,) = event_rows(owner)
    assert event["op"] in {"set", "clear"}
    assert event["after"]["v"] == 1
    assert event["after"]["pr"] == "removed"
    assert event["before"]["pr"] == "inherit", "senza riga il pasto di default era «inherit»"

    row = meal_row(owner, fam, DAY, "dinner")
    assert row is not None
    assert (row["presence"], row["content_version"]) == ("removed", 1)
    assert row["content_modified_by"] == fam.who("planner").person

    got = meals_by_day(planner.get(plan_query()))
    assert [d for d, meals in got.items() if ("dinner", 0) not in meals] == [iso(DAY)]
    assert got[iso(DAY)] == [("lunch", 0)]


def test_the_meal_read_after_a_removal_is_absent_with_the_new_version(
    meal_world: World, planner: Actor
) -> None:
    assert put(planner, "lunch", False, 0).status_code == 200
    again = planner.get(presence_url(DAY, "lunch").removesuffix("/presence"))
    assert again.json()["present"] is False
    assert etag(again) == '"1"'


def test_removing_a_meal_keeps_its_content_in_the_row(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    dish = make_dish(owner, fam, "Pasta e ceci")
    make_meal(owner, fam, DAY, "dinner", content_version=2, guests=3, guests_version=1)
    add_item(owner, fam, DAY, "dinner", dish=dish)
    assert put(planner, "dinner", False, 2).status_code == 200
    assert len(item_rows(owner, fam)) == 1, "il contenuto resta nella riga (05-data §4.2)"
    row = meal_row(owner, fam, DAY, "dinner")
    assert row is not None
    assert (row["presence"], row["content_version"], row["guests_count"]) == ("removed", 3, 3)


# --- AC-008.3: aggiungere un pasto che non è di default a un solo giorno --------------------------


@pytest.mark.tracks("meal.presence.write")
def test_ac_008_3_adding_a_snack_creates_the_row_and_shows_it_only_that_day(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    done = assert_tracks(
        owner=owner,
        fam=fam,
        happy=lambda: put(planner, "snack", True, 0),
        expected=[
            {"unit_type": "meal_content", "meal_date": DAY, "meal_type": "snack", "meal_slot": 0}
        ],
        failing=[("412 versione vecchia", lambda: put(planner, "snack", True, 4), 412)],
    )
    assert done.json()["present"] is True
    assert done.json()["contentVersion"] == 1
    (event,) = event_rows(owner)
    assert event["after"]["pr"] == "added"
    assert (event["before"] or {}).get("pr", "removed") in {"removed", "inherit"}
    row = meal_row(owner, fam, DAY, "snack")
    assert row is not None
    assert (row["presence"], row["content_version"], row["guests_count"]) == ("added", 1, 0)
    got = meals_by_day(planner.get(plan_query()))
    assert [d for d, meals in got.items() if ("snack", 0) in meals] == [iso(DAY)]
    assert got[iso(DAY)] == [("lunch", 0), ("snack", 0), ("dinner", 0)]


def test_adding_an_other_meal_in_slot_two_creates_an_added_row_with_that_slot(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    """AC-052.7 a livello di API: lo slot è nel percorso e la riga nasce `added`."""
    done = put(planner, "other", True, 0, slot=2)
    assert done.status_code == 200, done.text
    assert (done.json()["mealType"], done.json()["slot"]) == ("other", 2)
    row = meal_row(owner, meal_world.alfa, DAY, "other", 2)
    assert row is not None
    assert row["presence"] == "added"
    assert meal_row(owner, meal_world.alfa, DAY, "other", 0) is None
    (event,) = event_rows(owner)
    assert (event["meal_type"], event["meal_slot"]) == ("other", 2)


def test_two_other_meals_of_the_same_day_can_be_added_and_removed_independently(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    assert put(planner, "other", True, 0, slot=0).status_code == 200
    assert put(planner, "other", True, 0, slot=1).status_code == 200
    assert put(planner, "other", False, 1, slot=0).status_code == 200
    states = {r["meal_slot"]: r["presence"] for r in meal_rows(owner, meal_world.alfa)}
    assert states == {0: "removed", 1: "added"}


# --- riuso della riga, svuotamento e versioni crescenti -------------------------------------------


@pytest.mark.tracks("meal.presence.write")
def test_re_adding_a_removed_meal_reuses_the_row_and_versions_keep_growing(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    seen: list[int] = []
    for step, (present, version) in enumerate([(False, 0), (True, 1), (False, 2), (True, 3)]):
        done = put(planner, "dinner", present, version)
        assert done.status_code == 200, (step, done.text)
        seen.append(done.json()["contentVersion"])
        assert len([r for r in meal_rows(owner, fam) if r["meal_type"] == "dinner"]) == 1, step
    assert seen == [1, 2, 3, 4]
    row = meal_row(owner, fam, DAY, "dinner")
    assert row is not None
    assert (row["presence"], row["content_version"]) == ("added", 4)
    # orologio congelato: gli eventi hanno lo stesso `occurred_at`, l'ordine non e' osservabile
    assert sorted(e["after"]["pr"] for e in event_rows(owner)) == ["added"] * 2 + ["removed"] * 2
    assert tracked_count(owner, fam.id) == 4


def test_re_adding_a_removed_meal_empties_content_special_name_and_guests(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    dish = make_dish(owner, fam, "Pasta e ceci")
    make_meal(
        owner, fam, DAY, "other", 0, presence="removed", name="Aperitivo", special="restaurant",
        content_version=2, guests=4, guests_note="Zia Rita", guests_version=5,
    )  # fmt: skip
    first = add_item(owner, fam, DAY, "other", 0, dish=dish, position=0)
    second = add_item(owner, fam, DAY, "other", 0, text="Olive", position=1)
    done = put(planner, "other", True, 2)
    assert done.status_code == 200, done.text
    assert done.json()["items"] == []
    assert done.json()["special"] is None
    assert done.json()["name"] is None
    assert item_rows(owner, fam) == []
    row = meal_row(owner, fam, DAY, "other", 0)
    assert row is not None
    assert (row["presence"], row["name"], row["special_kind"]) == ("added", None, None)
    assert (row["guests_count"], row["guests_note"]) == (0, None)
    assert (row["content_version"], row["guests_version"]) == (3, 6), "entrambe le unità avanzano"
    events = event_rows(owner)
    assert sorted(e["unit_type"] for e in events) == ["meal_content", "meal_guests"], (
        "g/gn cambiano (4 -> 0): un evento anche per gli ospiti"
    )
    (event,) = (e for e in events if e["unit_type"] == "meal_content")
    removed = event["before"]["i"]
    assert [e["id"] for e in removed] == sorted([str(first), str(second)])
    by_id = {e["id"]: e for e in removed}
    assert by_id[str(first)] == {
        "id": str(first), "p": 0, "d": str(dish), "c": str(fam.courses["first"]),
    }  # fmt: skip
    assert by_id[str(second)] == {"id": str(second), "p": 1, "t": "Olive"}, (
        "le voci tolte stanno in `before` complete (annullabile)"
    )


def test_re_adding_a_removed_meal_invalidates_a_version_read_before_the_removal(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    make_meal(owner, meal_world.alfa, DAY, "dinner", content_version=5)
    assert put(planner, "dinner", False, 5).status_code == 200
    assert put(planner, "dinner", True, 6).status_code == 200
    stale = put(planner, "dinner", False, 5)
    assert stale.status_code == 412, (
        "un client con la versione di prima non scrive sul pasto «nuovo»"
    )
    assert stale.json()["params"]["current"]["contentVersion"] == 7


def test_re_adding_a_hidden_inherit_row_keeps_its_content_and_guests(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    """05-data §4.2: la riga `inherit` di un tipo non più di default si riaccende intatta."""
    fam = meal_world.alfa
    make_meal(
        owner, fam, DAY, "snack", presence="inherit", content_version=2, guests=2, guests_version=1
    )
    add_item(owner, fam, DAY, "snack", text="Biscotti")
    done = put(planner, "snack", True, 2)
    assert done.status_code == 200, done.text
    assert [i["freeText"] for i in done.json()["items"]] == ["Biscotti"]
    row = meal_row(owner, fam, DAY, "snack")
    assert row is not None
    assert (row["presence"], row["content_version"]) == ("added", 3)
    assert (row["guests_count"], row["guests_version"]) == (2, 1), "gli ospiti non si toccano"
    assert len(item_rows(owner, fam)) == 1


def test_removing_an_inherit_row_of_a_default_type_marks_it_removed(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    make_meal(owner, meal_world.alfa, DAY, "lunch", presence="inherit", content_version=1)
    assert put(planner, "lunch", False, 1).status_code == 200
    row = meal_row(owner, meal_world.alfa, DAY, "lunch")
    assert row is not None
    assert (row["presence"], row["content_version"]) == ("removed", 2)
    assert event_rows(owner)[0]["before"]["pr"] == "inherit"


def test_the_content_of_other_days_and_other_meals_is_untouched(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    make_meal(owner, fam, DAY, "lunch", content_version=1)
    add_item(owner, fam, DAY, "lunch", text="Riso")
    make_meal(owner, fam, date(2026, 10, 25), "dinner", presence="removed", content_version=3)
    before = meal_rows(owner, fam)
    assert put(planner, "dinner", False, 0).status_code == 200
    changed = [r for r in meal_rows(owner, fam) if r not in before]
    assert [(r["meal_date"], r["meal_type"]) for r in changed] == [(DAY, "dinner")]
    assert len(item_rows(owner, fam)) == 1


# --- If-Match, validazione e atomicità -----------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "if_match", "status", "code"),
    [
        ("senza If-Match", None, 428, "precondition_required"),
        ("versione futura", 9, 412, "conflict"),
        ("oltre int32", '"2147483648"', 412, "conflict"),
        ("19 cifre", '"1000000000000000000"', 422, "validation"),
        ("malformato", "abc", 422, "validation"),
        ("asterisco", "*", 422, "validation"),
        ("debole", 'W/"1"', 422, "validation"),
        ("negativo", '"-1"', 422, "validation"),
        ("zero iniziale", '"01"', 422, "validation"),
        ("virgolette vuote", '""', 422, "validation"),
    ],
)
def test_if_match_is_mandatory_and_checked_before_anything_is_written(
    label: str,
    if_match: Any,
    status: int,
    code: str,
    meal_world: World,
    planner: Actor,
    owner: Owner,
) -> None:
    state = planning_state(owner, meal_world.alfa)
    refused = planner.put(presence_url(DAY, "dinner"), {"present": False}, if_match=if_match)
    assert refused.status_code == status, (label, refused.status_code, refused.text)
    assert refused.json()["code"] == code
    assert planning_state(owner, meal_world.alfa) == state
    assert event_rows(owner) == []
    assert tracked_count(owner, meal_world.alfa.id) == 0


def test_a_stale_version_returns_the_current_state_names_the_author_by_id_only(
    meal_world: World, login: Login, planner: Actor, owner: Owner
) -> None:
    admin = login(meal_world.alfa.who("admin"))
    assert put(admin, "dinner", False, 0).status_code == 200
    lost = put(planner, "dinner", False, 0)
    assert lost.status_code == 412, lost.text
    params = lost.json()["params"]
    assert params["current"]["contentVersion"] == 1
    assert params["current"]["present"] is False
    assert params["modifiedBy"] == str(meal_world.alfa.who("admin").person)
    assert meal_world.alfa.who("admin").identity.email not in lost.text
    assert len(event_rows(owner)) == 1, "solo l'evento di chi ha vinto"


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, "", [], {}, "yes"])
def test_present_must_be_a_json_boolean(
    value: Any, meal_world: World, planner: Actor, owner: Owner
) -> None:
    refused = put(planner, "dinner", value, 0)
    assert refused.status_code == 422, (value, refused.status_code, refused.text)
    assert list(error_fields(refused)) == ["present"]
    assert meal_rows(owner, meal_world.alfa) == []
    assert event_rows(owner) == []


def test_a_missing_present_is_named_as_required(meal_world: World, planner: Actor) -> None:
    refused = planner.put(presence_url(DAY, "dinner"), {}, if_match=0)
    assert refused.status_code == 422
    assert error_fields(refused) == {"present": "required"}


@pytest.mark.parametrize(
    "field",
    ["name", "special", "items", "contentVersion", "version", "familyId", "family_id", "role",
     "presence", "guests", "mealType", "date", "slot"],
)  # fmt: skip
def test_extra_fields_are_refused_and_nothing_is_written(
    field: str, meal_world: World, planner: Actor, owner: Owner
) -> None:
    """Mass assignment (SR-024): la rotta cambia la presenza e basta."""
    refused = planner.put(presence_url(DAY, "dinner"), {"present": False, field: "x"}, if_match=0)
    assert refused.status_code == 422, (field, refused.status_code, refused.text)
    assert error_fields(refused) == {field: "unknown_field"}
    assert meal_rows(owner, meal_world.alfa) == []
    assert event_rows(owner) == []


def test_a_non_object_body_is_422_not_500(meal_world: World, planner: Actor, owner: Owner) -> None:
    bodies: list[Any] = [[], "false", 7, True]
    for body in bodies:
        got = planner.browser.request(
            "PUT", presence_url(DAY, "dinner"), json=body, headers={"If-Match": '"0"'},
            csrf=planner.csrf,
        )  # fmt: skip
        assert got.status_code == 422, (body, got.status_code, got.text)
    assert event_rows(owner) == []


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/meals/{DAY}/brunch/0/presence",
        f"/api/v1/meals/{DAY}/lunch/1/presence",
        f"/api/v1/meals/{DAY}/other/5/presence",
        "/api/v1/meals/2026-02-30/lunch/0/presence",
        "/api/v1/meals/xyz/lunch/0/presence",
    ],
)
def test_an_invalid_meal_key_is_404_or_422_and_writes_nothing(
    path: str, meal_world: World, planner: Actor, owner: Owner
) -> None:
    got = planner.put(path, {"present": False}, if_match=0)
    assert got.status_code in {404, 422}, (path, got.status_code, got.text)
    assert meal_rows(owner, meal_world.alfa) == []
    assert event_rows(owner) == []
    assert tracked_count(owner, meal_world.alfa.id) == 0


def test_if_the_event_cannot_be_written_the_presence_change_is_rolled_back(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    state = planning_state(owner, meal_world.alfa)
    with events_not_insertable(owner):
        failed = put(planner, "dinner", False, 0)
    assert failed.status_code >= 500, (failed.status_code, failed.text)
    assert "change_event" not in failed.text
    assert planning_state(owner, meal_world.alfa) == state, "tutto o niente"
    assert tracked_count(owner, meal_world.alfa.id) == 0
    assert put(planner, "dinner", False, 0).status_code == 200, "ritentabile con la stessa versione"
    assert len(event_rows(owner)) == 1


# --- eventi: solo identificativi, un evento per richiesta ---------------------------------------


def test_the_event_holds_no_name_no_email_and_the_author_is_the_person(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    fam = meal_world.alfa
    assert put(planner, "dinner", False, 0).status_code == 200
    stored = event_text(owner).lower()
    who = fam.who("planner")
    for secret in (who.identity.email.lower(), (who.identity.name or "").lower(), "@"):
        assert secret
        assert secret not in stored, f"{secret!r} nell'evento (SR-047)"
    assert str(who.person) in stored
    assert str(who.account) not in stored


def test_each_request_writes_its_own_event_with_a_correlation_id(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    """Backlog SL-05: ogni evento porta il `correlation_id` della richiesta; richieste diverse,
    identificatori diversi (move/swap/copy ne condivideranno uno solo per richiesta, SL-20/21)."""
    assert put(planner, "dinner", False, 0).status_code == 200
    assert put(planner, "lunch", False, 0).status_code == 200
    first, second = event_rows(owner)
    assert isinstance(first["correlation_id"], UUID)
    assert isinstance(second["correlation_id"], UUID)
    assert first["correlation_id"] != second["correlation_id"]


def test_the_presence_change_consumes_one_unit_of_the_daily_cap_and_nothing_more(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    assert tracked_count(owner, meal_world.alfa.id) == 0
    assert put(planner, "dinner", False, 0).status_code == 200
    assert tracked_count(owner, meal_world.alfa.id) == 1
    assert planner.get(plan_query()).status_code == 200
    assert tracked_count(owner, meal_world.alfa.id) == 1, "le letture non consumano il tetto"


# --- il passato ----------------------------------------------------------------------------------


def test_the_days_context_is_the_family_one_a_removal_today_is_allowed(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    """Oggi si può togliere un pasto (la correzione dei giorni passati è di SL-07, US-010)."""
    done = put(planner, "dinner", False, 0, day=TODAY)
    assert done.status_code == 200, done.text
    assert done.json()["past"] is False


def test_defaults_changed_to_none_make_every_meal_addable_at_version_zero(
    meal_world: World, planner: Actor, owner: Owner
) -> None:
    set_defaults(owner, meal_world.alfa, ())
    done = put(planner, "lunch", True, 0)
    assert done.status_code == 200
    assert done.json()["present"] is True
