"""Nessun `now()` nudo nello schema `app` (08 §10.8, 05-data §11.1, plan §5.5; D-T1).

Il catalogo (funzioni, default, policy, viste, vincoli, trigger) non contiene
now()/CURRENT_TIMESTAMP/... L'unica eccezione è il corpo di `app.now_utc()`.
"""

import psycopg
import pytest

from support.inventory import bare_time_problems, forbidden_time_expressions
from support.owner import Owner


def test_catalog_has_no_bare_time_expressions(catalog: psycopg.Connection) -> None:
    assert bare_time_problems(catalog) == []


def test_catalog_has_the_objects_the_check_is_about(catalog: psycopg.Connection) -> None:
    """Precondizione: lo schema non è vuoto (il controllo sopra non passa a vuoto)."""
    count = catalog.execute(
        "select count(*) from pg_proc where pronamespace = 'app'::regnamespace"
    ).fetchone()
    assert count is not None
    assert count[0] >= 4


@pytest.mark.parametrize(
    "text",
    [
        "select now()", "select NOW ( )", "select pg_catalog.now()",
        "CURRENT_TIMESTAMP", "current_timestamp(3)", "CURRENT_DATE", "current_time",
        "LOCALTIMESTAMP", "localtime", "transaction_timestamp()", "statement_timestamp()",
        "clock_timestamp()", "timeofday()", "'now'::timestamptz",
    ],
)  # fmt: skip
def test_matcher_recognises_every_forbidden_expression(text: str) -> None:
    assert forbidden_time_expressions(text) != []


@pytest.mark.parametrize(
    "text",
    ["select app.now_utc()", "now_utc()", "created_at timestamptz", "knowledge", "current_user"],
)
def test_matcher_accepts_the_replacement_and_lookalikes(text: str) -> None:
    assert forbidden_time_expressions(text) == []


# --- il controllo sul catalogo sa fallire: oggetti sintetici con orologio nudo ---------------


def _problems_with(
    owner: Owner, catalog: psycopg.Connection, setup: str, cleanup: str
) -> list[str]:
    owner.script(setup)
    try:
        return bare_time_problems(catalog)
    finally:
        owner.script(cleanup)


def test_check_flags_a_function_using_now(owner: Owner, catalog: psycopg.Connection) -> None:
    problems = _problems_with(
        owner, catalog,
        "create function app.zz_f() returns timestamptz language sql stable as 'select now()'",
        "drop function app.zz_f()",
    )  # fmt: skip
    assert any(p.startswith("funzione zz_f") for p in problems), problems


def test_check_flags_plpgsql_with_clock_timestamp(
    owner: Owner, catalog: psycopg.Connection
) -> None:
    problems = _problems_with(
        owner, catalog,
        "create function app.zz_g() returns timestamptz language plpgsql as "
        "$$ begin return clock_timestamp(); end $$",
        "drop function app.zz_g()",
    )  # fmt: skip
    assert any(p.startswith("funzione zz_g") for p in problems), problems


def test_check_flags_a_column_default(owner: Owner, catalog: psycopg.Connection) -> None:
    problems = _problems_with(
        owner, catalog,
        "create table app.zz_t (created_at timestamptz default now())",
        "drop table app.zz_t",
    )  # fmt: skip
    assert any(p.startswith("default zz_t.created_at") for p in problems), problems


def test_check_flags_a_generated_or_current_date_default(
    owner: Owner, catalog: psycopg.Connection
) -> None:
    problems = _problems_with(
        owner, catalog,
        "create table app.zz_d (d date default current_date)",
        "drop table app.zz_d",
    )  # fmt: skip
    assert any(p.startswith("default zz_d.d") for p in problems), problems


def test_check_flags_a_policy(owner: Owner, catalog: psycopg.Connection) -> None:
    problems = _problems_with(
        owner, catalog,
        "create table app.zz_p (at timestamptz); alter table app.zz_p enable row level security;"
        " create policy p_x on app.zz_p for select to menu_app using (at < now())",
        "drop table app.zz_p",
    )  # fmt: skip
    assert any(p.startswith("policy zz_p.p_x") for p in problems), problems


def test_check_flags_a_view(owner: Owner, catalog: psycopg.Connection) -> None:
    problems = _problems_with(
        owner, catalog,
        "create view app.zz_v as select current_timestamp as t",
        "drop view app.zz_v",
    )  # fmt: skip
    assert any(p.startswith("vista zz_v") for p in problems), problems


def test_check_flags_a_trigger_condition(owner: Owner, catalog: psycopg.Connection) -> None:
    problems = _problems_with(
        owner, catalog,
        "create table app.zz_r (at timestamptz); "
        "create function app.zz_trg() returns trigger language plpgsql as "
        "$$ begin return new; end $$; "
        "create trigger trg_x before insert on app.zz_r for each row "
        "when (new.at < app.now_utc()) execute function app.zz_trg()",
        "drop table app.zz_r; drop function app.zz_trg()",
    )  # fmt: skip
    # `app.now_utc()` è lecito nel trigger: nessun problema attribuibile a zz_r/zz_trg.
    assert [p for p in problems if "zz_r" in p or "zz_trg" in p] == []


def test_check_accepts_now_utc_in_defaults_and_functions(
    owner: Owner, catalog: psycopg.Connection
) -> None:
    problems = _problems_with(
        owner, catalog,
        "create table app.zz_ok (created_at timestamptz not null default app.now_utc()); "
        "create function app.zz_okf() returns timestamptz language sql stable "
        "as 'select app.now_utc()'",
        "drop table app.zz_ok; drop function app.zz_okf()",
    )  # fmt: skip
    assert [p for p in problems if "zz_ok" in p] == []
