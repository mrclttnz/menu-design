"""Matrice A/P/M del piano, CSRF e campi non scrivibili (SL-06a).

SR-008, SR-009 (negato per default, un test negativo per ogni cella «No»), SR-005 (ruolo riletto
a ogni richiesta), SR-023/THR-007 (CSRF e tipo di contenuto), THR-023 (escalation verticale),
AC-008.8 (il Membro non cambia i pasti: `403`). La matrice è `tests/security/authz_matrix.yaml`,
indipendente dal codice. Le operazioni del piano sono `plan.view.read`, `meal.view.read` e
`meal.presence.write` (nomi proposti dal tester).
"""

import importlib
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import pytest

from menu.common import AppError, ErrorCode
from support.accounts import security_events
from support.browser_sim import Browser
from support.ctx import make_ctx
from support.dishes import Actor, Who, World, event_rows
from support.matrix import MATRIX
from support.meals import (
    PLAN,
    TODAY,
    make_meal,
    meal_rows,
    meal_url,
    planning_state,
    presence_url,
)
from support.owner import Owner
from support.tracks import tracked_count

pytestmark = [pytest.mark.sec, pytest.mark.integration]
Login = Callable[[Who], Actor]

OPS = ["plan.view.read", "meal.view.read", "meal.presence.write"]
DAY = date(2026, 10, 24)
CELLS = [(op, role) for op in OPS for role in ("admin", "planner", "member")]


def _request(op_id: str) -> tuple[str, str, Any, str | None]:
    return {
        "plan.view.read": ("GET", PLAN, None, None),
        "meal.view.read": ("GET", meal_url(DAY, "dinner"), None, None),
        "meal.presence.write": ("PUT", presence_url(DAY, "dinner"), {"present": False}, '"0"'),
    }[op_id]


def _send(actor: Actor, op_id: str, **kw: Any) -> Any:
    method, path, body, if_match = _request(op_id)
    headers = {"If-Match": if_match} if if_match else {}
    if method == "GET":
        return actor.get(path, **kw)
    return actor.browser.request(
        method, path, json=body, headers=headers, **({"csrf": actor.csrf} | kw)
    )


def test_the_matrix_has_the_three_planning_operations_with_the_documented_shape() -> None:
    assert {op for op in MATRIX if op.split(".")[0] in {"plan", "meal"}} == set(OPS)
    assert MATRIX["meal.presence.write"]["cells"] == {
        "admin": "allow",
        "planner": "allow",
        "member": 403,
    }
    assert MATRIX["meal.presence.write"]["tracks"] == ["meal_content"]


@pytest.fixture
def seeded(meal_world: World, owner: Owner) -> World:
    make_meal(owner, meal_world.alfa, DAY, "lunch", content_version=1)
    return meal_world


# --- anonimo: 401 su ogni operazione --------------------------------------------------------------


@pytest.mark.parametrize("op_id", OPS)
def test_anonymous_gets_401_and_no_side_effect(
    op_id: str, seeded: World, auth_client: Any, owner: Owner
) -> None:
    anonymous = Browser(auth_client)
    token = anonymous.anonymous_csrf()
    method, path, body, if_match = _request(op_id)
    state = planning_state(owner, seeded.alfa)
    kw: dict[str, Any] = {} if method == "GET" else {"csrf": token}
    headers = {"If-Match": if_match} if if_match else {}
    response = anonymous.request(method, path, json=body, headers=headers, **kw)
    assert response.status_code == 401, (op_id, response.status_code, response.text)
    assert response.json()["code"] == "unauthenticated"
    assert planning_state(owner, seeded.alfa) == state
    assert event_rows(owner) == []
    assert not [c for c in anonymous.last_cookies if c.name == "__Host-session"]


def test_an_unknown_session_cookie_is_401_on_the_plan(seeded: World, auth_client: Any) -> None:
    stranger = Browser(auth_client)
    stranger.cookies["__Host-session"] = "x" * 43
    assert stranger.get(PLAN).status_code == 401


# --- matrice ruolo x operazione -------------------------------------------------------------------


@pytest.mark.parametrize(("op_id", "role"), CELLS)
def test_role_matrix(op_id: str, role: str, seeded: World, login: Login, owner: Owner) -> None:
    expected = MATRIX[op_id]["cells"][role]
    actor = login(seeded.alfa.who(role))
    state = planning_state(owner, seeded.alfa)
    response = _send(actor, op_id)
    if expected == "allow":
        assert response.status_code == 200, (op_id, role, response.status_code, response.text)
        assert response.headers["cache-control"] == "no-store"
        return
    assert expected == 403
    assert response.status_code == 403, (op_id, role, response.status_code, response.text)
    assert response.json()["code"] == "forbidden"
    assert planning_state(owner, seeded.alfa) == state, "una cella «No» non deve avere effetti"
    assert event_rows(owner) == []
    assert tracked_count(owner, seeded.alfa.id) == 0, "un 403 non consuma il tetto (SR-070)"
    denied = security_events(owner, "access.denied")
    assert denied, "manca l'evento access.denied"
    event = denied[-1]
    assert (event["outcome"], event["actor_kind"], event["actor_role"]) == (
        "denied",
        "account",
        role,
    )
    assert event["family_id"] == seeded.alfa.id
    assert event["actor_account_id"] == seeded.alfa.who(role).account


def test_ac_008_8_a_member_is_refused_before_any_validation_leak(
    seeded: World, login: Login, owner: Owner
) -> None:
    """Il permesso si controlla prima del merito e prima di `If-Match`."""
    member = login(seeded.alfa.who("member"))
    for body, if_match in (
        ({"present": "boh"}, None),
        ({}, "abc"),
        ({"present": False, "role": "admin"}, 0),
    ):
        got = member.put(presence_url(DAY, "dinner"), body, if_match=if_match)
        assert got.status_code == 403, (body, if_match, got.status_code, got.text)
    assert meal_rows(owner, seeded.alfa)[0]["content_version"] == 1


def test_a_member_cannot_touch_the_meal_with_any_other_method(
    seeded: World, login: Login, owner: Owner
) -> None:
    member = login(seeded.alfa.who("member"))
    state = planning_state(owner, seeded.alfa)
    for method in ("POST", "PATCH", "DELETE"):
        got = member.browser.request(
            method, presence_url(DAY, "dinner"), json={"present": False},
            headers={"If-Match": '"0"'}, csrf=member.csrf,
        )  # fmt: skip
        assert got.status_code in {403, 404, 405}, (method, got.status_code)
    assert planning_state(owner, seeded.alfa) == state


# --- ruolo e appartenenza riletti a ogni richiesta (SR-005, THR-023) ------------------------------


def test_a_demoted_planner_loses_the_write_on_the_next_request_but_still_reads(
    seeded: World, login: Login, owner: Owner
) -> None:
    planner = login(seeded.alfa.who("planner"))
    assert (
        planner.put(presence_url(DAY, "dinner"), {"present": False}, if_match=0).status_code == 200
    )
    owner.execute(
        "update app.person set role = 'member' where id = %s", (seeded.alfa.who("planner").person,)
    )
    refused = planner.put(presence_url(DAY, "dinner"), {"present": True}, if_match=1)
    assert refused.status_code == 403, refused.text
    assert planner.get(PLAN).status_code == 200
    assert len(event_rows(owner)) == 1


def test_a_promoted_member_can_write_on_the_next_request(
    seeded: World, login: Login, owner: Owner
) -> None:
    member = login(seeded.alfa.who("member"))
    assert (
        member.put(presence_url(DAY, "dinner"), {"present": False}, if_match=0).status_code == 403
    )
    owner.execute(
        "update app.person set role = 'planner' where id = %s", (seeded.alfa.who("member").person,)
    )
    assert (
        member.put(presence_url(DAY, "dinner"), {"present": False}, if_match=0).status_code == 200
    )


def test_a_person_removed_from_the_family_cannot_read_or_change_the_plan(
    seeded: World, login: Login, owner: Owner
) -> None:
    planner = login(seeded.alfa.who("planner"))
    owner.execute(
        "update app.person set status = 'former', account_id = null, role = null, "
        "former_reason = 'removed' where id = %s",
        (seeded.alfa.who("planner").person,),
    )
    for response in (
        planner.get(PLAN),
        planner.get(meal_url(DAY, "dinner")),
        planner.put(presence_url(DAY, "dinner"), {"present": False}, if_match=0),
    ):
        assert response.status_code in {403, 404}, response.status_code
    assert event_rows(owner) == []


# --- CSRF e tipo di contenuto sulla scrittura (SR-023, THR-007; 08 §7.2) --------------------------


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
def test_the_presence_write_rejects_csrf_and_media_type_attacks(
    label: str,
    override: dict[str, Any],
    status: int,
    code: str,
    seeded: World,
    login: Login,
    owner: Owner,
) -> None:
    planner = login(seeded.alfa.who("planner"))
    state = planning_state(owner, seeded.alfa)
    response = _send(planner, "meal.presence.write", **override)
    assert response.status_code == status, (label, response.status_code, response.text)
    assert response.json()["code"] == code
    assert planning_state(owner, seeded.alfa) == state, label
    assert event_rows(owner) == []
    assert tracked_count(owner, seeded.alfa.id) == 0


def test_the_csrf_token_of_another_session_or_the_anonymous_cookie_is_refused(
    seeded: World, login: Login, owner: Owner
) -> None:
    planner = login(seeded.alfa.who("planner"))
    admin = login(seeded.alfa.who("admin"))
    other_family = login(seeded.beta.who("planner"))
    for token in (admin.csrf, other_family.csrf, planner.browser.cookies["__Host-csrf"]):
        response = _send(planner, "meal.presence.write", csrf=token)
        assert response.status_code == 403
        assert response.json()["code"] == "csrf_failed"
    assert event_rows(owner) == []


def test_reads_have_no_side_effects_and_write_nothing_in_the_security_log(
    seeded: World, login: Login, owner: Owner
) -> None:
    planner = login(seeded.alfa.who("planner"))
    state = planning_state(owner, seeded.alfa)
    events = len(security_events(owner))
    for op_id in ("plan.view.read", "meal.view.read"):
        assert _send(planner, op_id).status_code == 200
    assert planning_state(owner, seeded.alfa) == state
    assert len(security_events(owner)) == events
    assert meal_rows(owner, seeded.alfa)[0]["content_version"] == 1


def test_no_cors_headers_on_the_planning_routes(seeded: World, login: Login) -> None:
    planner = login(seeded.alfa.who("planner"))
    assert "access-control-allow-origin" not in planner.get(PLAN).headers
    assert "access-control-allow-origin" not in planner.get(meal_url(TODAY)).headers


# --- `menu.access.authorize` per le operazioni del piano ------------------------------------------


@pytest.fixture
def tenancy(app_url: str) -> Iterator[Any]:
    module: Any = importlib.import_module("menu.tenancy")
    module.init(app_url)
    try:
        yield module
    finally:
        module.dispose()


@pytest.mark.parametrize(("op_id", "role"), CELLS)
def test_access_authorize_follows_the_matrix_for_the_planning_operations(
    op_id: str, role: str, tenancy: Any, seeded: World, owner: Owner
) -> None:
    access: Any = importlib.import_module("menu.access")
    who = seeded.alfa.who(role)
    ctx = make_ctx(seeded.alfa.id, who.account, role)  # type: ignore[arg-type]
    if MATRIX[op_id]["cells"][role] == "allow":
        assert access.authorize(ctx, op_id) is None
        return
    with pytest.raises(AppError) as raised:
        access.authorize(ctx, op_id)
    assert raised.value.code == ErrorCode.FORBIDDEN


def test_an_unknown_planning_operation_is_denied_by_default(tenancy: Any, seeded: World) -> None:
    access: Any = importlib.import_module("menu.access")
    who = seeded.alfa.who("admin")
    ctx = make_ctx(seeded.alfa.id, who.account, "admin")
    with pytest.raises((AppError, KeyError)):
        access.authorize(ctx, "meal.presence.erase")
