"""SR-023 (header di sicurezza, nessun CORS) e SR-046 (no-store)."""

import re

import pytest
from fastapi.testclient import TestClient
from httpx import Response

JSON = {"Content-Type": "application/json"}
REFERRER_OK = {"no-referrer", "same-origin", "strict-origin", "strict-origin-when-cross-origin"}


def csp_directives(value: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for part in value.split(";"):
        tokens = part.split()
        if tokens:
            out[tokens[0].lower()] = tokens[1:]
    return out


def check_security_headers(resp: Response) -> None:
    h = resp.headers
    m = re.search(r"max-age=(\d+)", h["strict-transport-security"])
    assert m
    assert int(m.group(1)) >= 15552000
    assert h["x-content-type-options"].lower() == "nosniff"
    assert h["referrer-policy"].lower() in REFERRER_OK
    csp = csp_directives(h["content-security-policy"])
    assert csp["object-src"] == ["'none'"]
    assert csp["base-uri"] == ["'none'"]
    assert csp["form-action"] == ["'self'"]
    assert csp["frame-ancestors"] == ["'none'"]
    assert csp["connect-src"] == ["'self'"]
    assert csp["require-trusted-types-for"] == ["'script'"]
    assert csp["trusted-types"] == ["'none'"]
    assert csp["img-src"] == ["'self'"]
    for directive in ("default-src", "script-src"):
        values = csp.get(directive, [])
        assert "'unsafe-inline'" not in values
        assert "'unsafe-eval'" not in values
        assert "*" not in values
    assert "default-src" in csp or "script-src" in csp


def test_security_headers_on_success(probe_client: TestClient) -> None:
    check_security_headers(probe_client.get("/healthz"))


@pytest.mark.parametrize(
    "request_args",
    [
        ("GET", "/no/such/path", {}),
        ("POST", "/healthz", {"content": b"{}", "headers": JSON}),  # 405
        ("GET", "/_probe/raise/forbidden", {}),
        ("GET", "/_probe/boom", {}),
        (
            "POST",
            "/_probe/echo",
            {"content": b'{"a":1}', "headers": {"Content-Type": "text/plain"}},
        ),
        ("POST", "/_probe/echo", {"content": b"x" * 70000, "headers": JSON}),
        ("POST", "/_probe/echo", {"content": b"{bad", "headers": JSON}),
        ("PUT", "/_probe/versioned/1", {"content": b"{}", "headers": JSON}),
    ],
    ids=["404", "405", "403", "500", "415", "413", "422", "428"],
)
def test_security_headers_on_every_error_path(
    probe_client: TestClient, request_args: tuple[str, str, dict[str, object]]
) -> None:
    """Le risposte generate dai middleware (413, 415, ...) non devono perdere gli header."""
    method, path, kwargs = request_args
    check_security_headers(probe_client.request(method, path, **kwargs))  # type: ignore[arg-type]


def test_no_cors_headers_even_with_foreign_origin(probe_client: TestClient) -> None:
    origin = {"Origin": "https://evil.example.test"}
    for resp in (
        probe_client.get("/healthz", headers=origin),
        probe_client.options(
            "/_probe/echo",
            headers={**origin, "Access-Control-Request-Method": "POST"},
        ),
    ):
        assert not any(k.lower().startswith("access-control-allow") for k in resp.headers)


def test_account_scope_response_is_no_store(probe_client: TestClient) -> None:
    """SR-046: risposta di una rotta non pubblica (assunzione: AuthzRoute solo dichiara)."""
    resp = probe_client.get("/_probe/account-only")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"].lower()
