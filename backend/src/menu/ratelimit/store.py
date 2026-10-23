"""Contatori in PostgreSQL: un solo `INSERT … ON CONFLICT` per richiesta (ADR-0006, OBJ-07).

La finestra e l'attesa si calcolano con l'orologio del database (`app.now_utc()`), mai con quello
del processo: istanze diverse concordano, e i test lo spostano. Chiave = HMAC-SHA-256 con pepper
del nome della regola e dell'identificativo: nessun IP, ID o email in chiaro nella tabella.
"""

import hashlib
import hmac
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from math import ceil

from sqlalchemy import text

from menu.ratelimit.rules import MAX_WINDOW_SECONDS, Rule
from menu.tenancy import system_tx

_UPSERT = text(
    "insert into app.rate_counter as c (key, window_start) "
    "select r.key, date_bin(make_interval(secs => r.secs), app.now_utc(), "
    "timestamptz '2000-01-01 00:00:00+00') "
    "from unnest(cast(:keys as bytea[]), cast(:secs as integer[])) as r(key, secs) "
    "order by r.key "  # stesso ordine di blocco in richieste concorrenti: niente deadlock
    "on conflict (key, window_start) do update set count = c.count + 1 "
    "returning c.key, c.count, c.window_start, app.now_utc()"
)


@dataclass(frozen=True)
class Hit:
    """Una regola applicata a un identificativo (IP, ID di sessione o di account)."""

    rule: Rule
    identifier: str


@dataclass(frozen=True)
class Exceeded:
    rule: Rule
    count: int

    @property
    def first_crossing(self) -> bool:
        """Vero solo per la richiesta che supera il limite per prima nella finestra."""
        return self.count == self.rule.limit + 1


@dataclass(frozen=True)
class Verdict:
    exceeded: tuple[Exceeded, ...]
    retry_after: int  # secondi fino alla fine della finestra più lunga superata (1..900)

    @property
    def allowed(self) -> bool:
        return not self.exceeded


def counter_key(pepper: bytes, rule: Rule, identifier: str) -> bytes:
    return hmac.new(pepper, f"{rule.name}\x00{identifier}".encode(), hashlib.sha256).digest()


def hit(pepper: bytes, hits: Sequence[Hit]) -> Verdict:
    """Incrementa tutti i contatori in una transazione breve; solleva se il database fallisce."""
    by_key = {counter_key(pepper, h.rule, h.identifier): h.rule for h in hits}
    if not by_key:
        return Verdict((), 1)
    keys = list(by_key)
    with system_tx() as tx:
        rows = tx.execute(
            _UPSERT, {"keys": keys, "secs": [by_key[k].window_seconds for k in keys]}
        ).all()
    exceeded: list[Exceeded] = []
    retry = 1
    for key, count, window_start, now in rows:
        rule = by_key[bytes(key)]
        if count > rule.limit:
            exceeded.append(Exceeded(rule, count))
            remaining = window_start + timedelta(seconds=rule.window_seconds) - now
            retry = max(retry, ceil(remaining.total_seconds()))
    exceeded.sort(key=lambda e: e.rule.name)
    return Verdict(tuple(exceeded), min(MAX_WINDOW_SECONDS, retry))
