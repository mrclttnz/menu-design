"""Contratto OpenAPI dell'accesso (SL-03a; piano §4.1, §4.3; ADR-0004 rev. 3; SR-023).

Le quattro operazioni, il loro `x-authz` e la forma di richieste e risposte. I nomi degli
`operationId` sono parte del contratto (piano §4.1: formato `<area>.<risorsa>.<azione>`):
`identity.session.read`, `identity.google.start`, `identity.google.callback`,
`identity.session.logout`. Il file `openapi.json` committato è confrontato con lo schema
generato da `test_openapi_contract.py` (rigenerarlo con `make openapi`).
"""

import re
from typing import Any

import pytest

OPERATIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("get", "/api/v1/session"): ("identity.session.read", "public"),
    ("post", "/api/v1/auth/google/start"): ("identity.google.start", "anonymous"),
    ("get", "/api/v1/auth/google/callback"): ("identity.google.callback", "public"),
    ("post", "/api/v1/auth/logout"): ("identity.session.logout", "account"),
}
OPERATION_ID = re.compile(r"^[a-z]+\.[a-z_]+\.[a-z_]+$")


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


def _body_schema(schema: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    content = op["requestBody"]["content"]
    assert set(content) == {"application/json"}, "i POST accettano solo application/json (415)"
    return _resolve(schema, content["application/json"]["schema"])


@pytest.mark.parametrize(("method", "path"), sorted(OPERATIONS))
def test_login_operations_exist_with_the_declared_operation_id_and_scope(
    generated_schema: dict[str, Any], method: str, path: str
) -> None:
    operation_id, scope = OPERATIONS[(method, path)]
    op = _op(generated_schema, method, path)
    assert op["operationId"] == operation_id
    assert OPERATION_ID.match(op["operationId"])
    assert op["x-authz"]["scope"] == scope


def test_logout_is_account_scoped_and_allowed_during_pending_deletion(
    generated_schema: dict[str, Any],
) -> None:
    authz = _op(generated_schema, "post", "/api/v1/auth/logout")["x-authz"]
    assert authz.get("reauth", False) is False
    assert authz.get("pendingDeletion", "allowed") == "allowed"
    assert "tracks" not in authz or authz["tracks"] == []


def test_only_the_planned_login_routes_are_public_or_anonymous(
    generated_schema: dict[str, Any],
) -> None:
    """Elenco chiuso (piano §4.1, 08 §6.8): `identity` non apre altre rotte senza sessione."""
    open_routes = {
        (method, path)
        for path, item in generated_schema["paths"].items()
        for method, op in item.items()
        if path.startswith("/api/v1/auth") or path == "/api/v1/session"
        if op["x-authz"]["scope"] in {"public", "anonymous"}
    }
    assert open_routes == {k for k, v in OPERATIONS.items() if v[1] in {"public", "anonymous"}}


def test_no_get_route_changes_state_and_logout_is_not_a_get(
    generated_schema: dict[str, Any],
) -> None:
    """THR-007: nessun `GET` con effetti (logout compreso); il callback è l'unico `GET` di auth."""
    paths = generated_schema["paths"]
    assert "post" in paths.get("/api/v1/auth/logout", {}), "logout assente dal contratto"
    assert set(paths["/api/v1/auth/logout"]) == {"post"}
    assert set(paths.get("/api/v1/auth/google/start", {})) == {"post"}
    assert set(paths.get("/api/v1/auth/google/callback", {})) == {"get"}, "il callback è solo GET"


def test_start_request_body_is_closed_and_has_a_fixed_purpose_vocabulary(
    generated_schema: dict[str, Any],
) -> None:
    """ADR-0004 rev. 3 punto 2 e ASM-075: `login` o `reauth`, mai `invite` su questa rotta."""
    body = _body_schema(
        generated_schema, _op(generated_schema, "post", "/api/v1/auth/google/start")
    )
    assert body.get("additionalProperties") is False, "extra='forbid' (SR-010)"
    assert set(body["properties"]) == {"purpose", "returnTo"}
    assert body["required"] == ["purpose"]
    purpose = _resolve(generated_schema, body["properties"]["purpose"])
    assert set(purpose["enum"]) == {"login", "reauth"}


def test_start_response_is_a_redirect_url_and_logout_has_no_content(
    generated_schema: dict[str, Any],
) -> None:
    start = _op(generated_schema, "post", "/api/v1/auth/google/start")
    ok = _resolve(
        generated_schema, start["responses"]["200"]["content"]["application/json"]["schema"]
    )
    assert set(ok["properties"]) == {"redirectUrl"}
    logout = _op(generated_schema, "post", "/api/v1/auth/logout")
    assert "204" in logout["responses"]
    assert "200" not in logout["responses"]
    assert "content" not in logout["responses"]["204"]


def test_logout_takes_an_empty_closed_json_body(generated_schema: dict[str, Any]) -> None:
    """Piano §4.3: richiesta `{}`; un corpo con campi estranei è `422 unknown_field`."""
    body = _body_schema(generated_schema, _op(generated_schema, "post", "/api/v1/auth/logout"))
    assert body.get("additionalProperties") is False
    assert not body.get("properties")


def test_callback_parameters_are_all_optional_so_it_can_always_redirect(
    generated_schema: dict[str, Any],
) -> None:
    """Il callback risponde sempre `302` (piano §4.3): un parametro obbligatorio darebbe `422`."""
    op = _op(generated_schema, "get", "/api/v1/auth/google/callback")
    params = {p["name"]: p for p in op.get("parameters", [])}
    assert {"code", "state", "error"} <= set(params)
    assert not [n for n, p in params.items() if p.get("required")], "tutti facoltativi"
    assert "302" in op["responses"]


def _property_names(schema: dict[str, Any], node: Any, seen: set[str] | None = None) -> set[str]:
    """Tutti i nomi di proprietà raggiungibili da `node`, seguendo `$ref`, `oneOf`, `items`."""
    seen = set() if seen is None else seen
    names: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in seen:
                return names
            seen.add(ref)
            return _property_names(schema, _resolve(schema, node), seen)
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                names |= set(value)
            names |= _property_names(schema, value, seen)
    elif isinstance(node, list):
        for item in node:
            names |= _property_names(schema, item, seen)
    return names


def test_session_read_documents_the_authenticated_and_anonymous_shapes(
    generated_schema: dict[str, Any],
) -> None:
    """SessionView (piano §4.2): anonima `{authenticated: false, notices: []}`, oppure con sessione.

    L'esito di autenticazione compare anche nella forma anonima: un accesso non riuscito
    lascia anonimi, ma la SPA deve poterne leggere l'esito (ADR-0004 rev. 3, punto 3).
    """
    op = _op(generated_schema, "get", "/api/v1/session")
    names = _property_names(generated_schema, op["responses"]["200"]["content"])
    assert {
        "authenticated",
        "csrfToken",
        "account",
        "displayName",
        "family",
        "person",
        "role",
        "privacyReviewRequired",
        "authOutcome",
        "notices",
    } <= names
    assert not {n for n in names if "email" in n.lower() and n != "expectedEmailMasked"}, (
        "SessionView non espone l'email (SR-014, THR-028)"
    )
    secrets = {"sub", "auth_subject", "authsubject"}
    assert not {n for n in names if n.lower() in secrets}, "né il sub"
