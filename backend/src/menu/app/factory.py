"""`create_app`: unico punto in cui si assemblano configurazione, middleware e router."""

import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from menu import access, catalog, family, identity, ratelimit, tenancy, views
from menu.app import health
from menu.common import AppError
from menu.platform import Settings, assert_all_routes_declare_authz, configure_logging
from menu.platform.http.middleware import BodyGuardMiddleware, EnvelopeMiddleware
from menu.platform.http.problem import (
    ProblemDetails,
    app_error_handler,
    http_exception_handler,
    validation_error_handler,
)
from menu.platform.http.static import StaticSite

_PROBLEM_RESPONSE: dict[int | str, dict[str, Any]] = {
    "default": {
        "model": ProblemDetails,
        "description": "Errore (RFC 9457, `code` di ADR-0010)",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        },
    }
}


def _problem_json_only(app: FastAPI) -> None:
    """Pubblica gli errori solo come `application/problem+json` (FastAPI aggiunge anche json)."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = generate()
            for item in schema.get("paths", {}).values():
                for operation in item.values():
                    default = operation.get("responses", {}).get("default", {})
                    default.get("content", {}).pop("application/json", None)
        return app.openapi_schema or generate()

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(
    extra_routers: Sequence[APIRouter] = (),
    *,
    health_clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    # Fail closed: APP_ENV, DATABASE_URL_APP, TRUSTED_PROXY_HOPS e SESSION_PEPPER sono obbligatori.
    settings = Settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tenancy.init(settings.database_url_app.get_secret_value())
        try:
            yield
        finally:
            app.state.identity.close()
            tenancy.dispose()

    app = FastAPI(
        lifespan=lifespan,
        title="Menu Design",
        version="0.1.0",
        debug=False,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        responses=_PROBLEM_RESPONSE,
    )
    app.state.settings = settings
    access.configure_denial_cap(settings.session_pepper.get_secret_value().encode())
    app.state.health = health.HealthProbe(health_clock)
    # Collegamento dei protocolli (piano §2.2): `family` decide chi può entrare, `identity` esegue.
    app.state.identity = identity.IdentityServices.build(settings)
    app.state.login_resolver = family.FamilyOnboarding()
    _problem_json_only(app)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_middleware(BodyGuardMiddleware)
    app.add_middleware(
        ratelimit.RateLimitMiddleware,
        pepper=settings.session_pepper.get_secret_value().encode(),
        trusted_proxy_hops=settings.trusted_proxy_hops,
        identify=lambda cookies: identity.identify_session(cookies.get(identity.SESSION_COOKIE)),
    )
    app.add_middleware(EnvelopeMiddleware)

    app.include_router(health.router)
    app.include_router(identity.router)
    app.include_router(views.session_router)
    app.include_router(catalog.router)
    for router in extra_routers:
        app.include_router(router)
    assert_all_routes_declare_authz(app)
    if settings.web_dist_dir is not None:
        # Dopo tutte le rotte: la SPA risponde solo a ciò che l'API non ha riconosciuto.
        app.router.default = StaticSite(settings.web_dist_dir)
    return app
