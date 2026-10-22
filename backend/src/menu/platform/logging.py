"""structlog in JSON su stdout con redazione (piano §5.3, SR-021, SR-051, THR-110).

Allow-list dei campi, chiavi vietate eliminate, ritorni a capo neutralizzati. Il timestamp è
solo un'etichetta del log, non un istante persistito.
"""

import logging
import sys
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
        # evento di sicurezza strutturato (audit.security_log, SR-058): mai l'IP completo
        "event_type",
        "outcome",
        "actor_kind",
        "actor_role",
        "family_id",
        "target_type",
        "target_id",
        "ip_prefix",
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


def _foreign_event(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Record della libreria standard (sqlalchemy, uvicorn.error...): niente testo libero.

    Il messaggio può contenere parametri SQL o valori dell'utente (SEC-SL00b-006): si registra
    solo il nome del logger e, se c'è un'eccezione, il nome del suo tipo (mai traceback né testo).
    """
    record = event_dict.get("_record")
    event_dict["event"] = f"stdlib.{getattr(record, 'name', 'unknown')}"
    exc_info = event_dict.pop("exc_info", None)
    exc = exc_info[1] if isinstance(exc_info, tuple) else None
    if isinstance(exc, BaseException):
        event_dict["exception"] = type(exc).__name__
    return event_dict


def _stdlib_severity(_: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    event_dict["severity"] = method_name.upper()
    return event_dict


_HANDLER_MARK = "_menu_redacting_handler"


class _StdoutHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Scrive sul `sys.stdout` corrente (come `PrintLogger`), non su quello della creazione."""

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self) -> Any:
        return sys.stdout

    @stream.setter
    def stream(self, _: Any) -> None:
        pass


def _configure_stdlib() -> None:
    """Instrada il logger radice nella stessa redazione di structlog (una volta sola)."""
    root = logging.getLogger()
    if any(getattr(h, _HANDLER_MARK, False) for h in root.handlers):
        return
    handler = _StdoutHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            use_get_message=False,
            foreign_pre_chain=[
                _foreign_event,
                _stdlib_severity,
                structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            ],
            processors=[redact, structlog.processors.JSONRenderer()],
        )
    )
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
    # Un errore di formattazione non deve stampare messaggio e argomenti su stderr (CWE-532).
    logging.raiseExceptions = False
    if root.level == logging.NOTSET or root.level > logging.WARNING:
        root.setLevel(logging.WARNING)


def configure_logging() -> None:
    _configure_stdlib()
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
