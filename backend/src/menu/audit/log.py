"""`security_log`: INSERT in `security_event` più log strutturato (senza IP completo)."""

import ipaddress
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy import event as sa_event
from sqlalchemy import text

from menu.audit.catalog import EVENT_TYPES
from menu.tenancy import Tx, system_tx

Outcome = Literal["success", "failure", "denied"]
ActorKind = Literal["account", "anonymous", "platform_operator", "system"]
Role = Literal["admin", "planner", "member"]

_INSERT = text(
    "insert into app.security_event (event_type, outcome, actor_kind, actor_account_id, "
    "actor_role, family_id, target_type, target_id, ip, correlation_id, details) "
    "values (:event_type, :outcome, :actor_kind, :actor_account_id, :actor_role, :family_id, "
    "cast(:target_type as varchar), :target_id, cast(:ip as inet), :correlation_id, "
    "cast(:details as jsonb))"
)
_log = structlog.get_logger("security_event")


@dataclass(frozen=True)
class SecurityEvent:
    event_type: str
    outcome: Outcome
    actor_kind: ActorKind
    actor_account_id: UUID | None = None
    actor_role: Role | None = None
    family_id: UUID | None = None
    target_type: str | None = None
    target_id: UUID | None = None
    ip: str | None = None
    correlation_id: UUID | None = None
    details_json: str | None = None  # JSON già serializzato, senza dati personali (<= 1 KiB)


def ip_prefix(ip: str | None) -> str | None:
    """IP troncato a /24 (IPv4) o /48 (IPv6) per il log; testo non valido → `None`."""
    if ip is None:
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def security_log(event: SecurityEvent, tx: Tx | None = None) -> None:
    """Scrive l'evento; la riga di log esce dopo l'evento `commit` di SQLAlchemy (con `tx` esterna).

    L'evento scatta subito prima del COMMIT del database: se questo fallisce (es. trigger
    differito) la riga di log è già uscita. Rischio accettato: solo un log in più, nessun dato.
    """
    if event.event_type not in EVENT_TYPES:
        raise ValueError("tipo di evento non presente nel catalogo")
    params: dict[str, Any] = {
        "event_type": event.event_type,
        "outcome": event.outcome,
        "actor_kind": event.actor_kind,
        "actor_account_id": event.actor_account_id,
        "actor_role": event.actor_role,
        "family_id": event.family_id,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "ip": event.ip,
        "correlation_id": event.correlation_id,
        "details": event.details_json,
    }
    fields: dict[str, Any] = {
        "event_type": event.event_type,
        "outcome": event.outcome,
        "actor_kind": event.actor_kind,
        "actor_role": event.actor_role,
        "family_id": None if event.family_id is None else str(event.family_id),
        "target_type": event.target_type,
        "target_id": None if event.target_id is None else str(event.target_id),
        "ip_prefix": ip_prefix(event.ip),
        "correlation_id": None if event.correlation_id is None else str(event.correlation_id),
    }

    def emit(*_: object) -> None:
        _log.info("security_event", **fields)

    if tx is None:
        with system_tx() as own:
            own.execute(_INSERT, params)
        emit()  # dopo il commit di `system_tx`
    else:
        tx.execute(_INSERT, params)
        sa_event.listen(tx, "commit", emit, once=True)
