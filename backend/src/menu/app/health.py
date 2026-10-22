"""GET /healthz: rotta pubblica con controllo del DB (A-24, THR-106).

Un solo `SELECT 1` come `menu_app` sul pool ogni ~5 s (esito in memoria, anche se negativo),
corpo minimo e nessun dettaglio dell'errore.
"""

import threading
from collections.abc import Callable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from menu import tenancy
from menu.platform import AuthzRoute

WINDOW_SECONDS = 5.0
_log = structlog.get_logger("menu.health")


class Health(BaseModel):
    status: str


class HealthProbe:
    """Esito del controllo del database, riusato dentro la finestra."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._measured_at: float | None = None
        self._ok = False

    def database_ok(self) -> bool:
        # Un solo controllo alla volta: chi arriva mentre uno è in corso non aspetta e
        # riceve l'ultimo esito (A-24, THR-106: nessuna coda di thread con il DB lento).
        if not self._lock.acquire(blocking=False):
            return self._ok
        try:
            if (
                self._measured_at is not None
                and 0 <= self._clock() - self._measured_at < WINDOW_SECONDS
            ):
                return self._ok
            try:
                tenancy.ping()
                self._ok = True
            except Exception as error:  # qualunque guasto è "non disponibile"; solo il tipo
                self._ok = False
                _log.warning("health.database_unavailable", exception=type(error).__name__)
            self._measured_at = self._clock()  # dopo il controllo: la finestra parte da qui
            return self._ok
        finally:
            self._lock.release()


router = APIRouter(route_class=AuthzRoute)


@router.get(
    "/healthz",
    operation_id="platform.health.read",
    response_model=Health,
    responses={
        503: {
            "model": Health,
            "description": 'Database non raggiungibile: corpo {"status":"unavailable"}',
        }
    },
    openapi_extra={"x-authz": {"scope": "public"}},
)
def read_health(request: Request) -> Response:
    probe: HealthProbe = request.app.state.health
    if probe.database_ok():
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "unavailable"}, status_code=503)
