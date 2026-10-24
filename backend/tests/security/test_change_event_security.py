"""Eventi di modifica: inventario `tracks`, sola aggiunta, isolamento e riservatezza (SL-05).

SR-022 (la cronologia non si modifica né si cancella dall'interfaccia), SR-047 (solo
identificativi), SR-057 (sola aggiunta), SR-009/SR-008 (isolamento), THR-117 (una modifica negata
o un evento alterato: evento nella stessa transazione, trigger, nessuna rotta di modifica, test
d'inventario `tracks`), US-049: AC-049.3 (l'operazione di scrittura diretta di un evento non
esiste), AC-049.4. 08 §6.3 (`tracks`), §6.2 (`cross_family`), SR-021 (nessun contenuto nei log).

L'inventario legge i marker `tracks("<operationId>")` dai sorgenti, come quello di `cross_family`
(indipendente da `-k`). Una scrittura nuova che non dichiara `tracks` deve essere classificata
nell'elenco chiuso `UNTRACKED_WRITES`: è la rete contro la dimenticanza (ADR-0012, «la
completezza dipende dal test di inventario»).
"""

import re
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from support.crossfamily import assert_cross_family
from support.dishes import (
    Actor,
    Who,
    World,
    event_rows,
    event_text,
    make_dish,
    request_for,
    send,
)
from support.matrix import MATRIX, operations_of
from support.owner import Owner
from support.paths import BACKEND
from support.tracks import tracked_count

pytestmark = [pytest.mark.sec, pytest.mark.integration]
Login = Callable[[Who], Actor]
OP = "catalog.dish.set_status"

# Elenco chiuso (08 §6.3): le scritture che NON generano un evento di modifica. Il piatto si
# crea e si modifica nella scheda senza evento (FR-061 elenca contenuto dei pasti, presenze,
# ospiti, settimana tipo e STATO dei piatti); login e logout non toccano il piano.
UNTRACKED_WRITES = frozenset(
    {
        "catalog.dish.create",
        "catalog.dish.update",
        "identity.google.start",
        "identity.session.logout",
    }
)


# --- inventario `tracks` (THR-117) ---------------------------------------------------------------


def _marked_tracks() -> set[str]:
    marked: set[str] = set()
    for path in (BACKEND / "tests").rglob("test_*.py"):
        marked |= set(re.findall(r'tracks\("([a-z_.]+)"\)', path.read_text(encoding="utf-8")))
    return marked


def test_the_set_status_route_declares_tracks_in_x_authz(generated_schema: dict[str, Any]) -> None:
    found = [op for _, _, op in operations_of(generated_schema) if op["operationId"] == OP]
    assert found, f"{OP} assente dal contratto"
    tracks = found[0]["x-authz"].get("tracks")
    assert tracks, "la rotta che cambia lo stato del piatto deve dichiarare `tracks`"
    assert "dish" in tracks, "T(dish) nel piano §4.2"


def test_exactly_the_status_route_tracks_in_sl05(generated_schema: dict[str, Any]) -> None:
    tracked = {
        op["operationId"]
        for _, _, op in operations_of(generated_schema)
        if op.get("x-authz", {}).get("tracks")
    }
    assert tracked == {OP}


def test_every_tracked_operation_has_a_tracks_marked_test() -> None:
    """08 §6.3: ogni operazione con `x-authz.tracks` non vuoto ha un test marcato."""
    tracked = {op for op, row in MATRIX.items() if row.get("tracks")}
    assert tracked == {OP}, "la matrice dei test dichiara le rotte che tracciano"
    assert tracked - _marked_tracks() == set(), "operazioni che tracciano senza test `tracks`"


def test_every_write_either_tracks_or_is_in_the_closed_list_of_untracked_writes(
    generated_schema: dict[str, Any],
) -> None:
    """Una scrittura nuova senza `tracks` e senza classificazione fa fallire la suite."""
    unsafe = {
        op["operationId"]
        for method, _, op in operations_of(generated_schema)
        if method in {"post", "put", "patch", "delete"}
    }
    tracked = {
        op["operationId"]
        for _, _, op in operations_of(generated_schema)
        if op.get("x-authz", {}).get("tracks")
    }
    unclassified = unsafe - tracked - UNTRACKED_WRITES
    assert unclassified == set(), (
        f"scritture non classificate (tracks o elenco chiuso): {unclassified}"
    )
    stale = UNTRACKED_WRITES - unsafe
    assert stale == set(), f"voci dell'elenco senza rotta: {stale}"


def test_the_test_matrix_and_the_closed_list_agree_on_which_writes_exist() -> None:
    unsafe = {op for op, row in MATRIX.items() if row["unsafe"]}
    assert unsafe == UNTRACKED_WRITES | {OP}


@pytest.mark.parametrize("op_id", ["catalog.dish.create", "catalog.dish.update"])
def test_reverse_control_a_successful_untracked_write_leaves_events_and_counter_alone(
    op_id: str, world: World, login: Login, owner: Owner
) -> None:
    """08 §6.3 «controllo inverso»: nessun evento (e nessun consumo del tetto) senza `tracks`."""
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    response = send(planner, request_for(op_id, world.alfa, dish))
    assert response.status_code in {200, 201}, (op_id, response.status_code, response.text)
    assert event_rows(owner) == []
    assert tracked_count(owner, world.alfa.id) == 0


def test_the_inventory_can_fail_an_unclassified_write_is_detected() -> None:
    """Il controllo sa fallire: su un insieme sintetico una scrittura nuova resta fuori."""
    unsafe = {"catalog.dish.set_status", "catalog.dish.archive", "catalog.dish.create"}
    tracked = {"catalog.dish.set_status"}
    assert unsafe - tracked - UNTRACKED_WRITES == {"catalog.dish.archive"}


# --- AC-049.3: nessuna rotta crea, modifica o cancella un evento ---------------------------------


def test_ac_049_3_the_contract_has_no_route_that_writes_history(
    generated_schema: dict[str, Any],
) -> None:
    for method, path, op in operations_of(generated_schema):
        text = f"{path} {op['operationId']}".lower()
        if method in {"post", "put", "patch", "delete"}:
            assert not re.search(r"history|change[-_]?event|/events?\b", text), (method, path)
        assert not op["operationId"].startswith("history."), (
            "la lettura della cronologia è di M1 (SL-?): non c'è nemmeno quella in SL-05"
        )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/history",
        "/api/v1/history/{id}",
        "/api/v1/change-events",
        "/api/v1/change_events",
        "/api/v1/change-events/{id}",
        "/api/v1/events",
        "/api/v1/events/{id}",
        "/api/v1/dishes/{dish}/events",
        "/api/v1/dishes/{dish}/history",
    ],
)
def test_ac_049_3_no_account_can_create_change_or_delete_an_event_over_http(
    method: str, path: str, world: World, login: Login, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    admin = login(world.alfa.who("admin"))
    owner.execute(
        "insert into app.change_event (family_id, actor_kind, actor_person_id, actor_role, "
        "unit_type, op, dish_id, before, after) values (%s, 'person', %s, 'admin', 'dish', "
        """'status_change', %s, '{"st":"to_try"}', '{"v":1,"st":"tested"}')""",
        (world.alfa.id, world.alfa.who("admin").person, dish),
    )
    snapshot = event_rows(owner)
    resolved = path.replace("{id}", str(snapshot[0]["id"])).replace("{dish}", str(dish))
    body = {"unitType": "dish", "op": "archive", "after": {"v": 1}}
    response = admin.browser.request(
        method, resolved, json=body, headers={"If-Match": '"1"'}, csrf=admin.csrf
    )
    assert response.status_code in {404, 405}, (method, resolved, response.status_code)
    assert event_rows(owner) == snapshot, "gli eventi sono rimasti identici"


# --- isolamento tra famiglie (SR-008, SR-041) ----------------------------------------------------


@pytest.mark.cross_family("catalog.dish.set_status")
@pytest.mark.parametrize(("attacker", "victim"), [("alfa", "beta"), ("beta", "alfa")])
def test_changing_the_status_of_a_dish_of_another_family_is_404_and_writes_nothing(
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
        send_foreign=lambda: actor.post(
            f"/api/v1/dishes/{target}/status", {"status": "tested"}, if_match=1
        ),
        send_missing=lambda: actor.post(
            f"/api/v1/dishes/{uuid4()}/status", {"status": "tested"}, if_match=1
        ),
        victim_ids=(str(target),),
    )
    assert event_rows(owner) == [], "nessun evento, né per la vittima né per l'aggressore"
    assert tracked_count(owner, a.id) == tracked_count(owner, v.id) == 0


@pytest.mark.cross_family("catalog.dish.set_status")
def test_a_foreign_dish_with_a_wrong_version_is_404_never_412(
    world: World, login: Login, owner: Owner
) -> None:
    target = make_dish(owner, world.beta, "CANARY-BETA-DISH-1")
    actor = login(world.alfa.who("planner"))
    response = actor.post(f"/api/v1/dishes/{target}/status", {"status": "tested"}, if_match=99)
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert event_rows(owner) == []


def test_the_family_of_an_event_comes_from_the_session_never_from_the_request(
    world: World, login: Login, owner: Owner
) -> None:
    mine = make_dish(owner, world.alfa, "Pasta e ceci")
    planner = login(world.alfa.who("planner"))
    for extra in ({"familyId": str(world.beta.id)}, {"actorPersonId": str(uuid4())}):
        refused = planner.post(
            f"/api/v1/dishes/{mine}/status", {"status": "tested", **extra}, if_match=1
        )
        assert refused.status_code == 422
    done = planner.post(f"/api/v1/dishes/{mine}/status", {"status": "tested"}, if_match=1)
    assert done.status_code == 200
    ((family, person),) = owner.rows("select family_id, actor_person_id from app.change_event")
    assert (family, person) == (world.alfa.id, world.alfa.who("planner").person)


def test_a_dish_of_the_same_family_but_a_foreign_family_header_is_still_the_session_family(
    world: World, login: Login, owner: Owner
) -> None:
    """SR-008: nessun parametro del client sceglie la famiglia (intestazione compresa)."""
    mine = make_dish(owner, world.alfa, "Pasta e ceci")
    planner = login(world.alfa.who("planner"))
    done = planner.browser.request(
        "POST",
        f"/api/v1/dishes/{mine}/status",
        json={"status": "tested"},
        headers={"If-Match": '"1"', "X-Family-Id": str(world.beta.id)},
        csrf=planner.csrf,
    )
    assert done.status_code == 200
    assert [e["family_id"] for e in event_rows(owner)] == [world.alfa.id]


# --- riservatezza nei log e nel registro di sicurezza (SR-021, SR-047) ---------------------------


NAME = "CANARY-NAME-4e71b"
NOTE = "CANARY-NOTE-a09c3"


def test_status_changes_never_log_event_content_names_or_emails(
    world: World,
    login: Login,
    owner: Owner,
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    planner = login(world.alfa.who("planner"))
    member = login(world.alfa.who("member"))
    beta = login(world.beta.who("planner"))
    dish = make_dish(owner, world.alfa, NAME, notes=NOTE)
    bodies = [
        planner.post(f"/api/v1/dishes/{dish}/status", {"status": "tested"}, if_match=1).text,
        planner.post(f"/api/v1/dishes/{dish}/status", {"status": NAME}, if_match=2).text,  # 422
        planner.post(f"/api/v1/dishes/{dish}/status", {"status": "to_try"}, if_match=9).text,  # 412
        member.post(f"/api/v1/dishes/{dish}/status", {"status": "to_try"}, if_match=2).text,  # 403
        beta.post(f"/api/v1/dishes/{dish}/status", {"status": "to_try"}, if_match=2).text,  # 404
    ]
    out = capfd.readouterr()
    logged = out.out + out.err + caplog.text
    who = world.alfa.who("planner")
    registry = str(owner.rows("select t::text from app.security_event t"))
    stored = event_text(owner)
    assert stored, "l'evento del primo cambio esiste"
    secrets_ = (NAME, NOTE, who.identity.email, who.identity.name or "x")
    for secret in secrets_:
        assert secret not in logged, f"{secret} nei log"
        assert secret not in registry, f"{secret} nel registro di sicurezza"
        assert secret not in stored, f"{secret} nell'evento"
    for fragment in ('"v": 1', '"v":1', '"st"'):
        assert fragment not in logged, (
            f"{fragment}: before/after non vanno mai nei log (05-data §10)"
        )
    assert NAME not in bodies[1], "il rifiuto non riflette il valore inviato"
