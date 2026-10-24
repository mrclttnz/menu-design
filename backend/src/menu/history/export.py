"""Contributore di export di `history` (05-data §9.3, SR-072): la cronologia (`change_event`).

Colonne elencate esplicitamente. Solo identificativi, codici e testi liberi del pasto (SR-047):
nessun nome o email. Il perimetro `family` contiene gli eventi della famiglia del contesto (la
RLS li limita); il perimetro `self` quelli di cui la persona è autore o soggetto.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from menu.common import ExportRows

_FAMILY = text(
    "select id, family_id, occurred_at, actor_kind, actor_person_id, actor_role, unit_type, op, "
    "meal_date, meal_type, meal_slot, subject_person_id, dish_id, before, after, correlation_id "
    "from app.change_event order by occurred_at, id"
)
_SELF = text(
    "select id, family_id, occurred_at, actor_kind, actor_person_id, actor_role, unit_type, op, "
    "meal_date, meal_type, meal_slot, subject_person_id, dish_id, before, after, correlation_id "
    "from app.change_event where family_id = app.current_family_id() "
    "and (actor_person_id = :person_id or subject_person_id = :person_id) "
    "order by occurred_at, id"
)


def _rows(tx: Any, statement: Any, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in tx.execute(statement, params).mappings()]


class HistoryExport:
    tables = frozenset({"change_event"})

    def export_family(self, tx: Any) -> ExportRows:
        return {"change_event": _rows(tx, _FAMILY)}

    def export_self(self, tx: Any, account_id: UUID, person_id: UUID | None) -> ExportRows:
        if person_id is None:
            return {}
        return {"change_event": _rows(tx, _SELF, person_id=person_id)}
