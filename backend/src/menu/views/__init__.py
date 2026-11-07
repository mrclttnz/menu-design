"""Modulo views (strato 11): letture composte (`GET /session`, `GET /plan`, poi `GET /history`)."""

from menu.views.plan import router as plan_router
from menu.views.session import router as session_router

__all__ = ["plan_router", "session_router"]
