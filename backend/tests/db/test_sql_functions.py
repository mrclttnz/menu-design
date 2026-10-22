"""Funzioni LANGUAGE sql dello schema `app` (08 §6.7, 05-data §3.2/§6.1/§11.1).

Elenco chiuso `INLINABLE_SQL_FUNCTIONS`; ognuna ha una chiamata diretta marcata `sqlfunc`
(`track_functions` non conta le funzioni inlinate). Cartella di test: db.
"""

import ast
from collections.abc import Callable
from uuid import uuid4

import psycopg
import pytest

from support.inventory import (
    APP_ROLE,
    INLINABLE_SQL_FUNCTIONS,
    SQL_FUNCTIONS_NOW,
    app_functions,
    sql_function_problems,
)
from support.owner import Owner
from support.paths import TESTS

Connect = Callable[..., psycopg.Connection]


def test_sql_function_inventory_is_consistent(catalog: psycopg.Connection) -> None:
    assert sql_function_problems(catalog, SQL_FUNCTIONS_NOW) == []


def test_sql_function_inventory_flags_an_unlisted_sql_function(
    owner: Owner,
    catalog: psycopg.Connection,
) -> None:
    owner.execute("create function app.zz_sql() returns int language sql as 'select 1'")
    try:
        problems = sql_function_problems(catalog, SQL_FUNCTIONS_NOW)
    finally:
        owner.execute("drop function app.zz_sql()")
    assert any("zz_sql" in p and "INLINABLE_SQL_FUNCTIONS" in p for p in problems), problems


def test_every_expected_sql_function_has_a_direct_call_test() -> None:
    """Ogni funzione attesa ha un test con `@pytest.mark.sqlfunc("<nome>")` in tests/db."""
    marked: set[str] = set()
    for path in (TESTS / "db").glob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("mark.sqlfunc"):
                marked.add(ast.literal_eval(node.args[0]))
    assert marked >= set(SQL_FUNCTIONS_NOW), SQL_FUNCTIONS_NOW - marked
    assert marked <= INLINABLE_SQL_FUNCTIONS


def test_context_functions_are_stable_sql_invoker(catalog: psycopg.Connection) -> None:
    by_name = {f["name"]: f for f in app_functions(catalog)}
    for name in ("current_family_id", "current_account_id", "now_utc"):
        assert by_name[name]["language"] == "sql"
        assert by_name[name]["volatility"] == "s"
    assert by_name["search_norm"]["volatility"] == "i"
    assert by_name["search_norm"]["strict"] is True


@pytest.mark.sqlfunc("current_family_id")
def test_current_family_id_reads_the_transaction_local_setting(connect_app: Connect) -> None:
    fam = uuid4()
    with connect_app(APP_ROLE, autocommit=False) as conn:
        assert conn.execute(b"select app.current_family_id()").fetchone() == (None,)
        conn.execute("select set_config('app.family_id', %s, true)", (str(fam),))
        assert conn.execute(b"select app.current_family_id()").fetchone() == (fam,)
        conn.execute(b"select set_config('app.family_id', '', true)")
        assert conn.execute(b"select app.current_family_id()").fetchone() == (None,)


@pytest.mark.sqlfunc("current_account_id")
def test_current_account_id_reads_the_transaction_local_setting(connect_app: Connect) -> None:
    acc = uuid4()
    with connect_app(APP_ROLE, autocommit=False) as conn:
        assert conn.execute(b"select app.current_account_id()").fetchone() == (None,)
        conn.execute("select set_config('app.account_id', %s, true)", (str(acc),))
        assert conn.execute(b"select app.current_account_id()").fetchone() == (acc,)
        conn.rollback()
        assert conn.execute(b"select app.current_account_id()").fetchone() == (None,)


@pytest.mark.sqlfunc("search_norm")
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Crème", "creme"),
        ("creme", "creme"),
        ("Crème Brûlée", "creme brulee"),
        ("ÀÈÌÒÙ àèìòù", "aeiou aeiou"),
        ("Pasta al Pomodoro", "pasta al pomodoro"),
        ("", ""),
    ],
)
def test_search_norm_direct_call(connect_app: Connect, raw: str, expected: str) -> None:
    with connect_app(APP_ROLE) as conn:
        row = conn.execute("select app.search_norm(%s)", (raw,)).fetchone()
    assert row == (expected,)


@pytest.mark.sqlfunc("search_norm")
def test_search_norm_is_strict_and_runs_as_menu_app(connect_app: Connect) -> None:
    """NULL → NULL (STRICT) e `menu_app` può usare `extensions.unaccent` attraverso la funzione."""
    with connect_app(APP_ROLE) as conn:
        assert conn.execute(b"select app.search_norm(null)").fetchone() == (None,)


@pytest.mark.sqlfunc("search_norm")
def test_search_norm_treats_sql_metacharacters_as_plain_text(connect_app: Connect) -> None:
    """THR-025: il valore è un parametro, non SQL; lo schema resta intatto."""
    payload = "x'; DROP SCHEMA app CASCADE; --"
    with connect_app(APP_ROLE) as conn:
        row = conn.execute("select app.search_norm(%s)", (payload,)).fetchone()
        still = conn.execute(b"select count(*) from pg_namespace where nspname = 'app'").fetchone()
    assert row == (payload.lower(),)
    assert still == (1,)


def test_search_norm_does_not_depend_on_the_callers_search_path(connect_app: Connect) -> None:
    """THR-044: `unaccent` è qualificato con `extensions` e il dizionario è esplicito."""
    with connect_app(APP_ROLE) as conn:
        conn.execute(b"set search_path = pg_temp")
        row = conn.execute("select app.search_norm(%s)", ("Crème",)).fetchone()
    assert row == ("creme",)
