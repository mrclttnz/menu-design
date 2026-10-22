"""Inventario delle funzioni SECURITY DEFINER (05-data §3.3, 08 §6.5; THR-044).

SL-02: l'insieme atteso è esattamente `console_bootstrap_family`, `console_security_events`,
`console_audit_note` (ADR-0011), eseguibili solo da `menu_console`. Il controllo è provato
anche con funzioni sintetiche: un inventario che non sa fallire non vale nulla.
"""

import psycopg
import pytest

from support.inventory import (
    EXPECTED_SECDEF_NOW,
    SQL_FUNCTIONS_NOW,
    app_functions,
    public_can_execute,
    secdef_problems,
)
from support.owner import Owner


def test_migration_0001_created_the_context_functions(catalog: psycopg.Connection) -> None:
    """Precondizione: lo schema ha davvero le funzioni di 0001 (altrimenti l'inventario è vuoto
    solo perché non esiste nulla)."""
    names = {f["name"] for f in app_functions(catalog)}
    assert names >= SQL_FUNCTIONS_NOW


def test_secdef_inventory_is_the_three_console_functions_of_sl_02(
    catalog: psycopg.Connection,
) -> None:
    assert {
        "console_bootstrap_family",
        "console_security_events",
        "console_audit_note",
    } == EXPECTED_SECDEF_NOW
    assert secdef_problems(catalog, EXPECTED_SECDEF_NOW) == []


@pytest.mark.parametrize("name", sorted(EXPECTED_SECDEF_NOW))
def test_console_functions_are_executable_only_by_menu_console(
    catalog: psycopg.Connection, name: str
) -> None:
    """THR-044, SR-040: EXECUTE al solo ruolo previsto, mai a PUBLIC né a `menu_app`."""
    oids = [f["oid"] for f in app_functions(catalog) if f["name"] == name]
    assert len(oids) == 1, f"app.{name} assente o in più firme"
    can = {
        role: catalog.execute(
            "select has_function_privilege(%s, %s::oid, 'EXECUTE')", (role, oids[0])
        ).fetchone()
        for role in ("menu_console", "menu_app", "menu_backup", "menu_owner")
    }
    assert can["menu_console"] == (True,)
    assert can["menu_app"] == (False,)
    assert can["menu_backup"] == (False,)
    assert not public_can_execute(catalog, oids[0])


@pytest.mark.parametrize("name", sorted(EXPECTED_SECDEF_NOW))
def test_secdef_functions_are_plpgsql(catalog: psycopg.Connection, name: str) -> None:
    """05-data §3.3: tutte plpgsql (così compaiono in pg_stat_user_functions)."""
    found = {f["name"]: f for f in app_functions(catalog)}
    assert found[name]["language"] == "plpgsql"


def test_no_app_function_is_executable_by_public(catalog: psycopg.Connection) -> None:
    """08 §6.5: funzioni INVOKER e trigger comprese (ALTER DEFAULT PRIVILEGES di bootstrap)."""
    open_to_public = [
        f["name"] for f in app_functions(catalog) if public_can_execute(catalog, f["oid"])
    ]
    assert open_to_public == []


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
    assert secdef_problems(catalog, EXPECTED_SECDEF_NOW | {"session_resolve"}) == [
        "funzione SECURITY DEFINER attesa e assente: session_resolve"
    ]
