"""Protocollo e registro `ExportContributor` (piano §2.2, OBJ-02; 05-data §9.3, SR-072).

Ogni modulo che possiede tabelle di famiglia registra un contributore all'import del proprio
pacchetto; `privacy` (SL-23a) raccoglie il registro. `tx` è la transazione di `menu.tenancy`
(qui `Any`: `common` non dipende da SQLAlchemy). Il registro ignora un oggetto già registrato.
"""

from typing import Any, Protocol
from uuid import UUID

ExportRows = dict[str, list[dict[str, Any]]]


class ExportContributor(Protocol):
    tables: frozenset[str]

    def export_family(self, tx: Any) -> ExportRows: ...

    def export_self(self, tx: Any, account_id: UUID, person_id: UUID | None) -> ExportRows: ...


_registry: list[ExportContributor] = []


def register_export_contributor(contributor: ExportContributor) -> None:
    if not any(c is contributor for c in _registry):
        _registry.append(contributor)


def export_contributors() -> tuple[ExportContributor, ...]:
    return tuple(_registry)
