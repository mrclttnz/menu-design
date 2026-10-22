"""Contributore di export di `catalog` (05-data §9.3): le portate della famiglia."""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from menu.common import ExportRows

_COURSES = text("select id, family_id, base_code, name, created_at from app.course order by id")


class CatalogExport:
    tables = frozenset({"course"})

    def export_family(self, tx: Any) -> ExportRows:
        return {"course": [dict(r) for r in tx.execute(_COURSES).mappings()]}

    def export_self(self, tx: Any, account_id: UUID, person_id: UUID | None) -> ExportRows:
        return {}
