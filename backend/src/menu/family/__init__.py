"""Modulo family (strato 6): famiglia, persone; registra il proprio `ExportContributor`."""

from menu.common import register_export_contributor
from menu.family.export import FamilyExport

register_export_contributor(FamilyExport())
