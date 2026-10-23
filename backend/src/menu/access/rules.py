"""`authorize` e l'evento di sicurezza per le risorse di un'altra famiglia."""

import json
from collections.abc import Mapping
from typing import Any

import structlog

from menu.access.matrix import OPERATIONS
from menu.audit import EventType, SecurityEvent, bump, security_log
from menu.common import AppError, ErrorCode, RequestContext

_log = structlog.get_logger("access")

# SEC-SL04-001: tetto agli eventi di rifiuto per account e ora, condiviso da `access.denied` e
# `access.cross_family`. 20/ora lascia rilevabile l'allarme SR-058 (> 10 all'ora per account).
DENIAL_LOG_NAME = "access_denied_log"
DENIAL_LOG_LIMIT = 20
DENIAL_LOG_WINDOW_SECONDS = 3600

_pepper: bytes | None = None


def configure_denial_cap(pepper: bytes | None) -> None:
    """Imposta il pepper delle chiavi del tetto (lo chiama `create_app`). `None` = senza tetto."""
    global _pepper
    _pepper = pepper


def _event(
    event_type: EventType, ctx: RequestContext, operation: str, *, suppressed: bool = False
) -> SecurityEvent:
    details: dict[str, Any] = {"operation": operation}
    if suppressed:
        details["suppressed"] = True
    return SecurityEvent(
        event_type=event_type.value,
        outcome="denied",
        actor_kind="account" if ctx.account_id is not None else "anonymous",
        actor_account_id=ctx.account_id,
        actor_role=ctx.role,
        family_id=ctx.family_id,
        correlation_id=ctx.correlation_id,
        # Solo il nome dell'operazione: mai identificativi o contenuti della risorsa (SR-057).
        details_json=json.dumps(details, separators=(",", ":")),
    )


def _record_denial(event_type: EventType, ctx: RequestContext, operation: str) -> None:
    """Scrive l'evento entro il tetto; alla prima richiesta oltre scrive un solo `suppressed`.

    Mai un errore verso il client: se il contatore o il registro falliscono, la risposta resta
    `403`/`404` e l'evento si perde (si registra solo il tipo di errore).
    """
    try:
        suppressed = False
        if _pepper is not None:
            who = "anonymous" if ctx.account_id is None else str(ctx.account_id)
            count = bump(_pepper, DENIAL_LOG_NAME, who, DENIAL_LOG_WINDOW_SECONDS)
            if count > DENIAL_LOG_LIMIT + 1:
                return
            suppressed = count == DENIAL_LOG_LIMIT + 1
        security_log(_event(event_type, ctx, operation, suppressed=suppressed))
    except Exception as error:
        _log.error("access.denial_unrecorded", exception=type(error).__name__)


def authorize(ctx: RequestContext, operation: str, facts: Mapping[str, Any] | None = None) -> None:
    """Ammette o solleva `forbidden` scrivendo `access.denied`. Negato per default.

    `facts` è riservato alle regole condizionate (SL-17): ora nessuna riga le usa.
    """
    allowed = OPERATIONS.get(operation)
    if allowed is not None and ctx.family_id is not None and ctx.role in allowed:
        return
    _record_denial(EventType.ACCESS_DENIED, ctx, operation)
    raise AppError(ErrorCode.FORBIDDEN)


def cross_family(ctx: RequestContext, operation: str) -> AppError:
    """Registra `access.cross_family` e restituisce il `404` da sollevare (SR-008, THR-020).

    Si usa per ogni risorsa non trovata per identificativo: inesistente o di un'altra famiglia
    producono lo stesso evento e la stessa risposta, così il client non le distingue. L'evento
    sta in una transazione propria: sopravvive al rollback della richiesta. Gli eventi sono
    limitati per account e ora (`DENIAL_LOG_LIMIT`).
    """
    _record_denial(EventType.ACCESS_CROSS_FAMILY, ctx, operation)
    return AppError(ErrorCode.NOT_FOUND)
