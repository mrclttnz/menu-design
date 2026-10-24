"""Tetto di 5.000 scritture tracciate al giorno per famiglia (SR-070, AC-049.5; THR-046, THR-100).

Le chiamano i servizi di dominio che scrivono un evento di modifica, DOPO autorizzazione e
precondizioni (403, 404, 412, 422 non consumano il tetto) e nella transazione della scrittura:
se questa fallisce o viene annullata, anche l'incremento sparisce. La finestra è il giorno
LOCALE della famiglia (da mezzanotte locale a mezzanotte locale, ADR-0006), non quello UTC.

Il contatore sta in `rate_counter` con chiave HMAC-SHA-256(pepper, `tracked_family` NUL
`family_id`). L'incremento è un solo `INSERT ... ON CONFLICT DO UPDATE ... WHERE count < limite`:
la riga si blocca fino al commit, quindi le scritture concorrenti della famiglia si
serializzano e nessuna supera il limite. Una scrittura respinta non incrementa.

Oltre il limite `consume_tracked_write` solleva `TrackedCapExceeded` e il `429` lo produce
`tracked_write`, che sta FUORI dalla transazione della famiglia: l'allarme (un solo evento
`rate_limit.exceeded` per finestra, SR-058, con un contatore a parte) si scrive quando quella
transazione è già annullata e chiusa, così nessuna richiesta tiene due connessioni del pool
né blocchi di riga mentre ne chiede una seconda (SEC-SL05-001, CR-SL05-002). Le rotte con
scritture tracciate usano sempre `with tracked_write(ctx), family_tx(ctx) as tx:`.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from math import ceil

import structlog
from sqlalchemy import text

from menu.audit import EventType, SecurityEvent, security_log
from menu.common import AppError, ErrorCode, RequestContext
from menu.ratelimit.rules import Rule
from menu.ratelimit.store import counter_key
from menu.tenancy import Tx, system_tx

TRACKED_FAMILY = Rule("tracked_family", limit=5000, window_seconds=86400)
_ALARM = Rule("tracked_family_alarm", limit=1, window_seconds=86400)

_CONSUME = text(
    "insert into app.rate_counter as c (key, window_start) "
    "select :key, cast(app.family_today() as timestamp) at time zone f.timezone "
    "from app.family f where f.id = app.current_family_id() "
    "on conflict (key, window_start) do update set count = c.count + 1 "
    "where c.count < :limit "
    "returning c.count"
)
_WINDOW = text(
    "select cast(app.family_today() as timestamp) at time zone f.timezone, "
    "cast(app.family_today() + 1 as timestamp) at time zone f.timezone, app.now_utc() "
    "from app.family f where f.id = app.current_family_id()"
)
_ALARM_BUMP = text(
    "insert into app.rate_counter as c (key, window_start) values (:key, :window_start) "
    "on conflict (key, window_start) do update set count = c.count + 1 "
    "returning c.count"
)

_log = structlog.get_logger("menu.ratelimit")
_pepper: bytes | None = None


def configure_tracked_writes(pepper: bytes | None) -> None:
    """Imposta il pepper (lo chiama `create_app`); senza, le scritture tracciate falliscono."""
    global _pepper
    _pepper = pepper


class TrackedCapExceeded(Exception):  # noqa: N818 - segnale interno, lo converte `tracked_write`
    """Tetto giornaliero raggiunto: porta l'inizio della finestra e i secondi al suo termine."""

    def __init__(self, window_start: datetime, retry_after: int) -> None:
        super().__init__("tetto delle scritture tracciate raggiunto")
        self.window_start = window_start
        self.retry_after = retry_after


@contextmanager
def tracked_write(ctx: RequestContext) -> Iterator[None]:
    """Da mettere FUORI da `family_tx`: scrive l'allarme dopo il rollback e risponde `429`."""
    try:
        yield
    except TrackedCapExceeded as cap:
        if _pepper is not None:
            _alarm_once(_pepper, ctx, cap.window_start)
        raise AppError(ErrorCode.RATE_LIMITED, {"retryAfterSeconds": cap.retry_after}) from None


def consume_tracked_write(tx: Tx, ctx: RequestContext) -> None:
    """Conta una scrittura tracciata in `tx`; oltre il limite solleva `TrackedCapExceeded`."""
    if _pepper is None or ctx.family_id is None:
        raise RuntimeError("tetto delle scritture tracciate non configurato")
    key = counter_key(_pepper, TRACKED_FAMILY, str(ctx.family_id))
    if tx.execute(_CONSUME, {"key": key, "limit": TRACKED_FAMILY.limit}).first() is not None:
        return
    row = tx.execute(_WINDOW).first()
    if row is None:
        raise RuntimeError("famiglia del contesto assente")
    start, end, now = row
    retry = max(1, ceil((end - now).total_seconds()))
    raise TrackedCapExceeded(start, retry)


def _alarm_once(pepper: bytes, ctx: RequestContext, window_start: datetime) -> None:
    """Un solo evento di sicurezza per famiglia e finestra; un guasto non cambia il `429`."""
    try:
        alarm_key = counter_key(pepper, _ALARM, str(ctx.family_id))
        with system_tx() as own:
            count = own.execute(
                _ALARM_BUMP, {"key": alarm_key, "window_start": window_start}
            ).scalar_one()
            if count == 1:
                security_log(
                    SecurityEvent(
                        event_type=EventType.RATE_LIMIT_EXCEEDED,
                        outcome="denied",
                        actor_kind="account",
                        actor_account_id=ctx.account_id,
                        actor_role=ctx.role,
                        family_id=ctx.family_id,
                        correlation_id=ctx.correlation_id,
                        details_json=json.dumps({"rule": TRACKED_FAMILY.name}),
                    ),
                    own,
                )
    except Exception as error:  # il 429 resta valido anche se l'allarme non si scrive
        _log.error("ratelimit.event_unrecorded", exception=type(error).__name__)
