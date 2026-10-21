"""structlog in JSON su stdout con redazione (piano §5.3, SR-021, SR-051, THR-110).

Allow-list dei campi, chiavi vietate eliminate, ritorni a capo neutralizzati. Il timestamp è
solo un'etichetta del log, non un istante persistito.
"""

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

ALLOWED_FIELDS = frozenset(
    {
        "event",
        "severity",
        "timestamp",
        "correlation_id",
        "exception",
        "method",
        "path",
        "status",
        "duration_ms",
    }
)
FORBIDDEN_KEYS = frozenset(
    {
        "cookie",
        "authorization",
        "token",
        "secret",
        "password",
        "code_verifier",
        "csrf",
        "email",
        "display_name",
        "name",
        "note",
        "free_text",
        "guests_note",
        "before",
        "after",
    }
)
_SCALARS = (str, int, float, bool, type(None))


def _severity(_: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    event_dict["severity"] = "WARNING" if method_name == "warn" else method_name.upper()
    return event_dict


def _neutralise(value: str) -> str:
    return value.replace("\r", "\\r").replace("\n", "\\n")


def redact(_: WrappedLogger, __: str, event_dict: MutableMapping[str, Any]) -> EventDict:
    """Elimina le chiavi vietate e quelle fuori allow-list; valori solo scalari e su una riga."""
    clean: EventDict = {}
    for key, value in event_dict.items():
        if key.lower() in FORBIDDEN_KEYS or key not in ALLOWED_FIELDS:
            continue
        if not isinstance(value, _SCALARS):
            value = type(value).__name__
        clean[key] = _neutralise(value) if isinstance(value, str) else value
    return clean


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _severity,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.format_exc_info,
            redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
