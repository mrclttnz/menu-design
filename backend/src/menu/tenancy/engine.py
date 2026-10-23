"""Engine SQLAlchemy sincrono su psycopg 3 e transazioni con contesto locale."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine import ExceptionContext, make_url
from sqlalchemy.exc import OperationalError

from menu.common import RequestContext

Tx = Connection

_DRIVER = "postgresql+psycopg"
_CONNECT_TIMEOUT_SECONDS = 3
_SET_CONTEXT = text(
    "select set_config('app.family_id', cast(:family as text), true), "
    "set_config('app.account_id', cast(:account as text), true), "
    "set_config('app.role', cast(:role as text), true)"
)

_engine: Engine | None = None


def _drop_parameter_values(context: ExceptionContext) -> None:
    """`hide_parameters` agisce solo sul messaggio: i valori non restano nemmeno in `.params`."""
    error = context.sqlalchemy_exception
    if error is not None:
        error.params = None


def init(url: str) -> None:
    """Crea l'engine (pool pigro: nessuna connessione finché non serve)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(
        make_url(url).set(drivername=_DRIVER),
        hide_parameters=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=_CONNECT_TIMEOUT_SECONDS,
        pool_recycle=300,
        # ADR-0003/0014: nessuno statement preparato (pooler in modalità transazione).
        connect_args={
            "prepare_threshold": None,
            "connect_timeout": _CONNECT_TIMEOUT_SECONDS,
            # Un peer sparito senza RST non deve bloccare una query per minuti (THR-106).
            "tcp_user_timeout": 10_000,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )
    event.listen(_engine, "handle_error", _drop_parameter_values)


def dispose() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def _require_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("tenancy non inizializzata")
    return _engine


def bind_context(
    tx: Tx,
    *,
    family_id: UUID | None = None,
    account_id: UUID | None = None,
    role: str | None = None,
) -> None:
    """Imposta (o cambia) il contesto locale della transazione già aperta `tx` (fail closed).

    Serve ai flussi che attraversano più ambiti nella stessa transazione, come il primo login
    (account, poi famiglia, poi sessione dell'account). Il valore è locale alla transazione:
    non sopravvive al commit né al riuso della connessione dal pool (THR-026, THR-027).
    """
    tx.execute(
        _SET_CONTEXT,
        {
            "family": "" if family_id is None else str(family_id),
            "account": "" if account_id is None else str(account_id),
            "role": role or "",
        },
    )


@contextmanager
def family_tx(ctx: RequestContext) -> Iterator[Tx]:
    """Transazione con `app.family_id`, `app.account_id`, `app.role` locali (fail closed)."""
    if ctx.family_id is None:
        raise ValueError("family_tx richiede un contesto con family_id")
    with _require_engine().begin() as conn:
        bind_context(conn, family_id=ctx.family_id, account_id=ctx.account_id, role=ctx.role)
        yield conn


@contextmanager
def account_tx(account_id: UUID) -> Iterator[Tx]:
    """Transazione con il solo `app.account_id` (RLS per account: `session`, `p_person_self`)."""
    with _require_engine().begin() as conn:
        bind_context(conn, account_id=account_id)
        yield conn


@contextmanager
def system_tx() -> Iterator[Tx]:
    """Transazione senza contesto di famiglia (tabelle non di famiglia, 05-data §6.3)."""
    with _require_engine().begin() as conn:
        yield conn


@contextmanager
def console_tx(correlation_id: UUID) -> Iterator[Tx]:
    """Transazione del job della console: solo `app.correlation_id` locale (ADR-0011)."""
    with _require_engine().begin() as conn:
        conn.execute(
            text("select set_config('app.correlation_id', cast(:correlation as text), true)"),
            {"correlation": str(correlation_id)},
        )
        yield conn


def ping() -> None:
    """`SELECT 1` come `menu_app` sul pool; ritenta una volta se la connessione era caduta."""
    for attempt in (1, 2):
        try:
            with system_tx() as tx:
                tx.exec_driver_sql("SELECT 1")
        except OperationalError as error:
            if not error.connection_invalidated or attempt == 2:
                raise
        else:
            return
