"""GET /healthz (Q-T2, THR-106): corpo minimo, no-store, nessun cookie, rotta pubblica."""

import pytest
from fastapi.testclient import TestClient


def test_healthz_body_is_exactly_status_unavailable_when_the_database_is_unreachable(
    real_client: TestClient,
) -> None:
    """SL-00b: `/healthz` controlla il DB (A-24); qui l'URL punta a una porta chiusa.

    Il caso `200 {"status":"ok"}` con database vero è in `tests/integration/test_healthz_db.py`.
    """
    resp = real_client.get("/healthz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
    assert resp.headers["content-type"].split(";")[0] == "application/json"


def test_503_leaks_neither_the_error_nor_the_database_url_in_body_or_logs(
    app_env: None, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """THR-106 / CWE-532: né dettagli dell'errore né la password dell'URL (canarino)."""
    canary = "CANARY-DB-PASSWORD"
    monkeypatch.setenv(
        "DATABASE_URL_APP",
        "postgresql+psycopg://menu_app:" + canary + "@localhost:1/menu"
        "?sslmode=verify-full&sslrootcert=/nonexistent/ca.crt",
    )
    from menu.app import create_app

    with TestClient(create_app(), base_url="https://testserver") as client:
        resp = client.get("/healthz")
    out = capfd.readouterr()
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
    assert canary not in resp.text
    assert canary not in out.out + out.err


def test_unreachable_database_answers_fast_and_is_not_retried_per_request(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raffica con il DB giù: una sola finestra di tentativi (A-24), risposta entro il timeout."""
    import time

    import psycopg

    attempts: list[int] = []
    original = psycopg.Connection.connect.__func__  # type: ignore[attr-defined]

    def counting(cls: object, /, *args: object, **kwargs: object) -> object:
        attempts.append(1)
        return original(cls, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(counting))
    from menu.app import create_app

    with TestClient(create_app(), base_url="https://testserver") as client:
        started = time.monotonic()
        codes = {client.get("/healthz").status_code for _ in range(15)}
    assert codes == {503}
    assert time.monotonic() - started < 6.0
    assert len(attempts) <= 2, f"{len(attempts)} tentativi di connessione per 15 richieste"


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
