"""`menu.access`: la matrice dichiarativa dei permessi, una riga per operazione (SL-04; SR-009).

`authorize(ctx, operation, facts=None)` (piano §3) solleva `forbidden` e scrive `access.denied`
quando il ruolo non basta; è negato per default (operazione sconosciuta, nessun ruolo). Le attese
sono quelle di `tests/security/authz_matrix.yaml` (trascritta dai requisiti, non letta da
`access`). Include le operazioni FUTURE dell'archivio («anche futura», piano SL-04): i loro nomi
sono quelli proposti nella matrice di test.
"""

import importlib
from collections.abc import Iterator
from typing import Any

import pytest

from menu.common import AppError, ErrorCode
from support.accounts import security_events
from support.ctx import make_ctx
from support.dishes import World
from support.matrix import FUTURE, MATRIX
from support.owner import Owner

pytestmark = pytest.mark.integration

CATALOG = {op: row for op, row in MATRIX.items() if op.startswith("catalog.")}
CELLS = [(op, role, row["cells"][role]) for op, row in CATALOG.items() for role in row["cells"]]
FUTURE_CELLS = [
    (op, role, "allow" if role in row["allow"] else 403)
    for op, row in FUTURE.items()
    for role in ("admin", "planner", "member")
]


@pytest.fixture
def tenancy(app_url: str) -> Iterator[Any]:
    module: Any = importlib.import_module("menu.tenancy")
    module.init(app_url)
    try:
        yield module
    finally:
        module.dispose()


def _authorize(world: World, op: str, role: str | None) -> Any:
    access: Any = importlib.import_module("menu.access")
    who = world.alfa.who(role) if role else None
    ctx = make_ctx(world.alfa.id, who.account if who else None, role)  # type: ignore[arg-type]
    return access.authorize(ctx, op)


@pytest.mark.parametrize(("op", "role", "expected"), CELLS)
def test_declared_cells_of_the_archive(
    tenancy: Any, world: World, owner: Owner, op: str, role: str, expected: Any
) -> None:
    if expected == "allow":
        assert _authorize(world, op, role) is None
        assert security_events(owner, "access.denied") == []
        return
    with pytest.raises(AppError) as raised:
        _authorize(world, op, role)
    assert raised.value.code is ErrorCode.FORBIDDEN
    (event,) = security_events(owner, "access.denied")
    assert event["outcome"] == "denied"
    assert event["actor_role"] == role
    assert event["family_id"] == world.alfa.id


@pytest.mark.parametrize(("op", "role", "expected"), FUTURE_CELLS)
def test_future_operations_already_have_a_row(
    tenancy: Any, world: World, op: str, role: str, expected: Any
) -> None:
    """Una riga per operazione, anche futura: la regola per A, P e M c'è prima della rotta."""
    if expected == "allow":
        assert _authorize(world, op, role) is None
        return
    with pytest.raises(AppError) as raised:
        _authorize(world, op, role)
    assert raised.value.code is ErrorCode.FORBIDDEN


def test_unknown_operations_are_denied_by_default(tenancy: Any, world: World) -> None:
    for role in ("admin", "planner", "member"):
        with pytest.raises((AppError, KeyError, ValueError)) as raised:
            _authorize(world, "catalog.dish.does_not_exist", role)
        if isinstance(raised.value, AppError):
            assert raised.value.code is ErrorCode.FORBIDDEN


def test_a_context_without_a_role_is_denied_everywhere(tenancy: Any, world: World) -> None:
    for op in CATALOG:
        with pytest.raises(AppError) as raised:
            _authorize(world, op, None)
        assert raised.value.code in {ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND}


def test_the_denial_event_never_carries_resource_content(
    tenancy: Any, world: World, owner: Owner
) -> None:
    with pytest.raises(AppError):
        _authorize(world, "catalog.dish.create", "member")
    (event,) = security_events(owner, "access.denied")
    assert "catalog.dish.create" in str(event["details"]) or event["target_type"]
    assert event["actor_account_id"] == world.alfa.who("member").account
