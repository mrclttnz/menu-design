"""Sessioni opache lato server (ADR-0004, SR-005, SR-037; 05-data §4.1, §6.1, §6.2).

Il cookie porta un token di 256 bit; in tabella resta solo l'SHA-256. Il cookie si risolve con
`app.session_resolve` (nessun account noto prima); ogni altra operazione sulla riga passa dalla
RLS per account. Validità: 30 giorni dall'ultimo uso e 90 dalla creazione, entrambi lato SQL.
`last_used_at` si rinnova al massimo una volta all'ora.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from menu import tenancy
from menu.audit.log import ip_prefix
from menu.identity.labels import device_label
from menu.identity.models import SessionInfo
from menu.identity.tokens import csrf_token_for, digest, new_secret, well_formed
from menu.tenancy import Tx, system_tx

SESSION_COOKIE = "__Host-session"
MAX_SESSIONS = 20  # per account (SR-070, THR-013)
IDLE_SECONDS = 30 * 24 * 3600

_RESOLVE = text("select * from app.session_resolve(:token_hash)")
_ACCOUNT_NAME = text("select display_name from app.account where id = :account_id")
_RENEW = text(
    "update app.session set last_used_at = app.now_utc() "
    "where id = :session_id and last_used_at < app.now_utc() - interval '1 hour' "
    "returning cast(extract(epoch from ((created_at + interval '2160 hours') - app.now_utc())) "
    "as bigint)"
)
_INSERT = text(
    "insert into app.session (account_id, token_hash, csrf_token_hash, auth_time, device_label, "
    "ip_prefix) values (:account_id, :token_hash, :csrf_token_hash, app.now_utc(), "
    "cast(:device_label as varchar), cast(:ip_prefix as inet)) returning id"
)
_DELETE = text("delete from app.session where id = :session_id")
_LOCK_ACCOUNT = text("select pg_advisory_xact_lock(hashtextextended(cast(:account_id as text), 0))")
# Sessioni valide come in `session_resolve` (720 ore dall'ultimo uso, 2160 dalla creazione): le
# scadute non contano e le toglie la pulizia giornaliera. Si tengono le `:keep` più recenti.
_EVICT = text(
    "with live as (select id, row_number() over (order by last_used_at desc, created_at desc, id) "
    "as position from app.session where account_id = :account_id "
    "and last_used_at >= app.now_utc() - interval '720 hours' "
    "and created_at >= app.now_utc() - interval '2160 hours') "
    "delete from app.session s using live where s.id = live.id and live.position > :keep "
    "returning s.id"
)


def resolve_session(token: str | None) -> SessionInfo | None:
    """Sessione valida del cookie, o `None` (scaduta, sconosciuta o malformata: stessa risposta)."""
    if not well_formed(token) or token is None:
        return None
    with system_tx() as tx:
        row = tx.execute(_RESOLVE, {"token_hash": digest(token)}).mappings().first()
        if row is None:
            return None
        account_id: UUID = row["account_id"]
        tenancy.bind_context(tx, account_id=account_id)
        renewed = tx.execute(_RENEW, {"session_id": row["session_id"]}).scalar_one_or_none()
        name = tx.execute(_ACCOUNT_NAME, {"account_id": account_id}).scalar_one_or_none()
    if name is None:
        return None
    max_age = None if renewed is None else max(1, min(IDLE_SECONDS, int(renewed)))
    return SessionInfo(
        session_id=row["session_id"],
        account_id=account_id,
        display_name=name,
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        auth_time=row["auth_time"],
        csrf_token=csrf_token_for(token),
        csrf_token_hash=bytes(row["csrf_token_hash"]),
        renewed_max_age=max_age,
    )


@dataclass(frozen=True)
class SessionRef:
    session_id: UUID
    account_id: UUID


def identify_session(token: str | None) -> SessionRef | None:
    """Sessione valida del cookie in sola lettura: non rinnova la finestra mobile (limiti)."""
    if not well_formed(token) or token is None:
        return None
    with system_tx() as tx:
        row = tx.execute(_RESOLVE, {"token_hash": digest(token)}).mappings().first()
    if row is None:
        return None
    return SessionRef(row["session_id"], row["account_id"])


def evict_over_cap(tx: Tx, account_id: UUID) -> list[UUID]:
    """Fa posto per una sessione nuova: revoca le meno usate oltre le `MAX_SESSIONS - 1` (SR-070).

    Il blocco per account serializza i login concorrenti dello stesso account: il secondo vede
    le sessioni già inserite dal primo. Contesto di account già impostato su `tx`.
    """
    tx.execute(_LOCK_ACCOUNT, {"account_id": str(account_id)})
    rows = tx.execute(_EVICT, {"account_id": account_id, "keep": MAX_SESSIONS - 1})
    return [row[0] for row in rows]


def create_session(
    tx: Tx, account_id: UUID, *, ip: str | None, user_agent: str | None
) -> tuple[str, UUID]:
    """Nuova sessione per l'account (contesto `app.account_id` già impostato): `(token, id)`."""
    token = new_secret()
    session_id: UUID = tx.execute(
        _INSERT,
        {
            "account_id": account_id,
            "token_hash": digest(token),
            "csrf_token_hash": digest(csrf_token_for(token)),
            "device_label": device_label(user_agent),
            "ip_prefix": ip_prefix(ip),
        },
    ).scalar_one()
    return token, session_id


def drop_session_of_cookie(tx: Tx, token: str | None) -> None:
    """Cancella la sessione che il browser già possiede (rigenerazione al login, THR-006)."""
    if not well_formed(token) or token is None:
        return
    row = tx.execute(_RESOLVE, {"token_hash": digest(token)}).mappings().first()
    if row is None:
        return
    tenancy.bind_context(tx, account_id=row["account_id"])
    tx.execute(_DELETE, {"session_id": row["session_id"]})


def delete_session(session: SessionInfo, tx: Tx | None = None) -> None:
    """Cancella la sessione sul server (logout, AC-001.4)."""
    if tx is not None:
        tx.execute(_DELETE, {"session_id": session.session_id})
        return
    with tenancy.account_tx(session.account_id) as own:
        own.execute(_DELETE, {"session_id": session.session_id})
