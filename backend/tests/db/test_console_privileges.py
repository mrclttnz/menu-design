"""Privilegi sulle tabelle nuove di SL-02 (05-data §3.1-3.2, §6.4; SR-012, SR-040, SR-057;
THR-051, THR-044). `menu_console` non ha privilegi su nessuna tabella; `menu_app` segue la
matrice di §3.2; `menu_backup` legge tutto.
"""

from collections.abc import Callable

import psycopg
import pytest

from support.inventory import APPEND_ONLY_FAMILY_TABLES, EXPECTED_FAMILY_TABLES_NOW, app_tables

Connect = Callable[..., psycopg.Connection]
# `security_event.id` è GENERATED ALWAYS: l'UPDATE fallirebbe prima del controllo dei permessi.
_UPDATE_COLUMN = {
    "family_default_meal": "meal_type",
    "security_event": "outcome",
    "dish_course": "course_id",
}
PRIVS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


@pytest.mark.parametrize("table", sorted(EXPECTED_FAMILY_TABLES_NOW | {"security_event"}))
def test_menu_console_is_denied_select_on_every_new_table(connect_app: Connect, table: str) -> None:
    """SR-040: "permesso negato" (non zero righe) sulle tabelle, anche sul registro."""
    with connect_app("menu_console") as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(f"select * from app.{table}".encode())  # noqa: S608


@pytest.mark.parametrize("table", sorted(EXPECTED_FAMILY_TABLES_NOW | {"security_event"}))
@pytest.mark.parametrize(
    "template",
    [
        "insert into app.{t} default values",
        "update app.{t} set {c} = {c}",
        "delete from app.{t}",
    ],
)
def test_menu_console_cannot_write_tables_directly(
    connect_app: Connect, table: str, template: str
) -> None:
    sql = template.format(t=table, c=_UPDATE_COLUMN.get(table, "id"))
    with connect_app("menu_console") as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(sql.encode())


def test_menu_console_has_no_privilege_on_any_table_or_sequence(
    catalog: psycopg.Connection,
) -> None:
    """Inventario: vale anche per le tabelle delle slice future (nessun GRANT dimenticato)."""
    tables = app_tables(catalog)
    assert set(tables) >= EXPECTED_FAMILY_TABLES_NOW | {"security_event"}
    granted = [
        f"{name}:{priv}"
        for name in tables
        for priv in PRIVS
        if catalog.execute(
            "select has_table_privilege('menu_console', %s::regclass, %s)",
            (f"app.{name}", priv),
        ).fetchone()
        == (True,)
    ]
    assert granted == []
    seq = catalog.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'app' and c.relkind = 'S' "
        "and case when c.relkind = 'S' then "
        "has_sequence_privilege('menu_console', c.oid, 'USAGE,SELECT,UPDATE') end"
    ).fetchall()
    assert seq == []


# `change_event` è di sola aggiunta (SELECT e INSERT): vedi test_change_event_schema.py.
@pytest.mark.parametrize("table", sorted(EXPECTED_FAMILY_TABLES_NOW - APPEND_ONLY_FAMILY_TABLES))
def test_menu_app_has_full_dml_on_family_tables(catalog: psycopg.Connection, table: str) -> None:
    """05-data §3.2: tabelle di famiglia sì/sì/sì/sì, sempre sotto RLS."""
    for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        row = catalog.execute(
            "select has_table_privilege('menu_app', %s::regclass, %s)", (f"app.{table}", priv)
        ).fetchone()
        assert row == (True,), f"menu_app senza {priv} su {table}"


def test_menu_app_has_insert_only_on_security_event(catalog: psycopg.Connection) -> None:
    got = {
        priv: catalog.execute(
            "select has_table_privilege('menu_app', 'app.security_event'::regclass, %s)", (priv,)
        ).fetchone()
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
    }
    assert got == {
        "SELECT": (False,),
        "INSERT": (True,),
        "UPDATE": (False,),
        "DELETE": (False,),
        "TRUNCATE": (False,),
    }


def test_menu_backup_can_select_every_app_table(catalog: psycopg.Connection) -> None:
    tables = app_tables(catalog)
    assert set(tables) >= EXPECTED_FAMILY_TABLES_NOW | {"security_event"}
    denied = [
        name
        for name in tables
        if catalog.execute(
            "select has_table_privilege('menu_backup', %s::regclass, 'SELECT')", (f"app.{name}",)
        ).fetchone()
        != (True,)
    ]
    assert denied == []
