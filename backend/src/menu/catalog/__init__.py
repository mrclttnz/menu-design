"""Modulo catalog (strato 7): portate, piatti; registra il proprio `ExportContributor`."""

from menu.catalog.api import router
from menu.catalog.export import CatalogExport
from menu.common import register_export_contributor

register_export_contributor(CatalogExport())

__all__ = ["router"]
