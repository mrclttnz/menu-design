"""Contributore di export di `planning` (05-data §9.3, SR-072): pasti e voci.

Colonne elencate esplicitamente (allow-list). La RLS limita le righe alla famiglia del contesto.
Il perimetro `family` comprende anche le righe `removed`: il loro contenuto resta nella riga
(05-data §4.2). Il perimetro `self` è vuoto: i pasti appartengono alla famiglia; le presenze
personali arrivano con `attendance` (SL-14).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from menu.common import ExportRows

_MEALS = text(
    "select family_id, meal_date, meal_type, meal_slot, name, presence, special_kind, "
    "content_version, content_modified_by, content_modified_at, guests_count, guests_note, "
    "guests_version, guests_modified_by, guests_modified_at from app.meal "
    "order by meal_date, meal_type, meal_slot"
)
_ITEMS = text(
    "select id, family_id, meal_date, meal_type, meal_slot, position, kind, dish_id, course_id, "
    "free_text, not_cooked from app.meal_item order by meal_date, meal_type, meal_slot, position"
)


def _rows(tx: Any, statement: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in tx.execute(statement).mappings()]


class PlanningExport:
    tables = frozenset({"meal", "meal_item"})

    def export_family(self, tx: Any) -> ExportRows:
        return {"meal": _rows(tx, _MEALS), "meal_item": _rows(tx, _ITEMS)}

    def export_self(self, tx: Any, account_id: UUID, person_id: UUID | None) -> ExportRows:
        return {}
