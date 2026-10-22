"""Debito di SL-00a pianificato in SL-01 (docs/STATUS.md, riesame di sicurezza INFO-10/INFO-12).

- INFO-10: la allow-list dei percorsi non-API ammette per nome relativo al router, quindi un
  `Mount("/assets")` dentro un router incluso con `prefix="/x"` passa. Deve contare il percorso
  effettivo (con prefisso) oppure solo le rotte di primo livello.
- INFO-12: il controllo di profondità/NUL del corpo JSON scatta solo con `Content-Type:
  application/json`. FastAPI interpreta come JSON anche un corpo senza `Content-Type` o con
  `application/*+json`: su una rotta `GET` con `Body()` il bypass restava possibile.
"""

from collections.abc import Iterator
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Body, FastAPI
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from menu.platform import AuthzRoute, assert_all_routes_declare_authz
from support.probe import PUBLIC

BASE_URL = "https://testserver"


async def _sub_app(scope: Scope, receive: Receive, send: Send) -> None:
    await PlainTextResponse("static")(scope, receive, send)


def _bare_app() -> FastAPI:
    return FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


# --- INFO-10 ----------------------------------------------------------------------------------


def test_allow_list_does_not_admit_a_mount_nested_under_a_router_prefix() -> None:
    router = APIRouter(route_class=AuthzRoute)
    router.mount("/assets", _sub_app)
    app = _bare_app()
    app.include_router(router, prefix="/x")
    with pytest.raises(ValueError, match="assets"):
        assert_all_routes_declare_authz(app, allowed_non_api=frozenset({"/assets"}))


def test_allow_list_admits_the_top_level_mount_at_the_exact_path() -> None:
    app = _bare_app()
    app.router.routes.append(Mount("/assets", app=_sub_app))
    assert_all_routes_declare_authz(app, allowed_non_api=frozenset({"/assets"}))


def test_allow_list_does_not_admit_the_same_path_under_any_prefix_or_suffix() -> None:
    for mount_path in ("/assets/deep", "/asset", "/assets2"):
        app = _bare_app()
        app.router.routes.append(Mount(mount_path, app=_sub_app))
        with pytest.raises(ValueError, match=mount_path.strip("/")):
            assert_all_routes_declare_authz(app, allowed_non_api=frozenset({"/assets"}))


def test_the_real_app_with_a_web_dist_starts_and_refuses_any_other_mount(
    app_env: None, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con la SPA attiva resta valido il deny-by-default: nessun altro `Mount`, nemmeno con
    il percorso della eccezione statica ma sotto un prefisso (INFO-10 sull'app vera)."""
    from menu.app import create_app
    from support.assets import build_dist

    monkeypatch.setenv("WEB_DIST_DIR", str(build_dist(tmp_path)))
    create_app()  # avvio regolare con la SPA

    def mount_router(path: str) -> APIRouter:
        router = APIRouter(route_class=AuthzRoute, prefix="/x")
        router.mount(path, _sub_app)
        return router

    for path in ("/evil", "/assets"):
        with pytest.raises(ValueError, match="AuthzRoute"):
            create_app(extra_routers=[mount_router(path)])


# --- INFO-12 ----------------------------------------------------------------------------------

DEEP = b"[" * 11 + b"]" * 11  # profondità 11 > 10
UTF16_NUL = "[1]".encode("utf-16-le")  # contiene byte NUL


@pytest.fixture
def body_client(app_env: None) -> Iterator[tuple[TestClient, list[str]]]:
    """App reale + una rotta GET che dichiara un corpo (caso che il test di SL-00a non copriva)."""
    from menu.app import create_app

    calls: list[str] = []
    router = APIRouter(route_class=AuthzRoute, prefix="/_probe")

    @router.get("/get-with-body", operation_id="probe.getbody.read", openapi_extra=PUBLIC)
    async def get_with_body(payload: Annotated[Any, Body()]) -> dict[str, bool]:
        calls.append("get_with_body")
        return {"ok": True}

    with TestClient(
        create_app(extra_routers=[router]), base_url=BASE_URL, raise_server_exceptions=False
    ) as client:
        yield client, calls


@pytest.mark.parametrize(
    "content_type", [None, "application/vnd.api+json", "application/problem+json"]
)
@pytest.mark.parametrize("body", [DEEP, UTF16_NUL], ids=["too-deep", "utf16-nul"])
def test_deep_or_nul_json_body_is_rejected_whatever_the_content_type_info_12(
    body_client: tuple[TestClient, list[str]], content_type: str | None, body: bytes
) -> None:
    client, calls = body_client
    headers = {"Content-Type": content_type} if content_type else {}
    r = client.request("GET", "/_probe/get-with-body", content=body, headers=headers)
    assert r.status_code in {415, 422}, r.status_code
    assert r.headers["content-type"].startswith("application/problem+json")
    assert calls == [], "l'handler non deve eseguire con un corpo che la guardia deve respingere"


def test_normal_small_json_body_still_reaches_a_get_handler_with_json_type(
    body_client: tuple[TestClient, list[str]],
) -> None:
    """Controllo di regressione: la guardia non deve rifiutare i corpi validi."""
    client, calls = body_client
    r = client.request(
        "GET",
        "/_probe/get-with-body",
        content=b'{"a": [1, 2]}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert calls == ["get_with_body"]
