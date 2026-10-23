"""Controlli CSRF e di sessione per le rotte di `identity` e di `views` (SR-023, THR-007).

Per ogni metodo non sicuro: `Origin` uguale all'origine dell'app (o, senza `Origin`,
`Sec-Fetch-Site: same-origin`); un `Sec-Fetch-Site` diverso da `same-origin` è sempre un rifiuto.
`Content-Type: application/json` lo impone `BodyGuardMiddleware` (415).
Richieste anonime: double submit del cookie `__Host-csrf` nell'header `X-CSRF-Token`.
Richieste con sessione: token legato alla sessione nello stesso header. Il confronto è sempre
in tempo costante. Ogni rifiuto è `403 csrf_failed` (o `401`) senza alcun effetto.
"""

from fastapi import Request, Response

from menu.common import AppError, ErrorCode
from menu.identity.cookies import CSRF_COOKIE, set_session_cookie
from menu.identity.models import SessionInfo
from menu.identity.sessions import SESSION_COOKIE, resolve_session
from menu.identity.tokens import (
    constant_time_equal,
    constant_time_equal_bytes,
    digest,
    well_formed,
)

CSRF_HEADER = "x-csrf-token"


def _fail() -> AppError:
    return AppError(ErrorCode.CSRF_FAILED)


def require_same_origin(request: Request) -> None:
    site = request.headers.get("sec-fetch-site")
    if site is not None and site != "same-origin":
        raise _fail()
    origin = request.headers.get("origin")
    expected: str = request.app.state.settings.app_origin
    if origin is None:
        if site != "same-origin":
            raise _fail()
        return
    if origin != expected:
        raise _fail()


def anonymous_guard(request: Request) -> None:
    """Dipendenza delle `POST` anonime: origine e double submit del cookie `__Host-csrf`."""
    require_same_origin(request)
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not well_formed(cookie) or not well_formed(header) or cookie is None or header is None:
        raise _fail()
    if not constant_time_equal(cookie, header):
        raise _fail()


def session_guard(request: Request, response: Response) -> SessionInfo:
    """Dipendenza delle `POST` con sessione: origine, sessione valida (401), token CSRF (403).

    Se la finestra mobile è stata rinnovata ora, rinnova anche il cookie (AC-001.2).
    """
    require_same_origin(request)
    token = request.cookies.get(SESSION_COOKIE)
    session = resolve_session(token)
    if session is None or token is None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    if session.renewed_max_age is not None:
        set_session_cookie(response, token, session.renewed_max_age)
    header = request.headers.get(CSRF_HEADER)
    if (
        not well_formed(header)
        or header is None
        or not constant_time_equal_bytes(digest(header), session.csrf_token_hash)
    ):
        raise _fail()
    return session
