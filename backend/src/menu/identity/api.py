"""Rotte di accesso con Google: avvio e callback (piano §4.3; ADR-0004 r.3).

`POST /auth/google/start` è anonima: origine, doppio invio del cookie `__Host-csrf`, corpo chiuso.
`GET /auth/google/callback` è pubblica e risponde sempre `302` (nessun errore HTTP, nessun
parametro d'esito nell'URL). Nessuna `GET` ha effetti oltre il callback, che è il ritorno di Google.
`GET /session` e `POST /auth/logout`, che compongono anche la famiglia, stanno in `menu.views`.
"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from menu.common import AppError, ErrorCode, ValidationCode
from menu.identity.clientinfo import request_ip
from menu.identity.cookies import clear_flow_cookie, set_flow_cookie, set_session_cookie
from menu.identity.flows import FLOW_COOKIE
from menu.identity.guards import anonymous_guard
from menu.identity.login import CallbackRequest, begin_login, complete_callback
from menu.identity.models import LoginResolver
from menu.identity.oidc import OidcError
from menu.identity.schemas import StartRequest, StartResponse
from menu.identity.services import services_of
from menu.identity.sessions import SESSION_COOKIE, resolve_session
from menu.platform import AuthzRoute
from menu.platform.http.problem import field_error

MAX_PARAMETER_LENGTH = 2048

router = APIRouter(prefix="/api/v1", route_class=AuthzRoute)


@router.post(
    "/auth/google/start",
    operation_id="identity.google.start",
    response_model=StartResponse,
    dependencies=[Depends(anonymous_guard)],
    openapi_extra={"x-authz": {"scope": "anonymous"}},
)
def start_login(body: StartRequest, request: Request, response: Response) -> StartResponse:
    if body.purpose == "reauth":
        # La riautenticazione arriva con SL-28: ora serve almeno una sessione valida.
        if resolve_session(request.cookies.get(SESSION_COOKIE)) is None:
            raise AppError(ErrorCode.UNAUTHENTICATED)
        raise AppError(
            ErrorCode.VALIDATION,
            {"errors": [field_error("purpose", ValidationCode.INVALID_VALUE)]},
        )
    try:
        url, handle = begin_login(
            services_of(request).oidc, body.return_to, request.cookies.get(FLOW_COOKIE)
        )
    except OidcError as error:
        raise AppError(ErrorCode.INTERNAL) from error
    set_flow_cookie(response, handle)
    return StartResponse(redirect_url=url)


def _single(request: Request, name: str) -> str | None:
    """Valore unico e di lunghezza ragionevole; ripetuto, vuoto o enorme vale come assente."""
    values = request.query_params.getlist(name)
    if len(values) != 1 or not values[0] or len(values[0]) > MAX_PARAMETER_LENGTH:
        return None
    return values[0]


@router.get(
    "/auth/google/callback",
    operation_id="identity.google.callback",
    status_code=302,
    response_class=Response,
    responses={302: {"description": "Ritorno alla SPA; l'esito si legge da `GET /session`."}},
    openapi_extra={"x-authz": {"scope": "public"}},
)
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    """Il valore dichiarato serve solo al contratto: i parametri si leggono con `_single`."""
    resolver: LoginResolver = request.app.state.login_resolver
    result = complete_callback(
        services_of(request).oidc,
        resolver,
        request.cookies.get(FLOW_COOKIE),
        CallbackRequest(
            code=_single(request, "code"),
            state=_single(request, "state"),
            error=_single(request, "error"),
            old_session_token=request.cookies.get(SESSION_COOKIE),
            ip=request_ip(request),
            user_agent=request.headers.get("user-agent"),
            correlation_id=request.state.correlation_id,
        ),
    )
    response = RedirectResponse(result.redirect_to, status_code=302)
    if result.session_token is not None:
        set_session_cookie(response, result.session_token)
    if result.clear_flow_cookie:
        clear_flow_cookie(response)
    return response
