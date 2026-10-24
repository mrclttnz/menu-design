"""Contratto OpenAPI dell'archivio piatti (SL-04; piano §4.2, §4.3; SR-010, SR-024, SR-060).

Sei operazioni: `catalog.course.list`, `catalog.dish.list|create|read|update` e, da SL-05,
`catalog.dish.set_status` (`POST /dishes/{dishId}/status`). Il contratto
è additivo: i campi M1/M2 (`priority`, `tagIds`, `likes`, `promotionProposed`) NON ci sono ancora.
I limiti di AC-004.5 e SR-060 sono nello schema, non solo nel codice.
"""

from typing import Any

import pytest

OPS = {
    ("get", "/api/v1/courses"): "catalog.course.list",
    ("get", "/api/v1/dishes"): "catalog.dish.list",
    ("post", "/api/v1/dishes"): "catalog.dish.create",
    ("get", "/api/v1/dishes/{dishId}"): "catalog.dish.read",
    ("put", "/api/v1/dishes/{dishId}"): "catalog.dish.update",
    ("post", "/api/v1/dishes/{dishId}/status"): "catalog.dish.set_status",  # SL-05
}
M1_M2_FIELDS = {"priority", "tagIds", "likes", "promotionProposed", "promotionDismissedOn"}


def _op(schema: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    item = schema["paths"].get(path)
    assert item is not None, f"{path} assente dal contratto"
    assert method in item, f"{method.upper()} {path} assente dal contratto"
    return item[method]  # type: ignore[no-any-return]


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    while True:
        if "$ref" in node:
            target: Any = schema
            for part in node["$ref"].removeprefix("#/").split("/"):
                target = target[part]
            node = target
            continue
        for key in ("anyOf", "oneOf"):
            options = [o for o in node.get(key, []) if o.get("type") != "null"]
            if len(options) == 1 and len(node.get(key, [])) == 2:
                node = options[0]
                break
        else:
            return node


def _body(schema: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    content = op["requestBody"]["content"]
    assert set(content) == {"application/json"}
    return _resolve(schema, content["application/json"]["schema"])


def _response(schema: dict[str, Any], op: dict[str, Any], status: str) -> dict[str, Any]:
    assert status in op["responses"], (status, list(op["responses"]))
    return _resolve(schema, op["responses"][status]["content"]["application/json"]["schema"])


@pytest.mark.parametrize(("method", "path"), sorted(OPS))
def test_operation_exists_with_family_scope(
    generated_schema: dict[str, Any], method: str, path: str
) -> None:
    op = _op(generated_schema, method, path)
    assert op["operationId"] == OPS[(method, path)]
    assert op["x-authz"]["scope"] == "family"
    assert {"admin", "planner"} <= set(op["x-authz"]["roles"])


def test_reads_allow_every_role_and_writes_are_for_admin_and_planner_in_sl04(
    generated_schema: dict[str, Any],
) -> None:
    for (method, path), op_id in OPS.items():
        roles = set(_op(generated_schema, method, path)["x-authz"]["roles"])
        if method == "get":
            assert roles == {"admin", "planner", "member"}, op_id
        else:
            assert roles == {"admin", "planner"}, "il Membro arriva con SL-17 (member_own_to_try)"


def test_create_body_is_closed_and_declares_the_limits(generated_schema: dict[str, Any]) -> None:
    body = _body(generated_schema, _op(generated_schema, "post", "/api/v1/dishes"))
    assert body.get("additionalProperties") is False, "extra='forbid' (SR-010)"
    props = body["properties"]
    assert set(props) == {"name", "courseIds", "notes", "prepTime", "sources", "status"}
    assert set(body["required"]) >= {"name", "courseIds"}
    assert props["name"]["maxLength"] == 120
    assert _resolve(generated_schema, props["notes"])["maxLength"] == 2000
    assert _resolve(generated_schema, props["sources"])["maxItems"] == 10
    assert _resolve(generated_schema, props["courseIds"])["minItems"] == 1


def test_update_body_has_no_status_and_requires_if_match(generated_schema: dict[str, Any]) -> None:
    op = _op(generated_schema, "put", "/api/v1/dishes/{dishId}")
    body = _body(generated_schema, op)
    assert body.get("additionalProperties") is False
    assert "status" not in body["properties"], "lo stato cambia con POST /status (SL-05)"
    assert M1_M2_FIELDS.isdisjoint(body["properties"])
    headers = {p["name"] for p in op.get("parameters", []) if p["in"] == "header"}
    assert "If-Match" in headers


def test_source_item_shape(generated_schema: dict[str, Any]) -> None:
    body = _body(generated_schema, _op(generated_schema, "post", "/api/v1/dishes"))
    items = _resolve(
        generated_schema, _resolve(generated_schema, body["properties"]["sources"])["items"]
    )
    assert items.get("additionalProperties") is False
    assert set(items["properties"]) == {"kind", "reference", "page", "note"}
    assert set(items["required"]) == {"kind", "reference"}
    kind = _resolve(generated_schema, items["properties"]["kind"])
    assert set(kind["enum"]) == {"link", "book", "magazine", "other"}
    assert items["properties"]["reference"]["maxLength"] == 500


def test_detail_response_has_the_documented_fields_and_no_future_ones(
    generated_schema: dict[str, Any],
) -> None:
    for method, path, status in (
        ("post", "/api/v1/dishes", "201"),
        ("get", "/api/v1/dishes/{dishId}", "200"),
        ("put", "/api/v1/dishes/{dishId}", "200"),
    ):
        detail = _response(generated_schema, _op(generated_schema, method, path), status)
        props = set(detail["properties"])
        assert {
            "id",
            "name",
            "status",
            "courseIds",
            "archived",
            "everPlanned",
            "sources",
            "createdBy",
            "version",
        } <= props, (method, path, props)
        assert {"notes", "prepTime"} <= props
        assert M1_M2_FIELDS.isdisjoint(props), props
        assert "familyId" not in props
        assert "family_id" not in props


def test_list_has_the_documented_query_parameters_and_page_shape(
    generated_schema: dict[str, Any],
) -> None:
    op = _op(generated_schema, "get", "/api/v1/dishes")
    params = {p["name"]: p for p in op["parameters"] if p["in"] == "query"}
    assert {"q", "courseId", "status", "archived", "cursor", "limit"} <= set(params)
    assert M1_M2_FIELDS.isdisjoint(params)
    limit = _resolve(generated_schema, params["limit"]["schema"])
    assert limit["maximum"] == 100
    assert limit["minimum"] >= 1
    page = _response(generated_schema, op, "200")
    assert set(page["properties"]) == {"items", "nextCursor"}
    summary = _resolve(generated_schema, page["properties"]["items"]["items"])
    assert {"id", "name", "status", "courseIds", "archived", "everPlanned"} <= set(
        summary["properties"]
    )
    assert "notes" not in summary["properties"], "l'elenco è DishSummary (senza note né fonti)"
    assert "sources" not in summary["properties"]


def test_course_list_shape(generated_schema: dict[str, Any]) -> None:
    page = _response(generated_schema, _op(generated_schema, "get", "/api/v1/courses"), "200")
    assert set(page["properties"]) == {"items"}
    course = _resolve(generated_schema, page["properties"]["items"]["items"])
    assert set(course["properties"]) == {"id", "baseCode", "name"}


def test_there_is_no_delete_archive_or_restore_operation_yet(
    generated_schema: dict[str, Any],
) -> None:
    """SL-08 (archive, restore, delete) arriva dopo: non anticiparle. Lo stato è di SL-05."""
    item = generated_schema["paths"].get("/api/v1/dishes/{dishId}", {})
    assert set(item) == {"get", "put"}
    for suffix in ("archive", "restore"):
        assert f"/api/v1/dishes/{{dishId}}/{suffix}" not in generated_schema["paths"]


# --- SL-05: POST /dishes/{dishId}/status ---------------------------------------------------------

STATUS_PATH = "/api/v1/dishes/{dishId}/status"


def test_status_body_is_closed_with_a_required_two_valued_status(
    generated_schema: dict[str, Any],
) -> None:
    op = _op(generated_schema, "post", STATUS_PATH)
    body = _body(generated_schema, op)
    assert body.get("additionalProperties") is False, "extra='forbid' (SR-010)"
    assert set(body["properties"]) == {"status"}
    assert body["required"] == ["status"]
    status = _resolve(generated_schema, body["properties"]["status"])
    assert set(status["enum"]) == {"to_try", "tested"}


def test_status_requires_if_match_and_documents_its_errors(
    generated_schema: dict[str, Any],
) -> None:
    op = _op(generated_schema, "post", STATUS_PATH)
    headers = {p["name"] for p in op.get("parameters", []) if p["in"] == "header"}
    assert "If-Match" in headers
    assert {"200", "401", "403", "404", "412", "422", "428", "429"} <= set(op["responses"])


def test_status_returns_a_dish_detail_with_etag(generated_schema: dict[str, Any]) -> None:
    op = _op(generated_schema, "post", STATUS_PATH)
    detail = _response(generated_schema, op, "200")
    read = _response(
        generated_schema, _op(generated_schema, "get", "/api/v1/dishes/{dishId}"), "200"
    )
    assert detail == read, "stessa forma di GET /dishes/{dishId} (DishDetail)"
    assert "ETag" in op["responses"]["200"].get("headers", {})


def test_status_declares_tracks_and_the_matrix_roles(generated_schema: dict[str, Any]) -> None:
    authz = _op(generated_schema, "post", STATUS_PATH)["x-authz"]
    assert authz["scope"] == "family"
    assert set(authz["roles"]) == {"admin", "planner"}
    assert "dish" in authz["tracks"], "T(dish): scrive un evento di modifica (ADR-0012)"
