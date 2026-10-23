"""Ogni rotta non sicura porta la guardia che corrisponde al suo `x-authz.scope` (SEC-SL03a-003).

Il controllo CSRF e quello di sessione sono opt-in (`Depends(anonymous_guard)` /
`Depends(session_guard)`): nulla fallisce se una rotta nuova se ne dimentica. Questo test
cammina su `app.routes` (router inclusi, con le dipendenze di route, di router e di
`include_router`) e per ogni metodo `POST/PUT/PATCH/DELETE` verifica che l'albero delle
dipendenze contenga la guardia dello scope:

| scope | guardia |
|---|---|
| `anonymous` | `anonymous_guard` (origine e doppio invio del cookie `__Host-csrf`) |
| `account`, `family` | `session_guard` (origine, sessione valida, token CSRF della sessione) |
| `public`, `signup` | nessuna guardia esiste: una scrittura con questo scope è un errore finché
la slice che la introduce non definisce la guardia e aggiorna questo test |

Vincolo SR-023, THR-007. Il controllo sa fallire: è provato su app sintetiche in fondo al file.
"""

from collections.abc import Callable, Iterable, Iterator
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.utils import get_dependant
from fastapi.params import Depends as DependsParam
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from menu.identity import anonymous_guard, session_guard
from menu.platform import AuthzRoute

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
GUARD_FOR_SCOPE: dict[str, Callable[..., Any]] = {
    "anonymous": anonymous_guard,
    "account": session_guard,
    "family": session_guard,
}


def _calls_of(call: Callable[..., Any]) -> Iterator[Callable[..., Any]]:
    """`call` e tutte le dipendenze che dichiara, ricorsivamente (`Depends` annidati)."""
    stack = [get_dependant(path="", call=call)]
    while stack:
        dependant = stack.pop()
        if dependant.call is not None:
            yield dependant.call
        stack.extend(dependant.dependencies)


def _declared(dependencies: Iterable[DependsParam]) -> set[Callable[..., Any]]:
    found: set[Callable[..., Any]] = set()
    for dependency in dependencies:
        if dependency.dependency is not None:
            found.update(_calls_of(dependency.dependency))
    return found


def _leaves(
    routes: Iterable[BaseRoute], inherited: frozenset[Callable[..., Any]] = frozenset()
) -> Iterator[tuple[APIRoute, frozenset[Callable[..., Any]]]]:
    for route in routes:
        original = getattr(route, "original_router", None)
        if isinstance(original, APIRouter):
            context = getattr(route, "include_context", None)
            extra = _declared(getattr(context, "dependencies", []))
            yield from _leaves(original.routes, inherited | extra)
        elif type(route).__name__.startswith("_Included"):
            raise AssertionError("router incluso non ispezionabile: aggiornare questo test")
        elif isinstance(route, APIRoute):
            yield route, inherited


def guard_problems(app: FastAPI) -> list[str]:
    problems: list[str] = []
    for route, inherited in _leaves(app.routes):
        unsafe = sorted(set(route.methods or ()) & UNSAFE)
        if not unsafe:
            continue
        extra = route.openapi_extra or {}
        scope = (extra.get("x-authz") or {}).get("scope")
        where = f"{','.join(unsafe)} {route.path} ({route.operation_id})"
        guard = GUARD_FOR_SCOPE.get(str(scope))
        if guard is None:
            problems.append(f"{where}: nessuna guardia definita per lo scope {scope!r}")
            continue
        present = _calls_of_route(route) | set(inherited)
        if guard not in present:
            problems.append(f"{where}: manca {guard.__name__} (scope {scope})")
    return problems


def _calls_of_route(route: APIRoute) -> set[Callable[..., Any]]:
    calls: set[Callable[..., Any]] = set()
    stack = [route.dependant]
    while stack:
        dependant = stack.pop()
        if dependant.call is not None:
            calls.add(dependant.call)
        stack.extend(dependant.dependencies)
    return calls


def test_every_unsafe_route_of_the_app_carries_the_guard_of_its_scope(
    app_env: None,
) -> None:
    from menu.app import create_app

    app = create_app()
    routes = list(_leaves(app.routes))
    assert routes, "nessuna rotta trovata: il controllo girerebbe a vuoto"
    unsafe = [r for r, _ in routes if set(r.methods or ()) & UNSAFE]
    assert unsafe, "attese almeno start e logout (SL-03a)"
    assert guard_problems(app) == []


def test_the_login_start_and_logout_are_guarded_today(app_env: None) -> None:
    from menu.app import create_app

    by_op = {r.operation_id: r for r, _ in _leaves(create_app().routes)}
    assert anonymous_guard in _calls_of_route(by_op["identity.google.start"])
    assert session_guard in _calls_of_route(by_op["identity.session.logout"])


# --- il controllo sa fallire: app sintetiche ---------------------------------------------------


def _app(*routers: APIRouter, include_deps: list[DependsParam] | None = None) -> FastAPI:
    app = FastAPI()
    for router in routers:
        app.include_router(router, dependencies=include_deps)
    return app


def _router(**kw: Any) -> APIRouter:
    return APIRouter(route_class=AuthzRoute, prefix="/api/v1", **kw)


def _authz(scope: str, roles: list[str] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"scope": scope}
    if roles:
        body["roles"] = roles
    return {"x-authz": body}


def _post(
    router: APIRouter, scope: str, deps: list[Any] | None = None, method: str = "post"
) -> None:
    @router.api_route(
        "/probe",
        methods=[method.upper()],
        operation_id="probe.guard.write",
        openapi_extra=_authz(scope, ["admin"] if scope == "family" else None),
        dependencies=deps,
    )
    def handler() -> dict[str, bool]:
        return {"ok": True}


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_an_unguarded_family_write_is_flagged(method: str) -> None:
    router = _router()
    _post(router, "family", method=method)
    problems = guard_problems(_app(router))
    assert len(problems) == 1, problems
    assert "manca session_guard" in problems[0], problems


def test_an_unguarded_account_write_is_flagged() -> None:
    router = _router()
    _post(router, "account")
    assert any("manca session_guard" in p for p in guard_problems(_app(router)))


def test_an_unguarded_anonymous_write_is_flagged() -> None:
    router = _router()
    _post(router, "anonymous")
    assert any("manca anonymous_guard" in p for p in guard_problems(_app(router)))


def test_the_wrong_guard_for_the_scope_is_flagged() -> None:
    router = _router()
    _post(router, "family", [Depends(anonymous_guard)])
    assert any("manca session_guard" in p for p in guard_problems(_app(router)))
    router = _router()
    _post(router, "anonymous", [Depends(session_guard)])
    assert any("manca anonymous_guard" in p for p in guard_problems(_app(router)))


def test_a_public_or_signup_write_is_flagged_until_a_guard_exists() -> None:
    for scope in ("public", "signup"):
        router = _router()
        _post(router, scope)
        assert any("nessuna guardia definita" in p for p in guard_problems(_app(router))), scope


def test_a_safe_method_needs_no_guard() -> None:
    router = _router()
    _post(router, "family", method="get")
    assert guard_problems(_app(router)) == []


def test_a_route_level_guard_is_accepted() -> None:
    router = _router()
    _post(router, "family", [Depends(session_guard)])
    assert guard_problems(_app(router)) == []


def test_a_router_level_guard_is_accepted() -> None:
    router = _router(dependencies=[Depends(session_guard)])
    _post(router, "family")
    assert guard_problems(_app(router)) == []


def test_a_guard_given_to_include_router_is_accepted() -> None:
    router = _router()
    _post(router, "family")
    assert guard_problems(_app(router, include_deps=[Depends(session_guard)])) == []


def test_a_guard_reached_through_a_nested_dependency_is_accepted() -> None:
    def family_context(session: Annotated[Any, Depends(session_guard)]) -> Any:
        return session

    router = _router()
    _post(router, "family", [Depends(family_context)])
    assert guard_problems(_app(router)) == []


def test_a_wrapper_that_does_not_depend_on_the_guard_is_flagged() -> None:
    """Chiamare la sessione «a mano» nel corpo di una dipendenza non basta: serve `Depends`."""

    def home_made_session() -> None:
        return None

    router = _router()
    _post(router, "family", [Depends(home_made_session)])
    assert any("manca session_guard" in p for p in guard_problems(_app(router)))
