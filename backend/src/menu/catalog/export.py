"""Contributore di export di `catalog` (05-data §9.3, SR-072): portate, piatti e fonti.

Colonne elencate esplicitamente (allow-list); `dish.name_search` è derivata e resta fuori. La RLS
limita le righe alla famiglia del contesto. Il perimetro `self` non contiene righe del catalogo:
piatti e portate appartengono alla famiglia, non a una persona.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from menu.common import ExportRows

_COURSES = text("select id, family_id, base_code, name, created_at from app.course order by id")
_DISHES = text(
    "select id, family_id, name, status, notes, prep_time, archived_at, ever_planned, "
    "created_by, created_at, version, modified_by, modified_at from app.dish order by id"
)
_DISH_COURSES = text(
    "select family_id, dish_id, course_id from app.dish_course order by dish_id, course_id"
)
_DISH_SOURCES = text(
    "select id, family_id, dish_id, position, kind, reference, page, note from app.dish_source "
    "order by dish_id, position"
)


def _rows(tx: Any, statement: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in tx.execute(statement).mappings()]


class CatalogExport:
    tables = frozenset({"course", "dish", "dish_course", "dish_source"})

    def export_family(self, tx: Any) -> ExportRows:
        return {
            "course": _rows(tx, _COURSES),
            "dish": _rows(tx, _DISHES),
            "dish_course": _rows(tx, _DISH_COURSES),
            "dish_source": _rows(tx, _DISH_SOURCES),
        }

    def export_self(self, tx: Any, account_id: UUID, person_id: UUID | None) -> ExportRows:
        return {}
