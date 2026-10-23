"""Modulo views (strato 11): letture composte (`GET /session`, poi `GET /plan`, `GET /history`)."""

from menu.views.session import router as session_router

__all__ = ["session_router"]
