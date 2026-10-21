"""Rotte di prova, SOLO per i test (mai in `src/`).

Ogni rotta di prova dichiara `x-authz` con `openapi_extra` (assunzione da confermare, vedi
report SL-00a). Tutte sono `public` tranne `account-only`.
"""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, ConfigDict, Field

from menu.common import AppError, ErrorCode
from menu.platform import AuthzRoute, expected_version

PROBE_PREFIX = "/_probe"
PUBLIC = {"x-authz": {"scope": "public"}}
ACCOUNT = {"x-authz": {"scope": "account", "pendingDeletion": "allowed", "reauth": False}}

# Valori canarino: non devono comparire mai in log, risposte d'errore, intestazioni.
LOG_CANARIES = {
    "cookie": "CANARY-LOG-COOKIE",
    "Cookie": "CANARY-LOG-COOKIE-CAP",
    "authorization": "CANARY-LOG-AUTHORIZATION",
    "AUTHORIZATION": "CANARY-LOG-AUTHORIZATION-UP",
    "token": "CANARY-LOG-TOKEN",
    "secret": "CANARY-LOG-SECRET",
    "password": "CANARY-LOG-PASSWORD",
    "code_verifier": "CANARY-LOG-VERIFIER",
    "csrf": "CANARY-LOG-CSRF",
    "email": "CANARY-LOG-EMAIL@example.test",
    "display_name": "CANARY-LOG-DISPLAYNAME",
    "name": "CANARY-LOG-NAME",
    "note": "CANARY-LOG-NOTE",
    "free_text": "CANARY-LOG-FREETEXT",
    "guests_note": "CANARY-LOG-GUESTNOTE",
    "before": {"dish": "CANARY-LOG-BEFORE"},
    "after": {"dish": "CANARY-LOG-AFTER"},
}


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=5)
    count: int = Field(ge=0, le=50)


def build_probe_router(calls: list[str]) -> APIRouter:
    """Router di prova; `calls` registra le esecuzioni degli handler."""
    router = APIRouter(route_class=AuthzRoute, prefix=PROBE_PREFIX)

    @router.post("/echo", operation_id="probe.echo.write", openapi_extra=PUBLIC)
    async def echo_post(payload: Annotated[Any, Body()]) -> dict[str, bool]:
        calls.append("echo_post")
        return {"ok": True}

    @router.put("/echo", operation_id="probe.echo.replace", openapi_extra=PUBLIC)
    async def echo_put(payload: Annotated[Any, Body()]) -> dict[str, bool]:
        calls.append("echo_put")
        return {"ok": True}

    @router.patch("/echo", operation_id="probe.echo.update", openapi_extra=PUBLIC)
    async def echo_patch(payload: Annotated[Any, Body()]) -> dict[str, bool]:
        calls.append("echo_patch")
        return {"ok": True}

    @router.delete("/echo", operation_id="probe.echo.delete", openapi_extra=PUBLIC)
    async def echo_delete() -> dict[str, bool]:
        calls.append("echo_delete")
        return {"ok": True}

    @router.get("/read", operation_id="probe.read.read", openapi_extra=PUBLIC)
    async def read() -> dict[str, bool]:
        calls.append("read")
        return {"ok": True}

    @router.post("/validated", operation_id="probe.item.write", openapi_extra=PUBLIC)
    async def validated(item: Item) -> dict[str, str]:
        calls.append("validated")
        return {"name": item.name}

    @router.put("/versioned/{item_id}", operation_id="probe.versioned.write", openapi_extra=PUBLIC)
    async def versioned(
        item_id: int, version: Annotated[int, Depends(expected_version)]
    ) -> dict[str, int]:
        calls.append("versioned")
        return {"version": version, "itemId": item_id}

    @router.get("/raise/{code}", operation_id="probe.error.read", openapi_extra=PUBLIC)
    async def raise_code(code: str, retry: int | None = None) -> None:
        calls.append("raise")
        params = {"retryAfterSeconds": retry} if retry is not None else None
        if params is None:
            raise AppError(ErrorCode(code))
        raise AppError(ErrorCode(code), params)

    @router.get("/boom", operation_id="probe.boom.read", openapi_extra=PUBLIC)
    async def boom() -> None:
        calls.append("boom")
        raise RuntimeError("CANARY-EXC-MESSAGE")

    @router.get("/log", operation_id="probe.log.read", openapi_extra=PUBLIC)
    async def log_in_request() -> dict[str, bool]:
        structlog.get_logger("probe").info(
            "probe.logged", **LOG_CANARIES, mystery_field_zz="CANARY-LOG-UNLISTED"
        )
        return {"ok": True}

    @router.get("/account-only", operation_id="probe.account.read", openapi_extra=ACCOUNT)
    async def account_only() -> dict[str, bool]:
        calls.append("account_only")
        return {"ok": True}

    @router.get("/rogue-public", operation_id="probe.rogue.read", openapi_extra=PUBLIC)
    async def rogue_public() -> dict[str, bool]:
        return {"ok": True}

    return router
