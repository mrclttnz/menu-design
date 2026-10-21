"""SR-009: ogni rotta dichiara `authz` (AuthzRoute); senza dichiarazione l'app non parte."""

from collections.abc import Callable

import pytest
from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount

from menu.app import create_app
from menu.platform import AuthzRoute, assert_all_routes_declare_authz
from support.probe import PUBLIC, build_probe_router


def _start_with(router: APIRouter) -> None:
    """Costruisce e avvia l'app: l'errore può nascere alla registrazione o allo startup."""
    app = create_app(extra_routers=[router])
    with TestClient(app):
        pass


def test_route_without_authz_in_authz_router_refuses_to_start(app_env: None) -> None:
    router = APIRouter(route_class=AuthzRoute)

    with pytest.raises(ValueError, match="manca 'x-authz'"):

        @router.get("/_probe/undeclared", operation_id="probe.undeclared.read")
        async def undeclared() -> dict[str, bool]:
            return {"ok": True}


def test_route_on_plain_router_without_authz_refuses_to_start(app_env: None) -> None:
    """Un router che aggira `AuthzRoute` non deve poter montare rotte non dichiarate."""
    router = APIRouter()

    @router.get("/_probe/sneaky", operation_id="probe.sneaky.read")
    async def sneaky() -> dict[str, bool]:
        return {"ok": True}

    with pytest.raises(ValueError, match="non usa AuthzRoute"):
        _start_with(router)


@pytest.mark.parametrize(
    "bad_authz",
    [
        {},  # senza scope
        {"scope": "root"},  # scope sconosciuto
        {"scope": ""},
        {"scope": "public", "roles": ["superuser"]},  # ruolo sconosciuto
        {"scope": "account", "pendingDeletion": "maybe"},
        {"scope": "family"},  # family senza ruoli
        {"scope": "family", "roles": []},
        {"scope": "public", "extra": 1},  # chiave sconosciuta
    ],
)
def test_malformed_authz_declaration_refuses_to_start(
    app_env: None, bad_authz: dict[str, object]
) -> None:
    router = APIRouter(route_class=AuthzRoute)

    with pytest.raises(ValueError, match="'x-authz' non valido"):

        @router.get(
            "/_probe/bad", operation_id="probe.bad.read", openapi_extra={"x-authz": bad_authz}
        )
        async def bad() -> dict[str, bool]:
            return {"ok": True}


@pytest.mark.parametrize(
    "operation_id", [None, "", "health", "platform.health", "Platform.Health.Read"]
)
def test_missing_or_malformed_operation_id_refuses_to_start(
    app_env: None, operation_id: str | None
) -> None:
    router = APIRouter(route_class=AuthzRoute)

    with pytest.raises(ValueError, match="operation_id assente o non nel formato"):

        @router.get("/_probe/opid", operation_id=operation_id, openapi_extra=PUBLIC)
        async def opid() -> dict[str, bool]:
            return {"ok": True}


async def _plain(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _plain_route_router() -> APIRouter:
    router = APIRouter(route_class=AuthzRoute)
    router.add_route("/_probe/plain", _plain)
    return router


def _mount_router(path: str = "/_probe/sub") -> APIRouter:
    router = APIRouter(route_class=AuthzRoute)
    sub = FastAPI()

    @sub.get("/x")
    async def sub_x() -> dict[str, bool]:
        return {"ok": True}

    router.mount(path, sub)
    return router


def _websocket_router() -> APIRouter:
    router = APIRouter(route_class=AuthzRoute)

    @router.websocket("/_probe/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()

    return router


@pytest.mark.parametrize(
    "make_router",
    [_plain_route_router, _mount_router, _websocket_router],
    ids=["plain-route", "mount", "websocket"],
)
def test_non_api_routes_without_authz_refuse_to_start(
    app_env: None, make_router: Callable[[], APIRouter]
) -> None:
    with pytest.raises(ValueError, match="non usa AuthzRoute"):
        _start_with(make_router())


def test_allow_list_admits_only_the_exact_listed_path(app_env: None) -> None:
    app = create_app(extra_routers=[build_probe_router([])])
    sub_app = FastAPI()
    app.router.routes.append(Mount("/assets", app=sub_app))

    with pytest.raises(ValueError, match="/assets"):
        assert_all_routes_declare_authz(app)
    assert_all_routes_declare_authz(app, allowed_non_api=frozenset({"/assets"}))
    with pytest.raises(ValueError, match="/assets"):
        assert_all_routes_declare_authz(app, allowed_non_api=frozenset({"/assets2", "/"}))


def test_declared_authz_starts_and_is_published_as_x_authz(app_env: None) -> None:
    app = create_app(extra_routers=[build_probe_router([])])
    with TestClient(app):
        op = app.openapi()["paths"]["/_probe/echo"]["post"]
    assert op["x-authz"] == PUBLIC["x-authz"]


def test_probe_router_alone_is_wellformed(app_env: None) -> None:
    """Controllo della fixture: il router di prova è accettato (nessun falso rosso sopra)."""
    _start_with(build_probe_router([]))
