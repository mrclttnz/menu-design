"""Inventario delle funzioni SECURITY DEFINER (05-data §3.3, 08 §6.5; THR-044).

In SL-00b l'insieme atteso è VUOTO (nessuna funzione privilegiata). Il controllo è provato
con funzioni sintetiche: un inventario che non sa fallire non vale nulla.
"""

import psycopg

from support.inventory import (
    EXPECTED_SECDEF_NOW,
    SQL_FUNCTIONS_NOW,
    app_functions,
    secdef_problems,
)
from support.owner import Owner


def test_migration_0001_created_the_context_functions(catalog: psycopg.Connection) -> None:
    """Precondizione: lo schema ha davvero le funzioni di 0001 (altrimenti l'inventario è vuoto
    solo perché non esiste nulla)."""
    names = {f["name"] for f in app_functions(catalog)}
    assert names >= SQL_FUNCTIONS_NOW


def test_secdef_inventory_is_empty_in_sl_00b(catalog: psycopg.Connection) -> None:
    assert frozenset() == EXPECTED_SECDEF_NOW
    assert secdef_problems(catalog, EXPECTED_SECDEF_NOW) == []


def test_context_functions_are_security_invoker(catalog: psycopg.Connection) -> None:
    by_name = {f["name"]: f for f in app_functions(catalog)}
    for name in SQL_FUNCTIONS_NOW:
        assert name in by_name, f"app.{name} assente"
        assert by_name[name]["secdef"] is False, f"app.{name} non deve essere SECURITY DEFINER"


def test_inventory_detects_an_unexpected_secdef_function(
    owner: Owner, catalog: psycopg.Connection
) -> None:
    owner.script(
        "create function app.zz_secdef() returns int language sql security definer "
        "set search_path = app, pg_temp as 'select 1'; "
        "revoke execute on function app.zz_secdef() from public"
    )
    try:
        problems = secdef_problems(catalog, EXPECTED_SECDEF_NOW)
    finally:
        owner.execute("drop function app.zz_secdef()")
    assert problems == ["funzione SECURITY DEFINER non prevista: zz_secdef"]


def test_inventory_detects_missing_search_path_and_public_execute(
    owner: Owner, catalog: psycopg.Connection
) -> None:
    owner.script(
        "create function app.zz_bad() returns int language sql security definer as 'select 1'; "
        "grant execute on function app.zz_bad() to public"
    )
    try:
        problems = secdef_problems(catalog, frozenset({"zz_bad"}))
    finally:
        owner.execute("drop function app.zz_bad()")
    assert any("search_path" in p for p in problems)
    assert any("PUBLIC" in p for p in problems)


def test_inventory_detects_an_expected_function_that_is_missing(
    catalog: psycopg.Connection,
) -> None:
    assert secdef_problems(catalog, frozenset({"session_resolve"})) == [
        "funzione SECURITY DEFINER attesa e assente: session_resolve"
    ]
