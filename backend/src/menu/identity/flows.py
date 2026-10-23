"""Tabella `auth_flow`: stato del flusso OIDC ed esito del callback (05-data §4.1, ADR-0004 r.3).

Ogni passo è una sola istruzione atomica in `system_tx`:
avvio (INSERT), reclamo monouso al callback (UPDATE ... WHERE consumed_at IS NULL), esito
negativo (UPDATE), lettura una sola volta (DELETE ... RETURNING). Nel database stanno solo gli
hash di cookie, `state` e `nonce`; il `code_verifier` PKCE è l'unico valore in chiaro (va inviato
a Google) e vive al massimo 15 minuti.
"""

import json
from dataclasses import dataclass, field

from sqlalchemy import text

from menu.identity.models import AuthOutcomeCode, AuthOutcomeRead
from menu.identity.tokens import digest, well_formed
from menu.tenancy import Tx, system_tx

FLOW_COOKIE = "__Host-auth_flow"
FLOW_SECONDS = 600

_START = text(
    "insert into app.auth_flow (handle_hash, purpose, return_to, state_hash, nonce_hash, "
    "code_verifier, expires_at) values (:handle_hash, 'login', cast(:return_to as varchar), "
    ":state_hash, :nonce_hash, :code_verifier, app.now_utc() + interval '10 minutes')"
)
_FORGET = text("delete from app.auth_flow where handle_hash = :handle_hash")
_CLAIM = text(
    "update app.auth_flow set consumed_at = app.now_utc(), "
    "expires_at = app.now_utc() + interval '5 minutes' "
    "where handle_hash = :handle_hash and consumed_at is null and expires_at > app.now_utc() "
    "returning purpose, session_id, return_to, state_hash, nonce_hash, code_verifier"
)
_FAIL = text(
    "update app.auth_flow set outcome_code = :code, outcome_params = cast(:params as jsonb) "
    "where handle_hash = :handle_hash and consumed_at is not null"
)
_READ = text(
    "delete from app.auth_flow where handle_hash = :handle_hash and outcome_code is not null "
    "and expires_at > app.now_utc() returning outcome_code, outcome_params"
)


@dataclass(frozen=True)
class ClaimedFlow:
    purpose: str
    session_id: object
    return_to: str | None
    state_hash: bytes = field(repr=False)
    nonce_hash: bytes = field(repr=False)
    code_verifier: str = field(repr=False)


def start_flow(
    *,
    handle: str,
    state: str,
    nonce: str,
    code_verifier: str,
    return_to: str | None,
    previous_handle: str | None,
) -> None:
    with system_tx() as tx:
        if well_formed(previous_handle) and previous_handle is not None:
            tx.execute(_FORGET, {"handle_hash": digest(previous_handle)})
        tx.execute(
            _START,
            {
                "handle_hash": digest(handle),
                "return_to": return_to,
                "state_hash": digest(state),
                "nonce_hash": digest(nonce),
                "code_verifier": code_verifier,
            },
        )


def claim_flow(handle: str | None) -> ClaimedFlow | None:
    """Reclama il flusso una sola volta (THR-002): `None` se assente, scaduto o già usato."""
    if not well_formed(handle) or handle is None:
        return None
    with system_tx() as tx:
        row = tx.execute(_CLAIM, {"handle_hash": digest(handle)}).mappings().first()
    if row is None:
        return None
    return ClaimedFlow(
        purpose=row["purpose"],
        session_id=row["session_id"],
        return_to=row["return_to"],
        state_hash=bytes(row["state_hash"]),
        nonce_hash=bytes(row["nonce_hash"]),
        code_verifier=row["code_verifier"],
    )


def record_failure(
    handle: str, code: AuthOutcomeCode, params: dict[str, str] | None = None, tx: Tx | None = None
) -> None:
    """Esito negativo sulla riga reclamata: la SPA lo legge una volta da `GET /session`."""
    values = {
        "handle_hash": digest(handle),
        "code": code,
        "params": None if params is None else json.dumps(params),
    }
    if tx is not None:
        tx.execute(_FAIL, values)
        return
    with system_tx() as own:
        own.execute(_FAIL, values)


def forget_flow(tx: Tx, handle: str) -> None:
    """Cancella la riga (esito positivo: nessun esito da conservare)."""
    tx.execute(_FORGET, {"handle_hash": digest(handle)})


def read_outcome(handle: str | None) -> AuthOutcomeRead | None:
    """Legge e cancella l'esito (una sola volta); senza il cookie dello stesso browser, mai."""
    if not well_formed(handle) or handle is None:
        return None
    with system_tx() as tx:
        row = tx.execute(_READ, {"handle_hash": digest(handle)}).mappings().first()
    if row is None:
        return None
    raw = row["outcome_params"]
    params = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else None
    return AuthOutcomeRead(code=row["outcome_code"], params=params)
