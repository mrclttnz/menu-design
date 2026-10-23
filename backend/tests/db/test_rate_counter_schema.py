"""Tabella `rate_counter` (migrazione 0006, SL-03b): ADR-0006, 05-data §3.2, §4.1, §6.3.

SR-059 (contatori persistenti: tabella normale, non UNLOGGED), ADR-0006 (chiavi HMAC-SHA-256:
32 byte, nessun identificativo in chiaro; un solo upsert multiriga per richiesta; pulizia oraria
del worker con SQL normale come `menu_app`), THR-103 (transazione breve), THR-044 (privilegi).
`rate_block` è rinviata con CHG-020: NON deve esistere.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from support.owner import Owner

Connect = Callable[..., psycopg.Connection]
KEY_A = bytes(range(32))
KEY_B = bytes(range(1, 33))
WINDOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)

UPSERT = (
    "insert into app.rate_counter (key, window_start) values (%s, %s), (%s, %s) "
    "on conflict (key, window_start) do update set count = app.rate_counter.count + 1 "
    "returning key, count"
)


def test_the_table_has_exactly_the_documented_columns(catalog: psycopg.Connection) -> None:
    rows = catalog.execute(
        "select column_name, data_type, is_nullable, column_default "
        "from information_schema.columns "
        "where table_schema = 'app' and table_name = 'rate_counter'"
    ).fetchall()
    assert rows, "tabella app.rate_counter assente (migrazione 0006)"
    cols = {r[0]: r[1:] for r in rows}
    assert set(cols) == {"key", "window_start", "count"}, "nessun IP, email o altro in chiaro"
    assert cols["key"][:2] == ("bytea", "NO")
    assert cols["window_start"][:2] == ("timestamp with time zone", "NO")
    assert cols["count"][:2] == ("integer", "NO")
    assert cols["count"][2] == "1"


def test_the_primary_key_is_key_and_window_start(catalog: psycopg.Connection) -> None:
    cols = catalog.execute(
        "select a.attname from pg_index i join pg_attribute a on a.attrelid = i.indrelid "
        "and a.attnum = any(i.indkey) where i.indrelid = 'app.rate_counter'::regclass "
        "and i.indisprimary order by a.attname"
    ).fetchall()
    assert [c[0] for c in cols] == ["key", "window_start"]


def test_the_table_is_logged_so_counters_survive_a_crash_restart(
    catalog: psycopg.Connection,
) -> None:
    """05-data §4.1: «Tabella normale, non UNLOGGED: SR-059 chiede che i contatori sopravvivano»."""
    persistence = catalog.execute(
        "select relpersistence from pg_class where oid = 'app.rate_counter'::regclass"
    ).fetchone()
    assert persistence == ("p",)


def test_rate_block_is_not_created_it_is_deferred_with_chg_020(catalog: psycopg.Connection) -> None:
    assert catalog.execute("select to_regclass('app.rate_block')").fetchone() == (None,)


@pytest.mark.parametrize("length", [0, 16, 31, 33, 64])
def test_a_key_that_is_not_32_bytes_is_rejected(owner: Owner, length: int) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute(
            "insert into app.rate_counter (key, window_start) values (%s, %s)",
            (bytes(length), WINDOW),
        )


@pytest.mark.parametrize("value", [0, -1])
def test_a_count_below_one_is_rejected(owner: Owner, value: int) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute(
            "insert into app.rate_counter (key, window_start, count) values (%s, %s, %s)",
            (KEY_A, WINDOW, value),
        )


def test_the_same_key_and_window_cannot_be_inserted_twice(owner: Owner) -> None:
    owner.execute(
        "insert into app.rate_counter (key, window_start) values (%s, %s)", (KEY_A, WINDOW)
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        owner.execute(
            "insert into app.rate_counter (key, window_start) values (%s, %s)", (KEY_A, WINDOW)
        )


def test_the_same_key_in_another_window_is_a_separate_row(owner: Owner) -> None:
    for window in (WINDOW, WINDOW + timedelta(minutes=15)):
        owner.execute(
            "insert into app.rate_counter (key, window_start) values (%s, %s)", (KEY_A, window)
        )
    assert owner.scalar("select count(*) from app.rate_counter") == 2


def test_menu_app_runs_the_single_multirow_upsert_and_reads_the_new_counts(
    connect_app: Connect,
) -> None:
    """ADR-0006: un solo INSERT … ON CONFLICT multiriga, che restituisce chiave e conteggio."""
    with connect_app() as conn:
        first = conn.execute(UPSERT, (KEY_A, WINDOW, KEY_B, WINDOW)).fetchall()
        assert sorted((bytes(k), c) for k, c in first) == [(KEY_A, 1), (KEY_B, 1)]
        second = conn.execute(UPSERT, (KEY_A, WINDOW, KEY_B, WINDOW)).fetchall()
        assert sorted((bytes(k), c) for k, c in second) == [(KEY_A, 2), (KEY_B, 2)]


@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE"])
def test_menu_app_has_full_dml_on_rate_counter(catalog: psycopg.Connection, privilege: str) -> None:
    """05-data §3.2: sì/sì/sì/sì (l'upsert e la pulizia oraria del worker)."""
    got = catalog.execute(
        "select has_table_privilege('menu_app', 'app.rate_counter'::regclass, %s)", (privilege,)
    ).fetchone()
    assert got == (True,)


def test_the_hourly_cleanup_runs_as_menu_app_with_plain_sql(
    owner: Owner, connect_app: Connect
) -> None:
    """05-data §11: il worker cancella le finestre più vecchie di 2 giorni."""
    now = datetime.now(UTC)
    owner.execute(
        "insert into app.rate_counter (key, window_start) values (%s, %s), (%s, %s)",
        (KEY_A, now - timedelta(days=3), KEY_B, now),
    )
    with connect_app() as conn:
        deleted = conn.execute(
            "delete from app.rate_counter where window_start < %s", (now - timedelta(days=2),)
        ).rowcount
    assert deleted == 1
    assert owner.scalar("select count(*) from app.rate_counter") == 1


@pytest.mark.parametrize("role", ["menu_console"])
def test_the_console_role_has_no_access_to_the_counters(
    catalog: psycopg.Connection, role: str
) -> None:
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        got = catalog.execute(
            "select has_table_privilege(%s, 'app.rate_counter'::regclass, %s)", (role, privilege)
        ).fetchone()
        assert got == (False,), f"{role} non deve avere {privilege} su rate_counter"


def test_no_role_but_the_intended_ones_has_write_access(catalog: psycopg.Connection) -> None:
    rows = catalog.execute(
        "select grantee, privilege_type from information_schema.role_table_grants "
        "where table_schema = 'app' and table_name = 'rate_counter' and grantee <> 'menu_owner'"
    ).fetchall()
    grantees = {r[0] for r in rows}
    assert "PUBLIC" not in grantees
    writers = {r[0] for r in rows if r[1] in {"INSERT", "UPDATE", "DELETE"}}
    assert writers == {"menu_app"}


def test_menu_backup_can_read_but_not_write(catalog: psycopg.Connection) -> None:
    """Come per ogni altra tabella (05-data §3.2): il ruolo di backup legge, non scrive."""
    can = {
        p: catalog.execute(
            "select has_table_privilege('menu_backup', 'app.rate_counter'::regclass, %s)", (p,)
        ).fetchone()
        for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
    }
    assert can == {"SELECT": (True,), "INSERT": (False,), "UPDATE": (False,), "DELETE": (False,)}


def test_it_is_a_non_family_table_without_rls_and_without_family_column(
    catalog: psycopg.Connection,
) -> None:
    """05-data §6.3: `rate_counter` è nell'elenco chiuso delle tabelle senza RLS di famiglia."""
    cols = {
        r[0]
        for r in catalog.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'app' and table_name = 'rate_counter'"
        ).fetchall()
    }
    assert "family_id" not in cols
    assert catalog.execute(
        "select relrowsecurity from pg_class where oid = 'app.rate_counter'::regclass"
    ).fetchone() == (False,)


def test_menu_app_cannot_alter_or_truncate_the_counters(connect_app: Connect) -> None:
    for statement in (
        "alter table app.rate_counter add column ip text",
        "truncate app.rate_counter",
        "drop table app.rate_counter",
    ):
        with connect_app() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement.encode())


def test_the_migration_is_revision_0006_after_0005() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from support.paths import BACKEND

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    head: Any = script.get_revision("0006")
    assert head.revision == "0006"
    assert head.down_revision == "0005"
