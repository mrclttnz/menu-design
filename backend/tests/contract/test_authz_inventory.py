"""Inventario delle rotte contro la matrice dei test (08 §6.1, SR-009, THR-023).

L'insieme degli `operationId` dello schema generato coincide con le righe di
`tests/security/authz_matrix.yaml` (trascritta dai requisiti, indipendente dal codice), e per
ogni operazione `x-authz` coincide con la riga: un allargamento dei permessi nel codice, una rotta
senza riga nella matrice o una riga senza rotta fanno fallire il test. Il controllo sa fallire:
le sue funzioni pure sono provate su schemi sintetici in fondo al file.
"""

import re
from typing import Any

import pytest

from support.matrix import MATRIX, operations_of

OPERATION_ID = re.compile(r"^[a-z]+\.[a-z_]+\.[a-z_]+$")


def inventory_problems(schema: dict[str, Any], matrix: dict[str, dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    found = {op["operationId"]: (m, p, op) for m, p, op in operations_of(schema)}
    for op_id in sorted(set(found) - set(matrix)):
        problems.append(f"{op_id}: operazione senza riga nella matrice dei test")
    for op_id in sorted(set(matrix) - set(found)):
        problems.append(f"{op_id}: riga della matrice senza operazione nello schema")
    for op_id in sorted(set(found) & set(matrix)):
        method, path, op = found[op_id]
        row = matrix[op_id]
        authz = op.get("x-authz", {})
        if (method, path) != (row["method"], row["path"]):
            problems.append(f"{op_id}: rotta {method.upper()} {path} diversa dalla matrice")
        if authz.get("scope") != row["scope"]:
            problems.append(f"{op_id}: scope {authz.get('scope')!r} invece di {row['scope']!r}")
        if set(authz.get("roles", [])) != set(row["roles"]):
            problems.append(f"{op_id}: ruoli {authz.get('roles', [])} diversi dalla matrice")
        if set(authz.get("rules", [])) != set(row["rules"]):
            problems.append(f"{op_id}: regole {authz.get('rules', [])} diverse dalla matrice")
        if not OPERATION_ID.match(op_id):
            problems.append(f"{op_id}: formato area.risorsa.azione non rispettato")
    return problems


def test_every_operation_is_in_the_test_matrix_and_declares_the_same_authz(
    generated_schema: dict[str, Any],
) -> None:
    assert inventory_problems(generated_schema, MATRIX) == []


def test_the_archive_operations_of_sl04_exist(generated_schema: dict[str, Any]) -> None:
    ids = {op["operationId"] for _, _, op in operations_of(generated_schema)}
    assert {
        "catalog.course.list",
        "catalog.dish.list",
        "catalog.dish.create",
        "catalog.dish.read",
        "catalog.dish.update",
    } <= ids


def test_family_scope_operations_declare_at_least_one_role(
    generated_schema: dict[str, Any],
) -> None:
    for _, path, op in operations_of(generated_schema):
        authz = op["x-authz"]
        if authz["scope"] == "family":
            assert authz.get("roles"), f"{path}: scope family senza ruoli (negato per default)"


def test_every_write_of_the_archive_declares_pending_deletion_allowed_or_blocked(
    generated_schema: dict[str, Any],
) -> None:
    """Da SL-31 `pendingDeletion` è obbligatorio ovunque; prima, se c'è, ha un valore valido."""
    for _, path, op in operations_of(generated_schema):
        value = op["x-authz"].get("pendingDeletion", "allowed")
        assert value in {"allowed", "blocked"}, path


def test_dish_writes_do_not_track_change_events_before_sl05(
    generated_schema: dict[str, Any],
) -> None:
    """SL-04 non scrive eventi di modifica: `tracks` arriva con SL-05 (piano)."""
    for op_id in ("catalog.dish.create", "catalog.dish.update"):
        found = [x[2] for x in operations_of(generated_schema) if x[2]["operationId"] == op_id]
        assert found, f"{op_id} assente dal contratto"
        assert not found[0]["x-authz"].get("tracks"), op_id


# --- il controllo sa fallire (provato su schemi sintetici) --------------------------------------


def _schema(authz: dict[str, Any], op_id: str = "catalog.dish.read") -> dict[str, Any]:
    return {"paths": {"/api/v1/dishes/{dishId}": {"get": {"operationId": op_id, "x-authz": authz}}}}


def _row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "method": "get",
        "path": "/api/v1/dishes/{dishId}",
        "scope": "family",
        "roles": ["admin", "planner", "member"],
        "rules": [],
    }
    row.update(over)
    return row


GOOD = {"scope": "family", "roles": ["admin", "planner", "member"]}


def test_inventory_accepts_a_matching_operation() -> None:
    assert inventory_problems(_schema(GOOD), {"catalog.dish.read": _row()}) == []


@pytest.mark.parametrize(
    ("authz", "row", "expected"),
    [
        ({**GOOD, "roles": ["admin", "planner", "member", "x"]}, {}, "ruoli"),
        ({**GOOD, "roles": ["admin"]}, {}, "ruoli"),
        ({**GOOD, "rules": ["self"]}, {}, "regole"),
        ({**GOOD, "scope": "account"}, {}, "scope"),
        (GOOD, {"path": "/api/v1/altro"}, "rotta"),
    ],
)
def test_inventory_flags_each_kind_of_drift(
    authz: dict[str, Any], row: dict[str, Any], expected: str
) -> None:
    problems = inventory_problems(_schema(authz), {"catalog.dish.read": _row(**row)})
    assert any(expected in p for p in problems), problems


def test_inventory_flags_an_operation_missing_from_the_matrix_and_the_reverse() -> None:
    problems = inventory_problems(_schema(GOOD), {})
    assert "catalog.dish.read: operazione senza riga nella matrice dei test" in problems
    problems = inventory_problems({"paths": {}}, {"catalog.dish.read": _row()})
    assert "catalog.dish.read: riga della matrice senza operazione nello schema" in problems
