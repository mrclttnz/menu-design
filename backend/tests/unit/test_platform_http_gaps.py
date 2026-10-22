"""CR-SL00a-008 e CR-SL00a-012: rami della piattaforma non coperti e correlazione.

Rami: `client_ip(request)` con `TRUSTED_PROXY_HOPS`, traduzioni `too_long`/URL/data,
stato HTTP inatteso → 500, e `correlation_id` in `request.state` (RequestContext, plan §3).
"""

import uuid
from datetime import date
from typing import Annotated

import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException

from menu.app import create_app
from menu.platform import AuthzRoute, client_ip
from support.probe import PUBLIC

JSON = {"Content-Type": "application/json"}


class Shapes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: Annotated[list[int], Field(max_length=2)]
    link: AnyHttpUrl
    day: date


def _router() -> APIRouter:
    router = APIRouter(route_class=AuthzRoute, prefix="/_gap")

    @router.get("/ip", operation_id="gap.ip.read", openapi_extra=PUBLIC)
    async def ip(request: Request) -> dict[str, str]:
        return {"ip": client_ip(request)}

    @router.get("/cid", operation_id="gap.cid.read", openapi_extra=PUBLIC)
    async def cid(request: Request) -> dict[str, str]:
        return {"cid": str(request.state.correlation_id)}

    @router.post("/shapes", operation_id="gap.shapes.write", openapi_extra=PUBLIC)
    async def shapes(body: Shapes) -> dict[str, bool]:
        return {"ok": True}

    @router.get("/teapot", operation_id="gap.teapot.read", openapi_extra=PUBLIC)
    async def teapot() -> None:
        raise HTTPException(status_code=418)

    return router


@pytest.fixture
def client(app_env: None) -> TestClient:
    return TestClient(
        create_app(extra_routers=[_router()]),
        base_url="https://testserver",
        raise_server_exceptions=False,
    )


def test_client_ip_uses_last_trusted_forwarded_entry(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    c = TestClient(create_app(extra_routers=[_router()]), base_url="https://testserver")
    resp = c.get("/_gap/ip", headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.9"})
    assert resp.json() == {"ip": "203.0.113.9"}


def test_client_ip_ignores_forwarded_header_with_zero_hops(client: TestClient) -> None:
    resp = client.get("/_gap/ip", headers={"X-Forwarded-For": "6.6.6.6"})
    assert resp.json()["ip"] != "6.6.6.6"


def test_validation_translations_for_list_url_and_date(client: TestClient) -> None:
    resp = client.post(
        "/_gap/shapes",
        headers=JSON,
        json={"items": [1, 2, 3], "link": "javascript:alert(1)", "day": "2026-13-45"},
    )
    assert resp.status_code == 422
    codes = {(e["field"], e["code"]) for e in resp.json()["errors"]}
    assert ("items", "limit_reached") in codes
    assert ("link", "url_invalid") in codes
    assert ("day", "date_invalid") in codes


def test_unexpected_http_status_becomes_a_generic_500(client: TestClient) -> None:
    resp = client.get("/_gap/teapot")
    assert resp.status_code == 500
    assert resp.json()["code"] == "internal"


def test_correlation_id_is_available_on_request_state(client: TestClient) -> None:
    """CR-SL00a-012a: `RequestContext.correlation_id` si legge da `scope['state']`."""
    resp = client.get("/_gap/cid")
    assert resp.status_code == 200
    uuid.UUID(resp.json()["cid"])
