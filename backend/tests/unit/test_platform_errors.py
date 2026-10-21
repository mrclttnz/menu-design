"""problem+json (RFC 9457), stati di ADR-0010, traduzione della validazione, mai 500 gratuiti."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from support.adr_tables import VALIDATION_CODES, error_code_table

PROBLEM_KEYS = {"type", "title", "status", "code", "params", "errors", "detail", "instance"}


def assert_problem(resp: Response, status: int, code: str) -> dict[str, Any]:
    assert resp.status_code == status
    assert resp.headers["content-type"].split(";")[0] == "application/problem+json"
    body = resp.json()
    assert set(body) <= PROBLEM_KEYS
    assert {"type", "title", "status", "code"} <= set(body)
    assert body["status"] == status
    assert body["code"] == code
    return body  # type: ignore[no-any-return]


@pytest.mark.parametrize(("code", "status"), sorted(error_code_table().items()))
def test_app_error_maps_to_adr_0010_status(
    probe_client: TestClient, code: str, status: int
) -> None:
    """ADR-0010: ogni ErrorCode ha il proprio stato HTTP e il campo `code`."""
    assert_problem(probe_client.get(f"/_probe/raise/{code}"), status, code)


def test_app_error_params_are_returned(probe_client: TestClient) -> None:
    body = assert_problem(
        probe_client.get("/_probe/raise/rate_limited?retry=7"), 429, "rate_limited"
    )
    assert body["params"] == {"retryAfterSeconds": 7}


def test_unknown_path_is_problem_not_found(probe_client: TestClient) -> None:
    assert_problem(probe_client.get("/no/such/path"), 404, "not_found")


def test_unhandled_exception_is_generic_500(probe_client: TestClient) -> None:
    """Piano §5.2: 500 internal, nessuno stack trace né messaggio nella risposta."""
    resp = probe_client.get("/_probe/boom")
    assert_problem(resp, 500, "internal")
    for leaked in ("CANARY-EXC-MESSAGE", "Traceback", "RuntimeError", 'File "'):
        assert leaked not in resp.text


def test_validation_missing_field_is_required(probe_client: TestClient) -> None:
    resp = probe_client.post("/_probe/validated", json={"count": 1})
    body = assert_problem(resp, 422, "validation")
    assert {"field": "name", "code": "required"} in [
        {k: e[k] for k in ("field", "code")} for e in body["errors"]
    ]


def test_validation_too_long_has_max_param_and_no_input_echo(probe_client: TestClient) -> None:
    resp = probe_client.post("/_probe/validated", json={"name": "CANARY-LONGVALUE", "count": 1})
    body = assert_problem(resp, 422, "validation")
    err = next(e for e in body["errors"] if e["field"] == "name")
    assert err["code"] == "string_too_long"
    assert err["params"] == {"max": 5}
    assert "CANARY-LONGVALUE" not in resp.text


def test_validation_unknown_field(probe_client: TestClient) -> None:
    resp = probe_client.post("/_probe/validated", json={"name": "ab", "count": 1, "hacker": 1})
    body = assert_problem(resp, 422, "validation")
    assert {"field": "hacker", "code": "unknown_field"} in [
        {k: e[k] for k in ("field", "code")} for e in body["errors"]
    ]


def test_validation_wrong_type_is_invalid_value(probe_client: TestClient) -> None:
    resp = probe_client.post("/_probe/validated", json={"name": "ab", "count": "CANARY-TYPE"})
    body = assert_problem(resp, 422, "validation")
    err = next(e for e in body["errors"] if e["field"] == "count")
    assert err["code"] == "invalid_value"
    assert "CANARY-TYPE" not in resp.text


@pytest.mark.parametrize(
    "payload",
    [{"count": -1, "name": "ab"}, {"count": 99, "name": "ab"}, {}, {"name": None, "count": None}],
)
def test_validation_error_codes_are_in_the_closed_set(
    probe_client: TestClient, payload: dict[str, object]
) -> None:
    body = assert_problem(probe_client.post("/_probe/validated", json=payload), 422, "validation")
    assert body["errors"]
    assert {e["code"] for e in body["errors"]} <= VALIDATION_CODES


@pytest.mark.parametrize(
    "raw",
    [b"{bad", b"", b"\xff\xfe\x00", b"[1,2", b'{"name": "ab", "count": NaN}', b"null"],
)
def test_malformed_json_is_422_validation_never_500(probe_client: TestClient, raw: bytes) -> None:
    resp = probe_client.post(
        "/_probe/validated", content=raw, headers={"Content-Type": "application/json"}
    )
    assert_problem(resp, 422, "validation")


def test_problem_body_is_valid_json_object(probe_client: TestClient) -> None:
    resp = probe_client.get("/_probe/raise/forbidden")
    assert isinstance(json.loads(resp.text), dict)
