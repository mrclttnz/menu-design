"""Contributore di export di `family` (05-data §9.3, SR-072): famiglia, pasti di default, persone.

Colonne elencate esplicitamente (allow-list): `account_id` e gli altri dati di account restano
fuori. `family_bootstrap` non si esporta (hash dell'email del Gestore). La RLS limita le righe
alla famiglia del contesto; il perimetro `self` aggiunge il filtro sulla propria persona.
`p_person_self` mostra anche le proprie righe `person` di altre famiglie: il filtro esplicito
su `app.current_family_id()` le esclude.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from menu.common import ExportRows

_FAMILY = text(
    "select id, name, timezone, frozen_through, status, created_at from app.family order by id"
)
_MEALS = text("select family_id, meal_type from app.family_default_meal order by meal_type")
_PERSONS = text(
    "select id, family_id, kind, status, role, display_name, joined_on, former_reason, "
    "guardian_declared_at, created_at from app.person "
    "where family_id = app.current_family_id() order by joined_on, id"
)
_OWN_PERSON = text(
    "select id, family_id, kind, status, role, display_name, joined_on, former_reason, "
    "guardian_declared_at, created_at from app.person "
    "where family_id = app.current_family_id() and id = :person_id"
)


def _rows(tx: Any, statement: Any, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in tx.execute(statement, params).mappings()]


class FamilyExport:
    tables = frozenset({"family", "family_default_meal", "person"})

    def export_family(self, tx: Any) -> ExportRows:
        return {
            "family": _rows(tx, _FAMILY),
            "family_default_meal": _rows(tx, _MEALS),
            "person": _rows(tx, _PERSONS),
        }

    def export_self(self, tx: Any, account_id: UUID, person_id: UUID | None) -> ExportRows:
        if person_id is None:
            return {}
        return {"person": _rows(tx, _OWN_PERSON, person_id=person_id)}
