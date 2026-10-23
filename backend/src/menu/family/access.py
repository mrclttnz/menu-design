"""Dipendenza delle rotte di famiglia: sessione, contesto riletto e `authorize` (SR-005, SR-009).

Il ruolo viene dalla membership attuale, mai dal client. Il permesso si controlla qui, prima
della validazione dei campi del corpo: chi non può scrivere non scopre le regole di merito.
Il JSON del corpo è già stato letto da FastAPI (un JSON malformato dà `422` prima di questa
dipendenza): non si usa per decidere il permesso.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from menu import access
from menu.common import RequestContext
from menu.family.membership import context_for
from menu.identity import SessionInfo, session_guard, session_reader


def family_access(operation: str, *, writes: bool) -> Callable[..., RequestContext]:
    """Dipendenza per `operation`: scritture con `session_guard` (CSRF), letture con il lettore."""
    guard = session_guard if writes else session_reader

    def dependency(
        request: Request, session: Annotated[SessionInfo, Depends(guard)]
    ) -> RequestContext:
        context = context_for(session, request.state.correlation_id)
        access.authorize(context, operation)
        return context

    return dependency
