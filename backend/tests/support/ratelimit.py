"""Aiuti per i test dei limiti di frequenza e del massimo di sessioni (SL-03b).

Contiene: i pepper sintetici, le rotte di prova AUTENTICATE (sotto `/api/v1/`, perché finora
l'API non ha altre scritture con sessione: il solo logout chiude la sessione che prova), e le
letture di `rate_counter` e `session` via `owner`. Nessun IP o dato reale: indirizzi di
documentazione (RFC 5737) e identità sintetiche.
"""

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request

from menu.common import AppError, ErrorCode
from menu.identity import SESSION_COOKIE, SessionInfo, resolve_session, session_guard
from menu.platform import AuthzRoute
from support.owner import Owner

# Due pepper diversi (>= 32 caratteri): servono a provare che la chiave dipende dal pepper.
PEPPER_A = "test-pepper-A-0123456789abcdef0123456789abcdef"
PEPPER_B = "test-pepper-B-0123456789abcdef0123456789abcdef"

IP_REAL = "203.0.113.9"  # l'ultima voce di X-Forwarded-For: quella del proxy fidato
IP_OTHER = "198.51.100.5"
PROBE_PREFIX = "/api/v1/_rl"
ACCOUNT = {"x-authz": {"scope": "account", "pendingDeletion": "allowed", "reauth": False}}


def build_authenticated_probe(calls: list[str]) -> APIRouter:
    """Una lettura e una scrittura con sessione, per provare i limiti per sessione e per account."""
    router = APIRouter(route_class=AuthzRoute, prefix=PROBE_PREFIX)

    def need_session(request: Request) -> SessionInfo:
        session = resolve_session(request.cookies.get(SESSION_COOKIE))
        if session is None:
            raise AppError(ErrorCode.UNAUTHENTICATED)
        return session

    @router.get("/read", operation_id="probe.rl.read", openapi_extra=ACCOUNT)
    async def read(_: Annotated[SessionInfo, Depends(need_session)]) -> dict[str, bool]:
        calls.append("read")
        return {"ok": True}

    @router.post("/write", operation_id="probe.rl.write", openapi_extra=ACCOUNT)
    async def write(_: Annotated[SessionInfo, Depends(session_guard)]) -> dict[str, bool]:
        calls.append("write")
        return {"ok": True}

    return router


# --- lo stato letto dal database (solo lettura, via owner) --------------------------------------


def counters(owner: Owner) -> list[tuple[bytes, datetime, int]]:
    rows = owner.rows("select key, window_start, count from app.rate_counter order by 2, 1")
    return [(bytes(r[0]), r[1], r[2]) for r in rows]


def counter_keys(owner: Owner) -> set[bytes]:
    return {key for key, _, _ in counters(owner)}


def rate_counter_text(owner: Owner) -> str:
    """Tutto il contenuto di `rate_counter` come testo (bytea in esadecimale), per cercarvi dati."""
    return "\n".join(str(r[0]) for r in owner.rows("select t::text from app.rate_counter t"))


def live_sessions(owner: Owner, account: UUID) -> list[UUID]:
    """Sessioni ancora valide (30 giorni di inattività, 90 dalla creazione) dell'account."""
    now = datetime.now(UTC)
    rows = owner.rows(
        "select id from app.session where account_id = %s "
        "and last_used_at > %s and created_at > %s order by created_at, id",
        (account, now - timedelta(days=30), now - timedelta(days=90)),
    )
    return [r[0] for r in rows]


def insert_session(
    owner: Owner, account: UUID, *, used_days_ago: float = 0.5, created_days_ago: float = 1
) -> UUID:
    """Sessione sintetica (il cookie non esiste: serve solo a riempire il numero di sessioni)."""
    session = uuid4()
    now = datetime.now(UTC)
    owner.execute(
        "insert into app.session (id, account_id, token_hash, csrf_token_hash, created_at, "
        "last_used_at, auth_time) values (%s, %s, %s, %s, %s, %s, %s)",
        (
            session,
            account,
            uuid4().bytes + uuid4().bytes,
            uuid4().bytes + uuid4().bytes,
            now - timedelta(days=created_days_ago),
            now - timedelta(days=used_days_ago),
            now - timedelta(days=created_days_ago),
        ),
    )
    return session


def set_last_used(owner: Owner, session: UUID, *, days_ago: float) -> None:
    owner.execute(
        "update app.session set last_used_at = %s where id = %s",
        (datetime.now(UTC) - timedelta(days=days_ago), session),
    )


@contextlib.contextmanager
def counter_writes_denied(owner: Owner) -> Iterator[None]:
    """Simula un database che non accetta più le scritture dei contatori (fail closed, THR-103)."""
    owner.execute("revoke insert, update, delete on app.rate_counter from menu_app")
    try:
        yield
    finally:
        owner.execute("grant select, insert, update, delete on app.rate_counter to menu_app")


def problem_params(body: Any) -> dict[str, Any]:
    params = body.get("params") if isinstance(body, dict) else None
    return params if isinstance(params, dict) else {}
