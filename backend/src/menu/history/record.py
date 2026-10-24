"""`record_change`: scrive l'evento di modifica nella stessa transazione della modifica (ADR-0012).

Autore e ruolo vengono dal `RequestContext` (la persona, mai l'account); il ruolo è quello
riletto dalla membership a inizio richiesta (FR-061). Il payload è validato dal codec prima
dell'`INSERT`: un payload non conforme solleva `CodecError` e la transazione chiamante fallisce.
Nessun nome o email entra nell'evento (SR-047), e `before`/`after` non vanno mai nei log.
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text

from menu.common import RequestContext
from menu.history import codec
from menu.tenancy import Tx

_INSERT = text(
    "insert into app.change_event (family_id, actor_kind, actor_person_id, actor_role, "
    "unit_type, op, meal_date, meal_type, meal_slot, subject_person_id, dish_id, "
    "before, after, correlation_id) "
    "values (:family, 'person', :person, :role, :unit_type, :op, :meal_date, :meal_type, "
    ":meal_slot, :subject, :dish, cast(:before as jsonb), cast(:after as jsonb), :correlation)"
)


@dataclass(frozen=True)
class EventKey:
    """Chiave dell'unità modificata; i campi richiesti dipendono dal tipo (CK del database)."""

    meal_date: date | None = None
    meal_type: str | None = None
    meal_slot: int | None = None
    subject_person_id: UUID | None = None
    dish_id: UUID | None = None


def record_change(
    tx: Tx,
    ctx: RequestContext,
    *,
    unit_type: str,
    op: str,
    key: EventKey,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> None:
    """Registra un evento di persona; `before` e `after` sono già in formato v1 (di solito da
    `codec.diff`, che però rifiuta uno stato invariato: in quel caso si costruiscono a mano);
    `codec.validate` li controlla qui."""
    if ctx.family_id is None or ctx.person_id is None or ctx.role is None:
        raise ValueError("un evento di persona richiede famiglia, persona e ruolo")
    codec.validate(unit_type, op, before, after)
    tx.execute(
        _INSERT,
        {
            "family": ctx.family_id,
            "person": ctx.person_id,
            "role": ctx.role,
            "unit_type": unit_type,
            "op": op,
            "meal_date": key.meal_date,
            "meal_type": key.meal_type,
            "meal_slot": key.meal_slot,
            "subject": key.subject_person_id,
            "dish": key.dish_id,
            "before": None if before is None else json.dumps(before, separators=(",", ":")),
            "after": json.dumps(after, separators=(",", ":")),
            "correlation": ctx.correlation_id,
        },
    )
