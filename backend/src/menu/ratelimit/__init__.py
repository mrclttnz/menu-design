"""Modulo ratelimit (strato 4): regole di SR-059 e SR-070, contatori in PostgreSQL, `429`.

ADR-0006: una tabella dichiarativa di regole, chiavi HMAC-SHA-256 con pepper, un solo upsert per
richiesta, fail closed (`503`). Il middleware applica il limite generale dell'API autenticata e
quelli per IP delle rotte anonime elencate in `rules.ROUTE_RULES`.
"""

from menu.ratelimit.middleware import RateLimitMiddleware, Session, SessionIdentifier
from menu.ratelimit.rules import (
    API_SESSION,
    OIDC_START,
    ROUTE_RULES,
    WRITE_ACCOUNT,
    WRITE_SESSION,
    Rule,
)
from menu.ratelimit.store import Hit, Verdict, hit

__all__ = [
    "API_SESSION",
    "OIDC_START",
    "ROUTE_RULES",
    "WRITE_ACCOUNT",
    "WRITE_SESSION",
    "Hit",
    "RateLimitMiddleware",
    "Rule",
    "Session",
    "SessionIdentifier",
    "Verdict",
    "hit",
]
