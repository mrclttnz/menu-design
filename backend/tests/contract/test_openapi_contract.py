"""Contratto OpenAPI e `x-authz` (piano §4.1; SR-009, SR-046; THR-110).

`openapi.json` è committato alla radice del repository e deve coincidere con lo schema generato.
"""

import json
import re
from typing import Any

from support.paths import BACKEND, REPO

HTTP_METHODS = {"get", "put", "post", "delete", "patch"}
SCOPES = {"public", "anonymous", "signup", "account", "family"}
ROLES = {"admin", "planner", "member"}
RULES = {"self", "if_present", "member_own_to_try"}
# Elenco chiuso delle rotte pubbliche (piano §4.1).
PUBLIC_INVENTORY = {
    ("get", "/healthz"),
    ("get", "/api/v1/session"),
    ("get", "/api/v1/auth/google/callback"),
}


def _operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method, path, op)
        for path, item in schema.get("paths", {}).items()
        for method, op in item.items()
        if method in HTTP_METHODS
    ]


def public_routes_outside_inventory(schema: dict[str, Any]) -> set[tuple[str, str]]:
    """Operazioni `public` non presenti nell'elenco chiuso (piano §4.1)."""
    public = {(m, p) for m, p, op in _operations(schema) if op["x-authz"]["scope"] == "public"}
    return public - PUBLIC_INVENTORY


def test_committed_openapi_exists_and_is_valid_json() -> None:
    path = REPO / "openapi.json"
    assert path.is_file(), "openapi.json mancante alla radice (contratto committato)"
    assert json.loads(path.read_text(encoding="utf-8"))["openapi"].startswith("3.1")


def test_committed_openapi_equals_generated(
    generated_schema: dict[str, Any], committed_schema: dict[str, Any]
) -> None:
    """CI: `openapi.json` senza differenze rispetto allo schema generato."""
    assert committed_schema == generated_schema


def test_export_script_exists() -> None:
    assert (BACKEND / "scripts" / "export_openapi.py").is_file()


def test_schema_is_openapi_3_1(generated_schema: dict[str, Any]) -> None:
    assert generated_schema["openapi"].startswith("3.1")


def test_healthz_is_declared_public(generated_schema: dict[str, Any]) -> None:
    op = generated_schema["paths"]["/healthz"]["get"]
    assert op["operationId"] == "platform.health.read"
    assert op["x-authz"]["scope"] == "public"


def test_there_is_at_least_one_operation(generated_schema: dict[str, Any]) -> None:
    assert _operations(generated_schema)


def test_every_operation_has_dotted_unique_operation_id(generated_schema: dict[str, Any]) -> None:
    ids = [op.get("operationId") for _, _, op in _operations(generated_schema)]
    assert all(isinstance(i, str) and re.fullmatch(r"[a-z_]+(\.[a-z_]+){2,}", i) for i in ids), ids
    assert len(ids) == len(set(ids))


def test_every_operation_declares_valid_x_authz(generated_schema: dict[str, Any]) -> None:
    ops = _operations(generated_schema)
    assert ops
    for method, path, op in ops:
        authz = op.get("x-authz")
        assert isinstance(authz, dict), f"{method} {path} senza x-authz"
        assert authz.get("scope") in SCOPES, f"{method} {path}"
        assert set(authz.get("roles", [])) <= ROLES, f"{method} {path}"
        assert set(authz.get("rules", [])) <= RULES, f"{method} {path}"
        assert authz.get("pendingDeletion", "allowed") in {"allowed", "blocked"}


def test_public_routes_are_exactly_the_closed_inventory_subset(
    generated_schema: dict[str, Any],
) -> None:
    assert ("get", "/healthz") in {
        (m, p) for m, p, op in _operations(generated_schema) if op["x-authz"]["scope"] == "public"
    }
    assert public_routes_outside_inventory(generated_schema) == set()


def test_inventory_check_catches_an_extra_public_route(app_env: None) -> None:
    from menu.app import create_app
    from support.probe import build_probe_router

    schema = create_app(extra_routers=[build_probe_router([])]).openapi()
    assert ("get", "/_probe/rogue-public") in public_routes_outside_inventory(schema)


def test_errors_are_published_only_as_problem_json(generated_schema: dict[str, Any]) -> None:
    for method, path, op in _operations(generated_schema):
        content = op["responses"]["default"]["content"]
        assert set(content) == {"application/problem+json"}, f"{method} {path}"
    assert "ProblemDetails" in generated_schema["components"]["schemas"]
    assert "ErrorCode" in generated_schema["components"]["schemas"]


def test_family_scope_operations_declare_roles(generated_schema: dict[str, Any]) -> None:
    for method, path, op in _operations(generated_schema):
        if op["x-authz"]["scope"] == "family":
            assert op["x-authz"].get("roles"), f"{method} {path}"
