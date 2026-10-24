"""Cambiare lo stato di un piatto: `POST /api/v1/dishes/{dishId}/status` (SL-05).

US-005: AC-005.1 (da provare -> collaudato: lo stato cambia e si registra un evento con data,
autore e ruolo dell'autore), AC-005.2 (collaudato -> da provare), AC-005.3 (nessun cambio
automatico), AC-005.4 (il Membro riceve `403`). US-049: AC-049.2 (solo identificativi nell'evento),
AC-049.4 (un'operazione fallita non lascia eventi). ADR-0008 (`If-Match` obbligatorio: `428`,
`412`, `422`), ADR-0012 (evento nella stessa transazione, formato compatto v1), THR-117.

Contratto (piano §4.2): corpo `{status: "to_try" | "tested"}`, `If-Match`, risposta `200
DishDetail` con `ETag`. Il test d'inventario dei marker `tracks` legge dai sorgenti la stringa
`tracks("catalog.dish.set_status")` (vedi `tests/security/test_change_event_security.py`).
"""

import contextlib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
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
    event_rows,
    event_text,
    link,
    make_dish,
    payload,
)
from support.owner import Owner
from support.tracks import assert_tracks, tracked_count

pytestmark = pytest.mark.integration
Login = Callable[[Who], Actor]
OP = "catalog.dish.set_status"
T0 = datetime(2026, 10, 23, 12, 7, 30, tzinfo=UTC)


@pytest.fixture
def clock(frozen_now: Callable[[datetime], None]) -> Callable[[datetime], None]:
    frozen_now(T0)
    return frozen_now


@pytest.fixture
def planner(world: World, login: Login, clock: Callable[[datetime], None]) -> Actor:
    return login(world.alfa.who("planner"))


def url(dish: Any) -> str:
    return f"/api/v1/dishes/{dish}/status"


def set_status(actor: Actor, dish: Any, status: str, version: int | str = 1) -> Any:
    return actor.post(url(dish), {"status": status}, if_match=version)


@contextlib.contextmanager
def events_not_insertable(owner: Owner) -> Iterator[None]:
    """Simula un database che rifiuta l'INSERT degli eventi: la scrittura deve fallire intera."""
    owner.execute("revoke insert on app.change_event from menu_app")
    try:
        yield
    finally:
        owner.execute("grant select, insert on app.change_event to menu_app")


# --- AC-005.1 e AC-005.2: il cambio di stato e il suo evento -------------------------------------


@pytest.mark.tracks("catalog.dish.set_status")
def test_ac_005_1_to_try_to_tested_changes_the_state_and_records_one_event(
    world: World, planner: Actor, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci", status="to_try")
    done = set_status(planner, dish, "tested")
    assert done.status_code == 200, done.text
    assert done.headers["cache-control"] == "no-store"
    assert etag(done) == '"2"'
    body = done.json()
    assert body["status"] == "tested"
    assert body["version"] == 2
    assert planner.get(f"/api/v1/dishes/{dish}").json() == body, "la risposta è il DishDetail"
    row = dish_row(owner, dish)
    assert row is not None
    assert (row[1], row[4]) == ("tested", 2)
    assert row[7] == world.alfa.who("planner").person, "modified_by = la persona che ha cambiato"

    (event,) = event_rows(owner)
    assert event["family_id"] == world.alfa.id
    assert event["actor_kind"] == "person"
    assert event["actor_person_id"] == world.alfa.who("planner").person, "persona, non account"
    assert event["actor_person_id"] != world.alfa.who("planner").account
    assert event["actor_role"] == "planner"
    assert (event["unit_type"], event["op"]) == ("dish", "status_change")
    assert event["dish_id"] == dish
    assert event["occurred_at"] == T0, "data e ora UTC dell'orologio del database (AC-005.1)"
    assert event["before"] == {"st": "to_try"}
    assert event["after"] == {"v": 1, "st": "tested"}
    for column in ("meal_date", "meal_type", "meal_slot", "subject_person_id"):
        assert event[column] is None, column


@pytest.mark.tracks("catalog.dish.set_status")
def test_ac_005_2_tested_back_to_to_try_changes_the_state_and_records_the_event(
    world: World, planner: Actor, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci", status="tested")
    done = set_status(planner, dish, "to_try")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "to_try"
    assert done.json()["version"] == 2
    (event,) = event_rows(owner)
    assert (event["unit_type"], event["op"], event["dish_id"]) == (
        "dish",
        "status_change",
        dish,
    )
    assert event["before"] == {"st": "tested"}
    assert event["after"] == {"v": 1, "st": "to_try"}


@pytest.mark.tracks("catalog.dish.set_status")
def test_the_administrator_can_change_the_status_and_the_event_records_the_admin_role(
    world: World, login: Login, clock: Callable[[datetime], None], owner: Owner
) -> None:
    admin = login(world.alfa.who("admin"))
    dish = make_dish(owner, world.alfa, "Risotto")
    assert set_status(admin, dish, "tested").status_code == 200
    (event,) = event_rows(owner)
    assert event["actor_role"] == "admin"
    assert event["actor_person_id"] == world.alfa.who("admin").person


@pytest.mark.tracks("catalog.dish.set_status")
def test_two_changes_make_two_events_and_each_keeps_the_role_at_that_moment(
    world: World, planner: Actor, owner: Owner, clock: Callable[[datetime], None]
) -> None:
    """FR-061: il ruolo dell'autore «in quel momento», riletto a ogni richiesta (SR-005)."""
    dish = make_dish(owner, world.alfa, "Risotto")
    assert set_status(planner, dish, "tested", 1).status_code == 200
    owner.execute(
        "update app.person set role = 'admin' where id = %s", (world.alfa.who("planner").person,)
    )
    clock(T0 + timedelta(seconds=5))  # istanti distinti: l'ordine degli eventi è deterministico
    assert set_status(planner, dish, "to_try", 2).status_code == 200
    first, second = event_rows(owner)
    assert first["occurred_at"] < second["occurred_at"]
    assert (first["actor_role"], second["actor_role"]) == ("planner", "admin")
    assert first["actor_person_id"] == second["actor_person_id"]
    assert (first["before"], first["after"]) == ({"st": "to_try"}, {"v": 1, "st": "tested"})
    assert (second["before"], second["after"]) == ({"st": "tested"}, {"v": 1, "st": "to_try"})


def test_the_status_change_leaves_every_other_field_of_the_dish_alone(
    world: World, planner: Actor, owner: Owner
) -> None:
    dish = make_dish(
        owner,
        world.alfa,
        "Pasta e ceci",
        courses=("first", "one_dish"),
        notes="Con rosmarino.",
        prep_time="30_60",
        sources=(link("https://ricette.example.test/ceci"), book("Il cucchiaio", "142")),
    )
    before = planner.get(f"/api/v1/dishes/{dish}").json()
    done = set_status(planner, dish, "tested")
    assert done.status_code == 200, done.text
    after = done.json()
    changed = {k for k in before if before[k] != after[k]}
    assert changed <= {"status", "version", "modifiedAt", "modifiedBy"}, changed
    assert {"status", "version"} <= changed


def test_a_status_change_makes_the_old_etag_stale_for_a_put(
    world: World, planner: Actor, owner: Owner
) -> None:
    """La scheda è una sola unità di concorrenza (`version`, 05-data): ADR-0008."""
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert set_status(planner, dish, "tested").status_code == 200
    stale = planner.put(f"/api/v1/dishes/{dish}", payload(world.alfa, "Nuovo nome"), if_match=1)
    assert stale.status_code == 412
    fresh = planner.put(f"/api/v1/dishes/{dish}", payload(world.alfa, "Nuovo nome"), if_match=2)
    assert fresh.status_code == 200
    assert fresh.json()["status"] == "tested", "il PUT non tocca lo stato"
    assert len(event_rows(owner)) == 1, "il PUT non scrive eventi: solo il cambio di stato"


# --- AC-005.3: nessun cambio automatico ----------------------------------------------------------


def test_ac_005_3_a_dish_stays_to_try_however_much_time_passes(
    world: World,
    planner: Actor,
    owner: Owner,
    clock: Callable[[datetime], None],
) -> None:
    dish = make_dish(owner, world.alfa, "Frittata", status="to_try", ever_planned=True)
    clock(T0 + timedelta(days=25))  # meno dei 30 giorni di inattività della sessione
    detail = planner.get(f"/api/v1/dishes/{dish}").json()
    assert detail["status"] == "to_try"
    assert detail["version"] == 1
    assert change_events(owner) == 0
    assert planner.get("/api/v1/dishes").json()["items"][0]["status"] == "to_try"


# --- AC-005.4: il Membro riceve 403 --------------------------------------------------------------


@pytest.mark.parametrize("status", ["to_try", "tested"])
def test_ac_005_4_a_member_gets_403_on_any_dish_and_nothing_is_written(
    status: str, world: World, login: Login, clock: Callable[[datetime], None], owner: Owner
) -> None:
    member = login(world.alfa.who("member"))
    dish = make_dish(owner, world.alfa, "Frittata", status=status)
    target = "tested" if status == "to_try" else "to_try"
    refused = set_status(member, dish, target)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "forbidden"
    row = dish_row(owner, dish)
    assert row is not None
    assert (row[1], row[4]) == (status, 1)
    assert change_events(owner) == 0


def test_a_member_created_dish_is_still_out_of_reach_of_the_status_route(
    world: World, login: Login, clock: Callable[[datetime], None], owner: Owner
) -> None:
    """Nessuna eccezione per i propri piatti prima di SL-17 (`member_own_to_try`)."""
    member = login(world.alfa.who("member"))
    dish = make_dish(owner, world.alfa, "Del membro", created_by="member")
    assert set_status(member, dish, "tested").status_code == 403
    assert change_events(owner) == 0


# --- AC-049.4: un'operazione fallita non lascia eventi -------------------------------------------


@pytest.mark.tracks("catalog.dish.set_status")
def test_ac_049_4_failed_attempts_leave_no_event_and_the_success_leaves_exactly_one(
    world: World, login: Login, planner: Actor, owner: Owner
) -> None:
    """Helper `assert_tracks` (08 §6.3): 403, 404, 412, 428, 422 senza eventi né modifiche."""
    member = login(world.alfa.who("member"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert_tracks(
        owner=owner,
        fam=world.alfa,
        happy=lambda: set_status(planner, dish, "tested"),
        expected=[
            {
                "unit_type": "dish",
                "op": "status_change",
                "dish_id": dish,
                "actor_role": "planner",
                "actor_person_id": world.alfa.who("planner").person,
                "before": {"st": "to_try"},
                "after": {"v": 1, "st": "tested"},
            }
        ],
        failing=[
            ("403 Membro", lambda: set_status(member, dish, "tested"), 403),
            ("404 sconosciuto", lambda: set_status(planner, uuid4(), "tested"), 404),
            ("412 versione vecchia", lambda: set_status(planner, dish, "tested", 7), 412),
            ("428 senza If-Match", lambda: planner.post(url(dish), {"status": "tested"}), 428),
            ("422 stato ignoto", lambda: set_status(planner, dish, "cooked"), 422),
            ("422 If-Match malformato", lambda: set_status(planner, dish, "tested", "abc"), 422),
            ("422 corpo vuoto", lambda: planner.post(url(dish), {}, if_match=1), 422),
        ],
    )


@pytest.mark.parametrize(
    ("label", "if_match", "status", "code"),
    [
        ("senza If-Match", None, 428, "precondition_required"),
        ("versione vecchia", 0, 412, "conflict"),
        ("versione futura", 9, 412, "conflict"),
        ("oltre int32", '"2147483648"', 412, "conflict"),
        ("malformato", "abc", 422, "validation"),
        ("asterisco", "*", 422, "validation"),
        ("debole", 'W/"1"', 422, "validation"),
        ("virgolette vuote", '""', 422, "validation"),
    ],
)
def test_if_match_is_mandatory_and_checked_before_anything_is_written(
    label: str,
    if_match: Any,
    status: int,
    code: str,
    world: World,
    planner: Actor,
    owner: Owner,
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    refused = planner.post(url(dish), {"status": "tested"}, if_match=if_match)
    assert refused.status_code == status, (label, refused.status_code, refused.text)
    assert refused.json()["code"] == code
    row = dish_row(owner, dish)
    assert row is not None
    assert (row[1], row[4]) == ("to_try", 1)
    assert change_events(owner) == 0


def test_a_stale_if_match_returns_the_current_state_as_for_a_put(
    world: World, login: Login, planner: Actor, owner: Owner
) -> None:
    """ADR-0008: il 412 riporta versione, autore (ID) e orario dell'ultima modifica."""
    admin = login(world.alfa.who("admin"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert set_status(admin, dish, "tested").status_code == 200
    lost = set_status(planner, dish, "to_try", 1)
    assert lost.status_code == 412, lost.text
    params = lost.json()["params"]
    assert params["current"]["version"] == 2
    assert params["current"]["status"] == "tested"
    assert params["modifiedBy"] == str(world.alfa.who("admin").person), "ID, mai il nome"
    assert world.alfa.who("admin").identity.email not in lost.text
    assert len(event_rows(owner)) == 1, "solo l'evento di chi ha vinto"


def test_an_unknown_dish_is_404_and_a_malformed_id_is_never_a_server_error(
    world: World, planner: Actor, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert set_status(planner, dish, "tested").status_code == 200, "la rotta esiste"
    missing = set_status(planner, uuid4(), "tested", 1)
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    for bad in ("abc", "1", "%00", "..%2Fsession"):
        got = planner.post(f"/api/v1/dishes/{bad}/status", {"status": "tested"}, if_match=1)
        assert got.status_code in {404, 422}, (bad, got.status_code)
    assert len(event_rows(owner)) == 1


# --- validazione del corpo (SR-010, SR-024) ------------------------------------------------------


@pytest.mark.parametrize("value", ["cooked", "TESTED", "", " tested", "tested ", None, 1, True, []])
def test_only_the_two_known_statuses_are_accepted(
    value: Any, world: World, planner: Actor, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    refused = planner.post(url(dish), {"status": value}, if_match=1)
    assert refused.status_code == 422, (value, refused.status_code, refused.text)
    assert list(error_fields(refused)) == ["status"]
    row = dish_row(owner, dish)
    assert row is not None
    assert row[1] == "to_try"
    assert change_events(owner) == 0


def test_a_missing_status_is_named_as_required(world: World, planner: Actor, owner: Owner) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    refused = planner.post(url(dish), {}, if_match=1)
    assert refused.status_code == 422
    assert error_fields(refused) == {"status": "required"}


@pytest.mark.parametrize(
    "field",
    ["name", "notes", "version", "id", "familyId", "family_id", "archived", "everPlanned",
     "createdBy", "modifiedBy", "role", "priority", "courseIds"],
)  # fmt: skip
def test_extra_fields_are_refused_and_nothing_is_written(
    field: str, world: World, planner: Actor, owner: Owner
) -> None:
    """Mass assignment (SR-010): la rotta cambia lo stato e basta."""
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    refused = planner.post(url(dish), {"status": "tested", field: "x"}, if_match=1)
    assert refused.status_code == 422, (field, refused.status_code, refused.text)
    assert error_fields(refused) == {field: "unknown_field"}
    row = dish_row(owner, dish)
    assert row is not None
    assert (row[0], row[1], row[4]) == ("Pasta e ceci", "to_try", 1)
    assert change_events(owner) == 0


def test_a_non_object_body_is_422_not_500(world: World, planner: Actor, owner: Owner) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    bodies: list[Any] = [[], "tested", 7]
    for body in bodies:
        got = planner.browser.request(
            "POST", url(dish), json=body, headers={"If-Match": '"1"'}, csrf=planner.csrf
        )
        assert got.status_code == 422, (body, got.status_code, got.text)
    assert change_events(owner) == 0


# --- AC-049.2: solo identificativi nell'evento ---------------------------------------------------


def test_ac_049_2_the_event_holds_no_name_no_email_and_no_dish_content(
    world: World, planner: Actor, owner: Owner
) -> None:
    dish = make_dish(
        owner,
        world.alfa,
        "CANARY-ALFA-NOME-PIATTO",
        notes="CANARY-ALFA-NOTE",
        sources=(link("https://canary-alfa.example.test/ricetta"),),
    )
    assert set_status(planner, dish, "tested").status_code == 200
    stored = event_text(owner).lower()
    assert stored, "nessun evento scritto"
    who = world.alfa.who("planner")
    for secret in (
        "canary-alfa-nome-piatto",
        "canary-alfa-note",
        "canary-alfa.example",
        who.identity.email.lower(),
        (who.identity.name or "").lower(),
        "@",
        world.alfa.canary.lower(),
    ):
        assert secret, "segreto vuoto: la prova non cerca nulla"
        assert secret not in stored, f"{secret!r} nell'evento (SR-047)"
    assert str(who.person) in stored, "la persona è indicata con l'identificativo"
    assert str(who.account) not in stored, "l'identificativo dell'account non entra negli eventi"


def test_the_event_survives_the_removal_of_the_author_without_rewriting_it(
    world: World, planner: Actor, owner: Owner
) -> None:
    """SR-047: la persona diventa tombstone; l'evento resta com'è e non porta nomi."""
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert set_status(planner, dish, "tested").status_code == 200
    (before,) = event_rows(owner)
    owner.execute(
        "update app.person set status = 'former', account_id = null, role = null, "
        "former_reason = 'removed' where id = %s",
        (world.alfa.who("planner").person,),
    )
    (after,) = event_rows(owner)
    assert after == before


# --- atomicità: stessa transazione della modifica (ADR-0012, AC-049.4) ---------------------------


def test_if_the_event_cannot_be_written_the_status_change_is_rolled_back(
    world: World, planner: Actor, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    with events_not_insertable(owner):
        failed = set_status(planner, dish, "tested")
    assert failed.status_code >= 500, (failed.status_code, failed.text)
    assert failed.json()["code"] != "forbidden"
    assert "change_event" not in failed.text, "nessun dettaglio interno nella risposta"
    row = dish_row(owner, dish)
    assert row is not None
    assert (row[1], row[4]) == ("to_try", 1), "stato e versione intatti: tutto o niente"
    assert change_events(owner) == 0
    assert set_status(planner, dish, "tested").status_code == 200, "ripristinato: si può ritentare"
    assert len(event_rows(owner)) == 1


def test_a_retry_after_a_server_failure_does_not_duplicate_the_event(
    world: World, planner: Actor, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    with events_not_insertable(owner):
        assert set_status(planner, dish, "tested").status_code >= 500
    assert set_status(planner, dish, "tested").status_code == 200
    assert set_status(planner, dish, "tested", 1).status_code == 412, "la versione è già avanzata"
    assert len(event_rows(owner)) == 1


# --- decisioni dell'utente (SL-05): stesso stato e piatto archiviato ---------------------------


@pytest.mark.tracks("catalog.dish.set_status")
def test_setting_the_same_status_again_is_a_change_it_bumps_the_version_and_writes_an_event(
    world: World, planner: Actor, owner: Owner
) -> None:
    """Decisione dell'utente: nessun caso speciale. Versione +1, un evento, consuma il tetto."""
    dish = make_dish(owner, world.alfa, "Pasta e ceci", status="tested")
    done = set_status(planner, dish, "tested")
    assert done.status_code == 200, done.text
    assert (done.json()["status"], done.json()["version"]) == ("tested", 2)
    (event,) = event_rows(owner)
    assert (event["unit_type"], event["op"]) == ("dish", "status_change")
    assert event["before"] == {"st": "tested"}
    assert event["after"] == {"v": 1, "st": "tested"}
    assert tracked_count(owner, world.alfa.id) == 1
    assert set_status(planner, dish, "tested", 1).status_code == 412, "la versione è avanzata"


@pytest.mark.tracks("catalog.dish.set_status")
def test_the_status_of_an_archived_dish_can_be_changed_like_a_put_allows(
    world: World, planner: Actor, owner: Owner
) -> None:
    """Decisione dell'utente: consentito come il PUT; il piatto resta archiviato."""
    dish = make_dish(owner, world.alfa, "Lasagne", status="to_try", archived=True)
    done = set_status(planner, dish, "tested")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "tested"
    assert done.json()["archived"] is True
    (event,) = event_rows(owner)
    assert event["dish_id"] == dish
    assert event["before"] == {"st": "to_try"}
