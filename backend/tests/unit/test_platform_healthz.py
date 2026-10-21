"""GET /healthz (Q-T2, THR-106): corpo minimo, no-store, nessun cookie, rotta pubblica."""

from fastapi.testclient import TestClient


def test_healthz_body_is_exactly_status_ok(real_client: TestClient) -> None:
    resp = real_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["content-type"].split(";")[0] == "application/json"


def test_healthz_is_no_store(real_client: TestClient) -> None:
    assert "no-store" in real_client.get("/healthz").headers["cache-control"].lower()


def test_healthz_sets_no_cookie_even_with_cookies_in_request(real_client: TestClient) -> None:
    resp = real_client.get("/healthz", headers={"Cookie": "__Host-session=CANARY-HEALTH"})
    assert "set-cookie" not in resp.headers
    assert "CANARY-HEALTH" not in resp.text


def test_healthz_leaks_no_version_or_server_banner(real_client: TestClient) -> None:
    resp = real_client.get("/healthz")
    assert set(resp.json()) == {"status"}
    assert "x-powered-by" not in resp.headers


def test_healthz_is_outside_api_v1_and_published_as_public(real_client: TestClient) -> None:
    op = real_client.app.openapi()["paths"]["/healthz"]["get"]  # type: ignore[attr-defined]
    assert op["operationId"] == "platform.health.read"
    assert op["x-authz"]["scope"] == "public"
