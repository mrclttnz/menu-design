"""Catalogo degli eventi di sicurezza (SR-020): l'elenco cresce con le slice che li producono.

Formato `dominio.azione` in minuscolo (CHECK `ck_security_event_event_type`, 05-data §4.1).
"""

from enum import StrEnum


class EventType(StrEnum):
    # Console (SL-02): scritti dalle funzioni `console_*` del database, mai dall'app.
    CONSOLE_FAMILY_BOOTSTRAP = "console.family_bootstrap"
    CONSOLE_SECURITY_LOG = "console.security_log"
    CONSOLE_AUDIT_NOTE = "console.audit_note"
    # Accesso (SL-03a, SR-020): scritti da `identity` e `views`, mai con email, `sub` o token.
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"


EVENT_TYPES: frozenset[str] = frozenset(e.value for e in EventType)
