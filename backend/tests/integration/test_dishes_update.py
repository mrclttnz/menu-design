"""Consultare e modificare un piatto: `GET` e `PUT /api/v1/dishes/{dishId}` (SL-04; ADR-0008).

Concorrenza ottimistica (08 §7.3): `ETag: "<n>"` sulle risorse singole, `If-Match` obbligatorio
sulla scrittura (`428` se assente, `422 invalid_value` se malformato, `412 conflict` se superato).
L'unità «scheda del piatto» (`version`) cresce anche per modifiche a fonti e portate (05-data).
"""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from support.dishes import (
    Actor,
    Who,
    World,
    book,
    change_events,
    dish_row,
    error_fields,
    etag,
    link,
    make_dish,
    payload,
)
from support.owner import Owner

pytestmark = pytest.mark.integration
Login = Callable[[Who], Actor]


@pytest.fixture
def planner(world: World, login: Login) -> Actor:
    return login(world.alfa.who("planner"))


@pytest.fixture
def dish(world: World, planner: Actor) -> dict[str, Any]:
    created = planner.post(
        "/api/v1/dishes",
        payload(
            world.alfa,
            "Pasta e ceci",
            status="tested",
            prepTime="30_60",
            notes="Con rosmarino.",
            sources=[link("https://ricette.example.test/ceci"), book("Il cucchiaio", "142")],
        ),
    )
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def url(dish: dict[str, Any]) -> str:
    return f"/api/v1/dishes/{dish['id']}"


# --- lettura --------------------------------------------------------------------------------------


def test_the_detail_carries_etag_equal_to_version(planner: Actor, dish: dict[str, Any]) -> None:
    detail = planner.get(url(dish))
    assert detail.status_code == 200
    assert etag(detail) == '"1"'
    assert detail.json()["version"] == 1
    assert detail.headers["cache-control"] == "no-store"
    assert detail.json()["sources"][1] == {
        "kind": "book",
        "reference": "Il cucchiaio",
        "page": "142",
    }


def test_every_role_can_read_a_dish(world: World, login: Login, dish: dict[str, Any]) -> None:
    for role in ("admin", "planner", "member"):
        reader = login(world.alfa.who(role))
        got = reader.get(url(dish))
        assert got.status_code == 200, (role, got.text)
        assert got.json()["name"] == "Pasta e ceci"


def test_an_unknown_dish_is_not_found(planner: Actor, dish: dict[str, Any]) -> None:
    assert planner.get(url(dish)).status_code == 200, "la rotta esiste: solo l'ID è sconosciuto"
    missing = planner.get(f"/api/v1/dishes/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"


@pytest.mark.parametrize("bad_id", ["abc", "1", "0" * 36, "%00", "..%2Fsession"])
def test_a_malformed_dish_id_is_never_a_server_error(
    planner: Actor, dish: dict[str, Any], bad_id: str
) -> None:
    assert planner.get(url(dish)).status_code == 200, "la rotta esiste: solo l'ID è malformato"
    got = planner.get(f"/api/v1/dishes/{bad_id}")
    assert got.status_code in {404, 422}, got.status_code
    assert got.json()["code"] in {"not_found", "validation"}


# --- AC: modifica completa -----------------------------------------------------------------------


def test_put_replaces_the_dish_and_bumps_the_version(
    world: World, planner: Actor, dish: dict[str, Any], owner: Owner
) -> None:
    fam = world.alfa
    body = payload(
        fam,
        "Pasta e ceci alla romana",
        courseIds=[str(fam.courses["first"]), str(fam.courses["one_dish"])],
        notes="Meglio il giorno dopo.",
        prepTime="over_60",
        sources=[book("La cucina romana", "7")],
    )
    updated = planner.put(url(dish), body, if_match=1)
    assert updated.status_code == 200, updated.text
    assert etag(updated) == '"2"'
    new = updated.json()
    assert new["version"] == 2
    assert new["name"] == "Pasta e ceci alla romana"
    assert new["notes"] == "Meglio il giorno dopo."
    assert new["prepTime"] == "over_60"
    assert sorted(new["courseIds"]) == sorted(body["courseIds"])
    assert new["sources"] == [{"kind": "book", "reference": "La cucina romana", "page": "7"}]
    # ciò che il PUT non può cambiare
    assert new["id"] == dish["id"]
    assert new["createdBy"] == dish["createdBy"]
    assert new["status"] == "tested", "lo stato cambia con POST /status (SL-05), non con PUT"
    assert new["archived"] is False
    assert new["everPlanned"] is False
    assert planner.get(url(dish)).json() == new
    row = dish_row(owner, dish["id"])
    assert row is not None
    assert row[4] == 2
    assert row[7] == fam.who("planner").person, "modified_by = chi ha modificato"


def test_put_without_optional_fields_clears_them(
    world: World, planner: Actor, dish: dict[str, Any]
) -> None:
    """`PUT` sostituisce la scheda: note, tempo e fonti omessi vengono tolti."""
    updated = planner.put(url(dish), payload(world.alfa, "Pasta e ceci"), if_match=1)
    assert updated.status_code == 200, updated.text
    new = updated.json()
    assert new.get("notes") is None
    assert new.get("prepTime") is None
    assert new["sources"] == []


def test_changing_only_the_sources_or_only_the_courses_bumps_the_version(
    world: World, planner: Actor, dish: dict[str, Any]
) -> None:
    """05-data: la versione «cresce anche per modifiche a fonti, portate»."""
    same = payload(
        world.alfa,
        "Pasta e ceci",
        courseIds=dish["courseIds"],
        notes=dish["notes"],
        prepTime=dish["prepTime"],
        sources=dish["sources"],
    )
    only_sources = dict(same, sources=[link("https://ricette.example.test/nuova")])
    first = planner.put(url(dish), only_sources, if_match=1)
    assert first.status_code == 200
    assert first.json()["version"] == 2
    only_courses = dict(only_sources, courseIds=[str(world.alfa.courses["side"])])
    second = planner.put(url(dish), only_courses, if_match=2)
    assert second.status_code == 200
    assert second.json()["version"] == 3


def test_the_etag_of_a_put_can_be_used_for_the_next_one(
    world: World, planner: Actor, dish: dict[str, Any]
) -> None:
    first = planner.put(
        url(dish), payload(world.alfa, "Uno"), if_match=etag(planner.get(url(dish)))
    )
    assert first.status_code == 200
    second = planner.put(url(dish), payload(world.alfa, "Due"), if_match=etag(first))
    assert second.status_code == 200
    assert second.json()["version"] == 3
    assert etag(second) == '"3"'


def test_put_validates_like_post(world: World, planner: Actor, dish: dict[str, Any]) -> None:
    refused = planner.put(
        url(dish),
        payload(world.alfa, "", courseIds=[], sources=[link("javascript:alert(1)")]),
        if_match=1,
    )
    assert refused.status_code == 422
    assert error_fields(refused) == {
        "name": "required",
        "courseIds": "course_required",
        "sources[0].reference": "url_invalid",
    }
    assert planner.get(url(dish)).json()["version"] == 1, "nessuna scrittura parziale"


def test_markup_in_a_modified_name_stays_literal(
    world: World, planner: Actor, dish: dict[str, Any]
) -> None:
    text = "<script>alert(1)</script>"
    updated = planner.put(url(dish), payload(world.alfa, text, notes=text), if_match=1)
    assert updated.status_code == 200
    assert updated.json()["name"] == text
    assert updated.json()["notes"] == text


def test_put_on_an_unknown_dish_is_not_found(
    world: World, planner: Actor, dish: dict[str, Any]
) -> None:
    ok = planner.put(url(dish), payload(world.alfa, "Esiste"), if_match=1)
    assert ok.status_code == 200, "la rotta esiste: solo l'ID è sconosciuto"
    missing = planner.put(f"/api/v1/dishes/{uuid4()}", payload(world.alfa), if_match=1)
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"


def test_put_does_not_write_change_events_in_sl04(
    world: World, planner: Actor, dish: dict[str, Any], owner: Owner
) -> None:
    planner.put(url(dish), payload(world.alfa, "Altro"), if_match=1)
    assert change_events(owner) == 0


# --- If-Match: 428, 412, 422 ----------------------------------------------------------------------


def test_put_without_if_match_is_428_and_changes_nothing(
    world: World, planner: Actor, dish: dict[str, Any], owner: Owner
) -> None:
    refused = planner.put(url(dish), payload(world.alfa, "Senza precondizione"))
    assert refused.status_code == 428
    assert refused.json()["code"] == "precondition_required"
    row = dish_row(owner, dish["id"])
    assert row is not None
    assert row[0] == "Pasta e ceci"
    assert row[4] == 1


def test_a_stale_version_is_412_with_the_current_state_and_does_not_write(
    world: World, login: Login, planner: Actor, dish: dict[str, Any], owner: Owner
) -> None:
    admin = login(world.alfa.who("admin"))
    won = admin.put(url(dish), payload(world.alfa, "Modificato dall'amministratore"), if_match=1)
    assert won.status_code == 200
    lost = planner.put(url(dish), payload(world.alfa, "Modificato dal pianificatore"), if_match=1)
    assert lost.status_code == 412, lost.text
    problem = lost.json()
    assert problem["code"] == "conflict"
    params = problem["params"]
    assert set(params) >= {"current", "modifiedBy", "modifiedAt"}
    assert params["current"]["version"] == 2
    assert params["modifiedBy"] == str(world.alfa.who("admin").person), "ID, mai il nome"
    assert params["modifiedAt"].endswith("Z") or "+" in params["modifiedAt"]
    admin_who = world.alfa.who("admin")
    assert str(admin_who.identity.name) not in lost.text
    assert admin_who.identity.email not in lost.text
    row = dish_row(owner, dish["id"])
    assert row is not None
    assert row[0] == "Modificato dall'amministratore"
    assert row[4] == 2


def test_if_match_zero_on_an_existing_dish_is_412(
    world: World, planner: Actor, dish: dict[str, Any]
) -> None:
    refused = planner.put(url(dish), payload(world.alfa, "x"), if_match=0)
    assert refused.status_code == 412
    assert refused.json()["code"] == "conflict"


def test_a_future_version_is_412_not_a_write(
    world: World, planner: Actor, dish: dict[str, Any]
) -> None:
    refused = planner.put(url(dish), payload(world.alfa, "x"), if_match=7)
    assert refused.status_code == 412


@pytest.mark.parametrize(
    "value",
    ["2147483648", "999999999999999999"],
)
def test_if_match_above_int32_but_within_18_digits_is_412_never_500(
    world: World, planner: Actor, dish: dict[str, Any], value: str
) -> None:
    """THR-107: le colonne `version` sono `integer`, il confronto è `bigint`: niente overflow."""
    refused = planner.put(url(dish), payload(world.alfa, "x"), if_match=f'"{value}"')
    assert refused.status_code == 412, (refused.status_code, refused.text)


@pytest.mark.parametrize(
    "value",
    [
        "abc",
        "*",
        'W/"1"',
        '"-1"',
        '"1.5"',
        '"01"',
        "1",
        '""',
        '"1", "2"',
        '"1000000000000000000"',  # 19 cifre
    ],
)
def test_malformed_if_match_is_422_invalid_value_and_not_reflected(
    world: World, planner: Actor, dish: dict[str, Any], value: str
) -> None:
    refused = planner.put(url(dish), payload(world.alfa, "x"), if_match=value)
    assert refused.status_code == 422, (value, refused.status_code, refused.text)
    assert error_fields(refused) == {"If-Match": "invalid_value"}
    assert value not in refused.text or value in {"1", "*"}
    assert planner.get(url(dish)).json()["version"] == 1


def test_if_match_of_eighteen_digits_is_accepted_as_a_precondition(
    world: World, planner: Actor, dish: dict[str, Any]
) -> None:
    refused = planner.put(url(dish), payload(world.alfa, "x"), if_match='"123456789012345678"')
    assert refused.status_code == 412


# --- campi non scrivibili (SR-010) ----------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["status", "id", "version", "familyId", "family_id", "createdBy", "createdAt", "modifiedBy",
     "modifiedAt", "archived", "archivedAt", "everPlanned", "priority", "tagIds", "role"],
)  # fmt: skip
def test_non_writable_fields_are_refused_on_put_and_nothing_changes(
    world: World, planner: Actor, dish: dict[str, Any], owner: Owner, field: str
) -> None:
    refused = planner.put(url(dish), payload(world.alfa, "Hack") | {field: "x"}, if_match=1)
    assert refused.status_code == 422, (field, refused.status_code, refused.text)
    assert error_fields(refused) == {field: "unknown_field"}
    row = dish_row(owner, dish["id"])
    assert row is not None
    assert row[0] == "Pasta e ceci"
    assert row[4] == 1


# --- sicurezza della scheda: chi vede cosa --------------------------------------------------------


def test_the_dish_of_another_family_is_not_found_for_get_and_put(
    world: World, planner: Actor, owner: Owner
) -> None:
    beta_dish = make_dish(owner, world.beta, "CANARY-BETA-DISH-1")
    assert planner.get(f"/api/v1/dishes/{beta_dish}").status_code == 404
    refused = planner.put(f"/api/v1/dishes/{beta_dish}", payload(world.alfa), if_match=1)
    assert refused.status_code == 404
    row = dish_row(owner, beta_dish)
    assert row is not None
    assert row[0] == "CANARY-BETA-DISH-1"
    assert row[4] == 1
