"""`AuthzRoute`: ogni rotta dichiara `x-authz` (SR-009); senza dichiarazione l'app non parte."""

import re
from collections.abc import Callable, Iterable, Iterator
from typing import Any, Literal

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from starlette.routing import BaseRoute

AUTHZ_KEY = "x-authz"
_OPERATION_ID = re.compile(r"[a-z_]+(\.[a-z_]+){2,}")


class Authz(BaseModel):
    """Forma di `x-authz` (piano §4.1). Campi sconosciuti rifiutati."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: Literal["public", "anonymous", "signup", "account", "family"]
    roles: list[Literal["admin", "planner", "member"]] = []
    rules: list[Literal["self", "if_present", "member_own_to_try"]] = []
    pendingDeletion: Literal["allowed", "blocked"] = "allowed"  # noqa: N815 - nome del contratto
    reauth: bool = False
    tracks: list[str] = []

    @model_validator(mode="after")
    def _family_needs_roles(self) -> Authz:
        if self.scope == "family" and not self.roles:
            raise ValueError("lo scope 'family' richiede almeno un ruolo")
        return self


def validate_authz(route: APIRoute) -> None:
    extra = route.openapi_extra or {}
    if AUTHZ_KEY not in extra:
        raise ValueError(f"{route.methods} {route.path}: manca '{AUTHZ_KEY}'")
    try:
        Authz.model_validate(extra[AUTHZ_KEY])
    except ValidationError as exc:
        raise ValueError(
            f"{route.path}: '{AUTHZ_KEY}' non valido ({exc.error_count()} errori)"
        ) from exc
    if not route.operation_id or not _OPERATION_ID.fullmatch(route.operation_id):
        raise ValueError(
            f"{route.path}: operation_id assente o non nel formato area.risorsa.azione"
        )


class AuthzRoute(APIRoute):
    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(path, endpoint, **kwargs)
        validate_authz(self)


def _walk(routes: Iterable[BaseRoute]) -> Iterator[BaseRoute]:
    for route in routes:
        nested = getattr(route, "original_router", None)
        if isinstance(nested, APIRouter):
            yield from _walk(nested.routes)
        elif type(route).__name__.startswith("_Included"):
            # Struttura interna di FastAPI cambiata: nel dubbio l'avvio è rifiutato.
            raise ValueError("router incluso non ispezionabile: aggiornare assert_all_routes")
        else:
            yield route


def assert_all_routes_declare_authz(
    app: FastAPI, allowed_non_api: frozenset[str] = frozenset()
) -> None:
    """Rifiuta l'avvio se una rotta non è `AuthzRoute` (allow-list esplicita, vuota di default).

    Route semplici, `Mount`, `WebSocketRoute` e `Host` sono rifiutati: non hanno `x-authz`.
    `allowed_non_api` elenca i percorsi esatti ammessi come eccezioni, ma solo per le rotte di
    primo livello dell'app: dentro un router incluso il percorso è relativo al prefisso e non
    corrisponderebbe a quello effettivo (INFO-10).
    """
    for route in app.routes:
        if type(route).__name__.startswith("_Included") or isinstance(
            getattr(route, "original_router", None), APIRouter
        ):
            nested: Iterable[BaseRoute] = _walk([route])
        else:
            path = getattr(route, "path", None)
            if isinstance(path, str) and path in allowed_non_api:
                continue
            nested = [route]
        for leaf in nested:
            if not isinstance(leaf, AuthzRoute):
                path = getattr(leaf, "path", None)
                raise ValueError(f"{path or type(leaf).__name__}: la rotta non usa AuthzRoute")
