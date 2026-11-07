"""Modulo catalog (strato 7): portate, piatti; registra il proprio `ExportContributor`."""

from menu.catalog.api import router
from menu.catalog.dishes import read_refs
from menu.catalog.export import CatalogExport
from menu.catalog.schemas import CourseRef, DishRef
from menu.common import register_export_contributor

register_export_contributor(CatalogExport())

__all__ = ["CourseRef", "DishRef", "read_refs", "router"]
