"""SEC-SL00a-006 (SR-021, THR-110): errori del database e di Pydantic non portano valori nei log.

Il traceback resta nel log, ma i valori (parametri SQL, `DETAIL: Key (..)=(..)`, `input_value`)
sono canarini che non devono comparire in stdout/stderr né nella risposta.
"""

from typing import Annotated

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy import text

from support.paths import SRC
from support.probe import PUBLIC

PARAM = "CANARY-SQLPARAM-5d2"
ECHO = "CANARY-SQLECHO-77b"
PYDANTIC = "CANARY-PYDANTIC-31e"


def _db_probe_router() -> APIRouter:
    from menu import tenancy
    from menu.platform import AuthzRoute

    router = APIRouter(route_class=AuthzRoute, prefix="/_probe_db")

    @router.get("/param", operation_id="probedb.param.read", openapi_extra=PUBLIC)
    async def param() -> None:
        with tenancy.system_tx() as tx:
            tx.execute(text("select 1 / 0 where :p = :p"), {"p": PARAM})

    @router.get("/echo", operation_id="probedb.echo.read", openapi_extra=PUBLIC)
    async def echo() -> None:
        # Il server stesso riporta il valore nel messaggio (invalid input syntax ...).
        with tenancy.system_tx() as tx:
            tx.execute(text("select cast(:v as integer)"), {"v": ECHO})

    @router.get("/pydantic", operation_id="probedb.pydantic.read", openapi_extra=PUBLIC)
    async def pydantic_error() -> None:
        TypeAdapter(Annotated[int, "n"]).validate_python(PYDANTIC)

    return router


@pytest.mark.parametrize(
    ("path", "canary", "exception_name"),
    [
        ("/_probe_db/param", PARAM, "DivisionByZero"),
        ("/_probe_db/echo", ECHO, "InvalidTextRepresentation"),
        ("/_probe_db/pydantic", PYDANTIC, "ValidationError"),
    ],
)
def test_error_values_never_reach_logs_or_responses(
    db_env: None,
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    path: str,
    canary: str,
    exception_name: str,
) -> None:
    from menu.app import create_app

    with TestClient(
        create_app(extra_routers=[_db_probe_router()]),
        base_url="https://testserver",
        raise_server_exceptions=False,
    ) as client:
        resp = client.get(path)
    out = capfd.readouterr()
    logged = out.out + out.err + caplog.text
    assert resp.status_code == 500
    assert resp.json()["code"] == "internal"
    assert canary not in resp.text
    assert "http.unhandled_exception" in logged, "l'errore deve comunque essere registrato"
    assert exception_name in logged, "il log deve dire QUALE errore è avvenuto (solo il tipo)"
    assert canary not in logged, "valore sensibile nel log (CWE-532)"


def test_engine_is_created_with_hide_parameters() -> None:
    """Rete statica: l'unico `create_engine` è in `tenancy` e nasconde i parametri."""
    code = "\n".join(p.read_text(encoding="utf-8") for p in (SRC / "tenancy").rglob("*.py"))
    assert "hide_parameters=True" in code
