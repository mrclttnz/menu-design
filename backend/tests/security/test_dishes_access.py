"""Matrice A/P/M dell'archivio piatti, CSRF e campi non scrivibili (SL-04).

SR-008, SR-009 (negato per default, test negativo per ogni cella «No»), SR-010 (mass assignment),
SR-023/THR-007 (CSRF), THR-023 (escalation verticale), SR-005 (ruolo e appartenenza riletti a
ogni richiesta). La matrice è `tests/security/authz_matrix.yaml`, trascritta dai requisiti e
indipendente dal codice. Le richieste valide di ogni operazione sono in
`support.dishes.request_for`.

Nota di stato (SL-04): il Membro non ha ancora la regola `member_own_to_try` (arriva con SL-17,
piano §4.3): in questa slice crea e modifica con `403`; a regime lo potrà fare per i piatti «da
provare».
"""

from collections.abc import Callable
from typing import Any

import pytest

from support.accounts import security_events
from support.browser_sim import Browser
from support.dishes import (
    Actor,
    Who,
    World,
    change_events,
    dish_count,
    dish_row,
    error_fields,
    family_state_hash,
    make_dish,
    payload,
    request_for,
    send,
)
from support.matrix import MATRIX
from support.owner import Owner

pytestmark = [pytest.mark.sec, pytest.mark.integration]
Login = Callable[[Who], Actor]

CATALOG_OPS = sorted(op for op in MATRIX if op.startswith("catalog."))
UNSAFE_OPS = [op for op in CATALOG_OPS if MATRIX[op]["unsafe"]]
CELLS = [(op, role) for op in CATALOG_OPS for role in ("admin", "planner", "member")]


def test_the_matrix_covers_the_five_archive_operations() -> None:
    assert CATALOG_OPS == [
        "catalog.course.list",
        "catalog.dish.create",
        "catalog.dish.list",
        "catalog.dish.read",
        "catalog.dish.update",
    ]


# --- anonimo: 401 su ogni operazione -------------------------------------------------------------


@pytest.mark.parametrize("op_id", CATALOG_OPS)
def test_anonymous_gets_401_and_no_side_effect(
    op_id: str, world: World, auth_client: Any, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    anonymous = Browser(auth_client)
    token = anonymous.anonymous_csrf()
    req = request_for(op_id, world.alfa, dish)
    before = family_state_hash(owner, world.alfa)
    kw: dict[str, Any] = {} if req.method == "GET" else {"csrf": token}
    headers = {"If-Match": req.if_match} if req.if_match else {}
    response = anonymous.request(
        req.method, req.path + req.query, json=req.body, headers=headers, **kw
    )
    assert response.status_code == 401, (op_id, response.status_code, response.text)
    assert response.json()["code"] == "unauthenticated"
    assert "Pasta e ceci" not in response.text
    assert family_state_hash(owner, world.alfa) == before
    assert not [c for c in anonymous.last_cookies if c.name == "__Host-session"]


def test_an_expired_or_unknown_session_cookie_is_401(
    world: World, auth_client: Any, owner: Owner
) -> None:
    make_dish(owner, world.alfa, "Pasta e ceci")
    stranger = Browser(auth_client)
    stranger.cookies["__Host-session"] = "x" * 43
    response = stranger.get("/api/v1/dishes")
    assert response.status_code == 401
    assert "Pasta e ceci" not in response.text


# --- matrice ruolo x operazione -------------------------------------------------------------------


@pytest.mark.parametrize(("op_id", "role"), CELLS)
def test_role_matrix(op_id: str, role: str, world: World, login: Login, owner: Owner) -> None:
    """Ogni cella: «allow» riesce; «403» è `forbidden`, evento `access.denied`, nessun effetto."""
    expected = MATRIX[op_id]["cells"][role]
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    actor = login(world.alfa.who(role))
    before = family_state_hash(owner, world.alfa)
    response = send(actor, request_for(op_id, world.alfa, dish))
    if expected == "allow":
        assert response.status_code in {200, 201}, (
            op_id,
            role,
            response.status_code,
            response.text,
        )
        assert response.headers["cache-control"] == "no-store"
        return
    assert expected == 403
    assert response.status_code == 403, (op_id, role, response.status_code, response.text)
    assert response.json()["code"] == "forbidden"
    assert family_state_hash(owner, world.alfa) == before, "una cella «No» non deve avere effetti"
    assert change_events(owner) == 0
    denied = security_events(owner, "access.denied")
    assert denied, "manca l'evento access.denied"
    event = denied[-1]
    assert event["outcome"] == "denied"
    assert event["actor_kind"] == "account"
    assert event["actor_role"] == role
    assert event["family_id"] == world.alfa.id
    assert event["actor_account_id"] == world.alfa.who(role).account
    assert op_id in str(event["details"]) or op_id == event["target_type"]
    assert "Pasta e ceci" not in str(event)
    assert "Nuovo piatto" not in str(event)


def test_a_denied_member_write_is_refused_before_any_validation_leak(
    world: World, login: Login, owner: Owner
) -> None:
    """Il permesso si controlla prima del merito: un Membro non scopre le regole di validazione."""
    member = login(world.alfa.who("member"))
    bad = member.post("/api/v1/dishes", payload(world.alfa, "", courseIds=[]))
    assert bad.status_code == 403, bad.text
    assert dish_count(owner, world.alfa) == 0


def test_the_member_cannot_create_a_tested_dish_nor_a_to_try_one_in_sl04(
    world: World, login: Login, owner: Owner
) -> None:
    member = login(world.alfa.who("member"))
    for status in ("tested", "to_try"):
        refused = member.post("/api/v1/dishes", payload(world.alfa, status=status))
        assert refused.status_code == 403, (status, refused.text)
    assert dish_count(owner, world.alfa) == 0


# --- ruolo e appartenenza riletti a ogni richiesta (SR-005, THR-023) ------------------------------


def test_a_demoted_planner_loses_the_write_on_the_next_request(
    world: World, login: Login, owner: Owner
) -> None:
    planner = login(world.alfa.who("planner"))
    assert planner.post("/api/v1/dishes", payload(world.alfa, "Prima")).status_code == 201
    owner.execute(
        "update app.person set role = 'member' where id = %s", (world.alfa.who("planner").person,)
    )
    refused = planner.post("/api/v1/dishes", payload(world.alfa, "Dopo"))
    assert refused.status_code == 403, refused.text
    assert planner.get("/api/v1/dishes").status_code == 200, "può ancora leggere"
    assert dish_count(owner, world.alfa) == 1


def test_a_promoted_member_can_write_on_the_next_request_with_no_stale_role(
    world: World, login: Login, owner: Owner
) -> None:
    member = login(world.alfa.who("member"))
    assert member.post("/api/v1/dishes", payload(world.alfa)).status_code == 403
    owner.execute(
        "update app.person set role = 'planner' where id = %s", (world.alfa.who("member").person,)
    )
    assert member.post("/api/v1/dishes", payload(world.alfa)).status_code == 201


def test_a_person_removed_from_the_family_gets_not_found_on_family_resources(
    world: World, login: Login, owner: Owner
) -> None:
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    owner.execute(
        "update app.person set status = 'former', account_id = null, role = null, "
        "former_reason = 'removed' where id = %s",
        (world.alfa.who("planner").person,),
    )
    for response in (
        planner.get("/api/v1/dishes"),
        planner.get(f"/api/v1/dishes/{dish}"),
        planner.get("/api/v1/courses"),
        planner.post("/api/v1/dishes", payload(world.alfa)),
    ):
        assert response.status_code in {403, 404}, response.status_code
        assert "Pasta e ceci" not in response.text
    assert dish_count(owner, world.alfa) == 1
    view = planner.browser.session().json()
    assert view["authenticated"] is True
    assert view["family"] is None


# --- campi non scrivibili: mass assignment (SR-010) -----------------------------------------------


MASS = [
    "id",
    "familyId",
    "family_id",
    "createdBy",
    "created_by",
    "createdAt",
    "modifiedBy",
    "modifiedAt",
    "version",
    "archived",
    "archivedAt",
    "everPlanned",
    "role",
    "priority",
    "tagIds",
]


@pytest.mark.parametrize("field", MASS)
def test_create_refuses_non_writable_fields(
    field: str, world: World, login: Login, owner: Owner
) -> None:
    planner = login(world.alfa.who("planner"))
    refused = planner.post("/api/v1/dishes", payload(world.alfa) | {field: "x"})
    assert refused.status_code == 422, (field, refused.status_code, refused.text)
    assert error_fields(refused) == {field: "unknown_field"}
    assert dish_count(owner, world.alfa) == 0


def test_create_refuses_a_foreign_family_id_in_the_body_without_using_it(
    world: World, login: Login, owner: Owner
) -> None:
    planner = login(world.alfa.who("planner"))
    refused = planner.post("/api/v1/dishes", payload(world.alfa) | {"familyId": str(world.beta.id)})
    assert refused.status_code == 422
    assert dish_count(owner, world.alfa) == 0
    assert dish_count(owner, world.beta) == 0


def test_the_family_of_a_new_dish_always_comes_from_the_session(
    world: World, login: Login, owner: Owner
) -> None:
    planner = login(world.alfa.who("planner"))
    created = planner.post("/api/v1/dishes", payload(world.alfa, "Mio"))
    assert created.status_code == 201
    row = owner.rows(
        "select family_id, created_by from app.dish where id = %s", (created.json()["id"],)
    )
    assert row == [(world.alfa.id, world.alfa.who("planner").person)]
    # una query string con un'altra famiglia non cambia nulla (SR-008: mai un parametro del client)
    other = planner.get(f"/api/v1/dishes?familyId={world.beta.id}&family_id={world.beta.id}")
    assert other.status_code in {200, 422}
    if other.status_code == 200:
        assert [d["name"] for d in other.json()["items"]] == ["Mio"]


# --- CSRF su ogni scrittura (SR-023, THR-007; 08 §7.2) --------------------------------------------


def _csrf_request(actor: Actor, op_id: str, world: World, dish: Any, **override: Any) -> Any:
    req = request_for(op_id, world.alfa, dish)
    headers = {"If-Match": req.if_match} if req.if_match else {}
    kw: dict[str, Any] = {"csrf": actor.csrf} | override
    return actor.browser.request(req.method, req.path, json=req.body, headers=headers, **kw)


@pytest.mark.parametrize("op_id", UNSAFE_OPS)
@pytest.mark.parametrize(
    ("label", "override", "status", "code"),
    [
        ("senza token", {"csrf": None}, 403, "csrf_failed"),
        ("token vuoto", {"csrf": ""}, 403, "csrf_failed"),
        ("token errato", {"csrf": "x" * 43}, 403, "csrf_failed"),
        ("origine estranea", {"origin": "https://evil.example"}, 403, "csrf_failed"),
        ("origine null", {"origin": "null"}, 403, "csrf_failed"),
        ("cross-site", {"sec_fetch_site": "cross-site"}, 403, "csrf_failed"),
        ("same-site", {"sec_fetch_site": "same-site"}, 403, "csrf_failed"),
        ("text/plain", {"content_type": "text/plain"}, 415, "unsupported_media_type"),
        (
            "form",
            {"content_type": "application/x-www-form-urlencoded"},
            415,
            "unsupported_media_type",
        ),
        ("multipart", {"content_type": "multipart/form-data"}, 415, "unsupported_media_type"),
    ],
)
def test_unsafe_archive_operations_reject_csrf_and_media_type_attacks(
    op_id: str,
    label: str,
    override: dict[str, Any],
    status: int,
    code: str,
    world: World,
    login: Login,
    owner: Owner,
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    planner = login(world.alfa.who("planner"))
    before = family_state_hash(owner, world.alfa)
    response = _csrf_request(planner, op_id, world, dish, **override)
    assert response.status_code == status, (label, response.status_code, response.text)
    assert response.json()["code"] == code
    assert family_state_hash(owner, world.alfa) == before, label
    assert change_events(owner) == 0


@pytest.mark.parametrize("op_id", UNSAFE_OPS)
def test_the_csrf_token_of_another_session_is_refused(
    op_id: str, world: World, login: Login, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    planner = login(world.alfa.who("planner"))
    admin = login(world.alfa.who("admin"))
    before = family_state_hash(owner, world.alfa)
    response = _csrf_request(planner, op_id, world, dish, csrf=admin.csrf)
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    other_family = login(world.beta.who("planner"))
    response = _csrf_request(planner, op_id, world, dish, csrf=other_family.csrf)
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert family_state_hash(owner, world.alfa) == before


@pytest.mark.parametrize("op_id", UNSAFE_OPS)
def test_the_anonymous_csrf_cookie_value_does_not_replace_the_session_token(
    op_id: str, world: World, login: Login, owner: Owner
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    planner = login(world.alfa.who("planner"))
    anonymous_value = planner.browser.cookies["__Host-csrf"]
    response = _csrf_request(planner, op_id, world, dish, csrf=anonymous_value)
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_get_operations_have_no_side_effects(world: World, login: Login, owner: Owner) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    planner = login(world.alfa.who("planner"))
    before = family_state_hash(owner, world.alfa)
    events = len(security_events(owner))
    for op_id in ("catalog.course.list", "catalog.dish.list", "catalog.dish.read"):
        assert send(planner, request_for(op_id, world.alfa, dish)).status_code == 200
    assert family_state_hash(owner, world.alfa) == before
    assert len(security_events(owner)) == events, "una lettura lecita non scrive nel registro"


def test_the_archive_has_no_delete_patch_or_other_methods_yet(
    world: World, login: Login, owner: Owner
) -> None:
    """SL-08 introdurrà `DELETE`; prima nessun metodo oltre a quelli del contratto."""
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    planner = login(world.alfa.who("planner"))
    for method, path in (
        ("DELETE", f"/api/v1/dishes/{dish}"),
        ("PATCH", f"/api/v1/dishes/{dish}"),
        ("PUT", "/api/v1/dishes"),
        ("POST", f"/api/v1/dishes/{dish}"),
        ("DELETE", "/api/v1/dishes"),
    ):
        response = planner.browser.request(
            method, path, json={}, csrf=planner.csrf, headers={"If-Match": '"1"'}
        )
        assert response.status_code in {404, 405}, (method, path, response.status_code)
    assert dish_row(owner, dish) is not None
    assert "access-control-allow-origin" not in planner.get("/api/v1/dishes").headers
