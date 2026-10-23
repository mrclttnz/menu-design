"""Cookie dell'accesso: tutti `__Host-` (Secure, Path=/, nessun Domain), SR-005, SR-037.

- `__Host-session`: sessione, `HttpOnly`, `SameSite=Lax`, 30 giorni mobili.
- `__Host-auth_flow`: flusso OIDC in corso, `HttpOnly`, `SameSite=Lax` (deve tornare dal
  redirect di Google), 10 minuti.
- `__Host-csrf`: token anonimo del double submit, **non** `HttpOnly` (la SPA lo ripete
  nell'header), `SameSite=Strict`.
"""

from fastapi import Request, Response

from menu.identity.flows import FLOW_COOKIE, FLOW_SECONDS
from menu.identity.sessions import IDLE_SECONDS, SESSION_COOKIE
from menu.identity.tokens import new_secret, well_formed

CSRF_COOKIE = "__Host-csrf"


def set_session_cookie(response: Response, token: str, max_age: int = IDLE_SECONDS) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def set_flow_cookie(response: Response, handle: str) -> None:
    response.set_cookie(
        FLOW_COOKIE,
        handle,
        max_age=FLOW_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_flow_cookie(response: Response) -> None:
    response.delete_cookie(FLOW_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def ensure_csrf_cookie(request: Request, response: Response) -> None:
    """Imposta il token anonimo se manca (o è malformato); altrimenti non tocca nulla."""
    if well_formed(request.cookies.get(CSRF_COOKIE)):
        return
    response.set_cookie(
        CSRF_COOKIE,
        new_secret(),
        path="/",
        secure=True,
        httponly=False,
        samesite="strict",
    )
