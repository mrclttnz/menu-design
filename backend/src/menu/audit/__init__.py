"""Modulo audit (strato 3): registro di sicurezza e catalogo degli eventi (SR-020, SR-057).

`security_log` scrive la riga in `security_event` (il ruolo dell'app ha solo INSERT) e un log
strutturato con gli stessi campi, senza l'IP completo (piano §5.3, SR-051, SR-058).
"""

from menu.audit.cap import bump
from menu.audit.catalog import EVENT_TYPES, EventType
from menu.audit.log import SecurityEvent, security_log

__all__ = ["EVENT_TYPES", "EventType", "SecurityEvent", "bump", "security_log"]
