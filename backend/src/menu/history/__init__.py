"""Modulo history (strato 3): eventi di modifica compatti, codec v1, export (ADR-0012).

Registra il proprio `ExportContributor` (tabella `change_event`).
"""

from menu.common import register_export_contributor
from menu.history import codec
from menu.history.export import HistoryExport
from menu.history.record import EventKey, record_change

register_export_contributor(HistoryExport())

__all__ = ["EventKey", "codec", "record_change"]
