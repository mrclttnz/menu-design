"""`app.now_utc()` (05-data §11.1, plan §5.5, 08 §4.4; D-T1 = b + c; THR-048).

Una sola sorgente di "adesso" nel database. In produzione restituisce `now()`; solo l'ambiente
di test la sostituisce con `CREATE OR REPLACE` dall'helper `owner`. `menu_app` non può farlo.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from support import pg
from support.inventory import APP_ROLE, BACKUP_ROLE, CONSOLE_ROLE, OWNER_ROLE, app_functions
from support.owner import Owner


def _now_utc(catalog: psycopg.Connection) -> dict[str, object]:
    found = [f for f in app_functions(catalog) if f["name"] == "now_utc"]
    assert len(found) == 1, "app.now_utc() non esiste"
    return found[0]


def test_now_utc_is_now_in_production_schema(worker_db: str) -> None:
    """08 §4.4: subito dopo `upgrade head`, PRIMA di qualunque sostituzione.

    Si usa un clone fresco del template (non il database del worker, che può essere stato
    toccato da altri test): corpo = quello della migrazione e valore = now() nella stessa tx.
    """
    _, head = pg.ensure_templates()
    with pg.scratch_db(head) as fresh, pg.admin_connect(fresh) as conn:
        func = _now_utc(conn)
        src = conn.execute(
            "select prosrc from pg_proc where proname = 'now_utc' "
            "and pronamespace = 'app'::regnamespace"
        ).fetchone()
        assert src is not None
        assert re.sub(r"\s+", " ", src[0].strip().rstrip(";")).lower() == "select now()"
        assert func["language"] == "sql"
        assert func["volatility"] == "s", "STABLE"
        conn.autocommit = False
        same = conn.execute("select app.now_utc() = now()").fetchone()
        conn.rollback()
        assert same == (True,)


def test_now_utc_signature_ownership_and_grants(catalog: psycopg.Connection) -> None:
    func = _now_utc(catalog)
    assert func["owner"] == OWNER_ROLE
    assert func["secdef"] is False
    row = catalog.execute(
        "select pg_get_function_arguments(oid), pg_get_function_result(oid), proparallel "
        "from pg_proc where proname = 'now_utc' and pronamespace = 'app'::regnamespace"
    ).fetchone()
    assert row == ("", "timestamp with time zone", "s")
    assert catalog.execute(
        "select has_function_privilege(%s, 'app.now_utc()', 'EXECUTE')", (APP_ROLE,)
    ).fetchone() == (True,)
    public = catalog.execute(
        "select 1 from pg_proc p, aclexplode(p.proacl) a where p.proname = 'now_utc' "
        "and p.pronamespace = 'app'::regnamespace and a.grantee = 0"
    ).fetchall()
    assert public == [], "EXECUTE revocato a PUBLIC"
    for role in (CONSOLE_ROLE, BACKUP_ROLE):
        assert catalog.execute(
            "select has_function_privilege(%s, 'app.now_utc()', 'EXECUTE')", (role,)
        ).fetchone() == (False,), role


def test_no_test_hook_in_production_function(catalog: psycopg.Connection) -> None:
    """Nessun parametro, `current_setting`, `set_config` o ramo di test nel corpo."""
    row = catalog.execute(
        "select prosrc from pg_proc where proname = 'now_utc' "
        "and pronamespace = 'app'::regnamespace"
    ).fetchone()
    assert row is not None
    for forbidden in ("current_setting", "set_config", "case", "test", "coalesce"):
        assert forbidden not in row[0].lower()


@pytest.mark.sqlfunc("now_utc")
def test_now_utc_direct_call_matches_transaction_start(
    connect_app: Callable[..., psycopg.Connection],
) -> None:
    with connect_app(APP_ROLE, autocommit=False) as conn:
        row = conn.execute(b"select app.now_utc(), now(), app.now_utc() = now()").fetchone()
        assert row is not None
        assert row[2] is True
        assert row[0].tzinfo is not None


def test_menu_app_cannot_replace_or_alter_now_utc(
    connect_app: Callable[..., psycopg.Connection],
) -> None:
    """Nessun gancio in produzione: `menu_app` non è proprietario né ha CREATE su `app`."""
    for role in (APP_ROLE, CONSOLE_ROLE, BACKUP_ROLE):
        with connect_app(role) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    b"create or replace function app.now_utc() returns timestamptz "
                    b"language sql stable as $$ select '2000-01-01'::timestamptz $$"
                )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(b"alter function app.now_utc() rename to now_utc_old")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(b"drop function app.now_utc()")


def test_menu_app_cannot_shadow_now_utc_with_search_path(
    connect_app: Callable[..., psycopg.Connection],
) -> None:
    with connect_app(APP_ROLE) as conn:
        conn.execute(
            b"create function pg_temp.now_utc() returns timestamptz "
            b"language sql as $$ select '2000-01-01'::timestamptz $$"
        )
        conn.execute(b"set search_path = pg_temp, app")
        row = conn.execute(b"select app.now_utc() > '2001-01-01'::timestamptz").fetchone()
    assert row == (True,)


# --- sostituzione da parte dell'helper (solo test) -----------------------------------------


def test_owner_helper_replaces_now_utc_and_keeps_the_oid(
    owner: Owner,
    frozen_now: Callable[[datetime], None],
    connect_app: Callable[..., psycopg.Connection],
    catalog: psycopg.Connection,
) -> None:
    oid_before = _now_utc(catalog)["oid"]
    target = datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    frozen_now(target)
    with connect_app(APP_ROLE, autocommit=False) as conn:
        row = conn.execute(b"select app.now_utc()").fetchone()
    assert row is not None
    assert row[0] == target
    assert _now_utc(catalog)["oid"] == oid_before, "CREATE OR REPLACE mantiene l'OID"
    assert _now_utc(catalog)["volatility"] == "s"


def test_replaced_now_utc_drives_column_defaults_and_policies(
    owner: Owner,
    frozen_now: Callable[[datetime], None],
    connect_app: Callable[..., psycopg.Connection],
) -> None:
    """Default e policy che richiamano la funzione seguono la sostituzione (stesso OID)."""
    owner.script(
        "create table app.zz_clock (id int primary key, created_at timestamptz not null "
        "default app.now_utc()); grant select, insert on app.zz_clock to menu_app"
    )
    try:
        frozen_now(datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC))
        with connect_app(APP_ROLE) as conn:
            conn.execute(b"insert into app.zz_clock (id) values (1)")
            row = conn.execute(b"select created_at from app.zz_clock where id = 1").fetchone()
        assert row == (datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC),)
    finally:
        owner.execute("drop table if exists app.zz_clock")


def test_set_test_now_rejects_naive_datetimes(owner: Owner) -> None:
    with pytest.raises(AssertionError, match="naive"):
        owner.set_test_now(datetime(2026, 1, 1))  # noqa: DTZ001  (il test prova proprio questo)


def test_fixture_restores_the_production_function_between_tests(
    owner: Owner, catalog: psycopg.Connection
) -> None:
    """Secondo test del 08 §4.4: dopo ogni sostituzione la fixture ripristina il corpo."""
    row = catalog.execute(
        "select prosrc from pg_proc where proname = 'now_utc' "
        "and pronamespace = 'app'::regnamespace"
    ).fetchone()
    assert row is not None
    assert re.sub(r"\s+", " ", row[0].strip().rstrip(";")).lower() == "select now()"
    delta = owner.scalar("select app.now_utc()") - datetime.now(UTC)
    assert abs(delta) < timedelta(seconds=30)
