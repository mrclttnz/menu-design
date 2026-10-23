"""Contatore per limitare il volume di un tipo di evento (SEC-SL04-001, CWE-779).

Usa la stessa tabella `rate_counter` e lo stesso formato di chiave del modulo `ratelimit`
(HMAC-SHA-256 con pepper di «nome\\0identificativo»: nessun ID in chiaro). Vive in `audit`
perché `access` (stesso strato di `ratelimit`) non può importarlo.
"""

import hashlib
import hmac

from sqlalchemy import text

from menu.tenancy import system_tx

_BUMP = text(
    "insert into app.rate_counter as c (key, window_start) "
    "values (:key, date_bin(make_interval(secs => :secs), app.now_utc(), "
    "timestamptz '2000-01-01 00:00:00+00')) "
    "on conflict (key, window_start) do update set count = c.count + 1 "
    "returning c.count"
)


def bump(pepper: bytes, name: str, identifier: str, window_seconds: int) -> int:
    """Incrementa il contatore della finestra corrente e ne restituisce il valore (1, 2, …)."""
    key = hmac.new(pepper, f"{name}\x00{identifier}".encode(), hashlib.sha256).digest()
    with system_tx() as tx:
        count = tx.execute(_BUMP, {"key": key, "secs": window_seconds}).scalar_one()
    return int(count)
