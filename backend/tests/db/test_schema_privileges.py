"""Privilegi sugli schemi e sulle funzioni (05-data §3.1 "Supabase e schemi"; THR-044, SR-075).

Nessun `CREATE` su `app` e `public` per ruoli diversi da `menu_owner`; nessun accesso per
PUBLIC; `ALTER DEFAULT PRIVILEGES` toglie EXECUTE a PUBLIC sulle funzioni nuove di `menu_owner`.
"""

from typing import Any

import psycopg
import pytest

from support.inventory import (
    APP_ROLE,
    BACKUP_ROLE,
    CONSOLE_ROLE,
    LOGIN_ROLES,
    OWNER_ROLE,
    public_can_execute,
    role_rows,
    schema_create_grantees,
)
from support.owner import Owner


def test_only_menu_owner_can_create_in_schema_app(catalog: psycopg.Connection) -> None:
    assert set(role_rows(catalog)) == set(LOGIN_ROLES), "precondizione: i quattro ruoli esistono"
    assert schema_create_grantees(catalog, "app") == {OWNER_ROLE}


def test_nobody_but_menu_owner_can_create_in_schema_public(catalog: psycopg.Connection) -> None:
    assert set(role_rows(catalog)) == set(LOGIN_ROLES), "precondizione: i quattro ruoli esistono"
    assert schema_create_grantees(catalog, "public") <= {OWNER_ROLE}


@pytest.mark.parametrize("role", [APP_ROLE, CONSOLE_ROLE, BACKUP_ROLE])
@pytest.mark.parametrize(
    "ddl",
    [
        "create table {schema}.zz_attack (id int)",
        "create function {schema}.zz_attack() returns int language sql as 'select 1'",
        "create view {schema}.zz_attack as select 1 as one",
    ],
)
@pytest.mark.parametrize("schema", ["app", "public"])
def test_non_owner_roles_cannot_create_objects(
    connect_app: Any,
    role: str,
    ddl: str,
    schema: str,
) -> None:
    """THR-044 / THR-026: nessun ruolo applicativo può creare oggetti (nessun DDL)."""
    with connect_app(role) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(ddl.format(schema=schema).encode())


def test_menu_app_cannot_hijack_now_utc_via_temp_schema_functions(connect_app: Any) -> None:
    """Una funzione omonima in `pg_temp` non sostituisce quella qualificata di `app`."""
    with connect_app(APP_ROLE) as conn:
        conn.execute(
            b"create function pg_temp.now_utc() returns timestamptz "
            b"language sql as $$ select '1999-01-01'::timestamptz $$"
        )
        row = conn.execute(b"select app.now_utc() <> '1999-01-01'::timestamptz").fetchone()
    assert row == (True,)


@pytest.mark.parametrize("role", [CONSOLE_ROLE, BACKUP_ROLE])
def test_console_and_backup_have_no_execute_on_now_utc(connect_app: Any, role: str) -> None:
    """05-data §3.2/§11.1: EXECUTE su app.now_utc() solo a `menu_app` (e al proprietario)."""
    with connect_app(role) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(b"select app.now_utc()")


def test_usage_on_schema_app_only_for_the_intended_roles(catalog: psycopg.Connection) -> None:
    assert set(role_rows(catalog)) == set(LOGIN_ROLES), "precondizione: i quattro ruoli esistono"
    usage = {
        role: catalog.execute("select has_schema_privilege(%s, 'app', 'USAGE')", (role,)).fetchone()
        for role in sorted(LOGIN_ROLES)
    }
    assert usage == {r: (True,) for r in sorted(LOGIN_ROLES)}
    public_usage = catalog.execute(
        "select 1 from pg_namespace n, aclexplode(n.nspacl) a "
        "where n.nspname = 'app' and a.grantee = 0 and a.privilege_type = 'USAGE'"
    ).fetchall()
    assert public_usage == [], "REVOKE ALL ON SCHEMA app FROM PUBLIC"


def test_new_owner_functions_are_not_executable_by_public_nor_other_roles(
    owner: Owner, catalog: psycopg.Connection
) -> None:
    """`ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`."""
    owner.execute("create function app.zz_default_priv() returns int language sql as 'select 1'")
    try:
        row = catalog.execute(
            "select p.oid from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'app' and p.proname = 'zz_default_priv'"
        ).fetchone()
        assert row is not None
        assert not public_can_execute(catalog, row[0])
        for role in (APP_ROLE, CONSOLE_ROLE, BACKUP_ROLE):
            assert catalog.execute(
                "select has_function_privilege(%s, %s, 'EXECUTE')", (role, row[0])
            ).fetchone() == (False,), role
    finally:
        owner.execute("drop function if exists app.zz_default_priv()")


@pytest.mark.parametrize("role", [APP_ROLE, CONSOLE_ROLE])
def test_alembic_version_is_not_accessible_to_runtime_roles(
    catalog: psycopg.Connection, role: str
) -> None:
    """05-data §6.3: `alembic_version` solo `menu_owner` (app e console non la vedono)."""
    allowed = catalog.execute(
        "select has_table_privilege(%s, 'app.alembic_version', 'SELECT, INSERT, UPDATE, DELETE')",
        (role,),
    ).fetchone()
    assert allowed == (False,)
