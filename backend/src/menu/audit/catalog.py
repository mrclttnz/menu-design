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
    # Limiti e sessioni (SL-03b, SR-058, SR-070): `rate_limit.exceeded` ha solo la regola.
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"
    SESSION_EVICTED = "session.evicted"
    # Accesso ai dati (SL-04, SR-009, THR-020): permesso mancante e risorsa di un'altra famiglia.
    # Mai con identificativi o contenuti della risorsa: solo l'operazione.
    ACCESS_DENIED = "access.denied"
    ACCESS_CROSS_FAMILY = "access.cross_family"


EVENT_TYPES: frozenset[str] = frozenset(e.value for e in EventType)
