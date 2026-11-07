"""Contratto OpenAPI del piano (SL-06a; piano §4.2, §4.3; SR-060, ADR-0008, ADR-0009).

Tre operazioni: `plan.view.read` (`GET /plan`), `meal.view.read` (`GET /meals/{date}/{mealType}/
{slot}`), `meal.presence.write` (`PUT .../presence`). Il contratto è additivo: i campi M1/M2 di
`MealView` (`guests`, `attendance`, `covers`, `dislikeWarnings`) NON ci sono ancora. I nomi delle
operazioni sono proposti dal tester (rapporto, N-1).
"""

from typing import Any

import pytest

OPS = {
    ("get", "/api/v1/plan"): "plan.view.read",
    ("get", "/api/v1/meals/{date}/{mealType}/{slot}"): "meal.view.read",
    ("put", "/api/v1/meals/{date}/{mealType}/{slot}/presence"): "meal.presence.write",
}
M1_M2_FIELDS = {"guests", "attendance", "covers", "dislikeWarnings"}
PRESENCE = ("put", "/api/v1/meals/{date}/{mealType}/{slot}/presence")
MEAL = ("get", "/api/v1/meals/{date}/{mealType}/{slot}")


def _op(schema: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    item = schema["paths"].get(path)
    assert item is not None, f"{path} assente dal contratto"
    assert method in item, f"{method.upper()} {path} assente dal contratto"
    return item[method]  # type: ignore[no-any-return]


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        target: Any = schema
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def _response_schema(schema: dict[str, Any], op: dict[str, Any], status: str) -> dict[str, Any]:
    assert status in op["responses"], (status, list(op["responses"]))
    return _resolve(schema, op["responses"][status]["content"]["application/json"]["schema"])


@pytest.mark.parametrize(("method", "path"), sorted(OPS))
def test_operation_exists_with_family_scope(
    generated_schema: dict[str, Any], method: str, path: str
) -> None:
    op = _op(generated_schema, method, path)
    assert op["operationId"] == OPS[(method, path)]
    assert op["x-authz"]["scope"] == "family"


def test_reads_allow_every_role_and_the_write_is_for_admin_and_planner(
    generated_schema: dict[str, Any],
) -> None:
    for (method, path), op_id in OPS.items():
        roles = set(_op(generated_schema, method, path)["x-authz"]["roles"])
        if method == "get":
            assert roles == {"admin", "planner", "member"}, op_id
        else:
            assert roles == {"admin", "planner"}, op_id


def test_only_the_presence_write_tracks_and_it_tracks_meal_content(
    generated_schema: dict[str, Any],
) -> None:
    assert _op(generated_schema, *PRESENCE)["x-authz"]["tracks"] == ["meal_content"]
    for key in OPS:
        if key != PRESENCE:
            assert not _op(generated_schema, *key)["x-authz"].get("tracks"), key


def test_the_plan_declares_from_and_to_as_optional_query_dates(
    generated_schema: dict[str, Any],
) -> None:
    op = _op(generated_schema, "get", "/api/v1/plan")
    params = {p["name"]: p for p in op["parameters"]}
    assert set(params) == {"from", "to"}
    for param in params.values():
        assert param["in"] == "query"
        assert param.get("required", False) is False


def test_the_plan_documents_its_errors_including_range_too_large(
    generated_schema: dict[str, Any],
) -> None:
    op = _op(generated_schema, "get", "/api/v1/plan")
    assert {"200", "401", "422"} <= set(op["responses"]), list(op["responses"])
    assert "62" in op["responses"]["422"]["description"], "il limite SR-060 è documentato"


def test_plan_view_has_the_documented_fields(generated_schema: dict[str, Any]) -> None:
    view = _response_schema(generated_schema, _op(generated_schema, "get", "/api/v1/plan"), "200")
    assert {"from", "to", "today", "timezone", "days", "refs"} <= set(view["properties"])
    assert set(view["required"]) >= {"from", "to", "today", "timezone", "days", "refs"}


def test_meal_view_has_the_m0_fields_and_none_of_the_later_ones(
    generated_schema: dict[str, Any],
) -> None:
    meal = _response_schema(generated_schema, _op(generated_schema, *MEAL), "200")
    fields = set(meal["properties"])
    assert {
        "date", "mealType", "slot", "name", "present", "special", "contentVersion", "items", "past",
    } <= fields  # fmt: skip
    assert not fields & M1_M2_FIELDS, "guests, attendance e covers arrivano con M1"


def test_the_meal_read_returns_an_etag_and_404_for_an_invalid_slot(
    generated_schema: dict[str, Any],
) -> None:
    op = _op(generated_schema, *MEAL)
    assert "ETag" in op["responses"]["200"]["headers"]
    assert "404" in op["responses"]


def test_the_presence_body_is_closed_with_a_required_boolean(
    generated_schema: dict[str, Any],
) -> None:
    op = _op(generated_schema, *PRESENCE)
    content = op["requestBody"]["content"]
    assert set(content) == {"application/json"}
    body = _resolve(generated_schema, content["application/json"]["schema"])
    assert set(body["properties"]) == {"present"}
    assert body["properties"]["present"]["type"] == "boolean"
    assert body["required"] == ["present"]
    assert body.get("additionalProperties") is False, "mass assignment (SR-024)"


def test_the_presence_write_documents_if_match_etag_and_its_errors(
    generated_schema: dict[str, Any],
) -> None:
    op = _op(generated_schema, *PRESENCE)
    assert {"200", "401", "403", "404", "412", "422", "428", "429"} <= set(op["responses"])
    assert "ETag" in op["responses"]["200"]["headers"]
    meal = _response_schema(generated_schema, op, "200")
    assert "contentVersion" in meal["properties"]
