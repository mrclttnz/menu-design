"""Modulo tenancy (strato 2): engine, `family_tx`, `system_tx` (ADR-0003, 05-data §6).

Unico punto in cui nasce un engine o una connessione. Il contesto di famiglia si imposta solo
con `set_config(..., true)`, cioè locale alla transazione: non sopravvive al riuso della
connessione dal pool (THR-026, THR-027). L'app lavora sempre come `menu_app` (SR-042).
"""

from menu.tenancy.engine import Tx, dispose, family_tx, init, ping, system_tx

__all__ = ["Tx", "dispose", "family_tx", "init", "ping", "system_tx"]
