"""Modulo planning (strato 8): pasti del piano, lettura e presenza; registra il proprio export."""

from menu.common import register_export_contributor
from menu.planning.api import router
from menu.planning.export import PlanningExport
from menu.planning.meals import MAX_DAYS, PlanData, read_plan

register_export_contributor(PlanningExport())

__all__ = ["MAX_DAYS", "PlanData", "read_plan", "router"]
