# Fixture per `semgrep --test .semgrep` (non importato né eseguito).
import sqlalchemy as sa
from sqlalchemy import (
    AsyncSession,
    Session,
    async_sessionmaker,
    create_async_engine,
    create_engine,
    literal_column,
    sessionmaker,
    text,
)


def bad(name: str) -> None:
    # ruleid: menu-sqlalchemy-text-formatted
    text(f"select * from t where n = '{name}'")
    # ruleid: menu-sqlalchemy-text-formatted
    text("select {}".format(name))
    # ruleid: menu-sqlalchemy-text-formatted
    text("select * from t where n = '" + name + "'")
    # ruleid: menu-sqlalchemy-text-formatted
    text("select * from t where n = '%s'" % name)
    # ok: menu-sqlalchemy-text-formatted
    text("select * from t where n = :n")


def session_scope(engine: object) -> None:
    # ruleid: menu-sqlalchemy-session-outside-tenancy
    Session(engine)
    # ruleid: menu-sqlalchemy-session-outside-tenancy
    sessionmaker(engine)
    # ruleid: menu-sqlalchemy-session-outside-tenancy
    create_engine("postgresql://x")


def set_config_scope(conn: object) -> None:
    # ruleid: menu-set-config-session-scope, menu-set-config-outside-tenancy
    conn.execute("select set_config('app.tenant_id', 'x', false)")
    # ruleid: menu-set-config-session-scope
    conn.execute("SET app.tenant_id = 'x'")
    # ok: menu-set-config-session-scope
    # ruleid: menu-set-config-outside-tenancy
    conn.execute("select set_config('app.tenant_id', 'x', true)")
    # ok: menu-set-config-session-scope
    conn.execute("SET LOCAL app.tenant_id = 'x'")


def text_variants(name: str, conn: object) -> None:
    # SEC-SL00a-007: text() ammette SOLO un letterale, anche via variabile o alias del modulo.
    query = f"select * from t where n = '{name}'"
    # ruleid: menu-sqlalchemy-text-formatted
    text(query)
    # ruleid: menu-sqlalchemy-text-formatted
    sa.text(query)
    # ruleid: menu-sqlalchemy-text-formatted
    sa.text("select * from t where n = '" + name + "'")
    # ruleid: menu-sqlalchemy-text-formatted
    text(name + " from t")
    # ruleid: menu-sqlalchemy-text-formatted
    text(name)
    # ok: menu-sqlalchemy-text-formatted
    sa.text("select * from t where n = :n")
    # ok: menu-sqlalchemy-text-formatted
    text("select 1")


def other_raw_sql_entry_points(name: str, conn: object) -> None:
    # ruleid: menu-sqlalchemy-text-formatted
    literal_column(f"{name}")
    # ruleid: menu-sqlalchemy-text-formatted
    literal_column(name)
    # ok: menu-sqlalchemy-text-formatted
    literal_column("count(*)")
    # ruleid: menu-sqlalchemy-text-formatted
    conn.exec_driver_sql(f"select {name}")
    # ruleid: menu-sqlalchemy-text-formatted
    conn.exec_driver_sql(name)
    # ok: menu-sqlalchemy-text-formatted
    conn.exec_driver_sql("select 1")


def async_session_scope(engine: object) -> None:
    # ruleid: menu-sqlalchemy-session-outside-tenancy
    create_async_engine("postgresql+psycopg://x")
    # ruleid: menu-sqlalchemy-session-outside-tenancy
    AsyncSession(engine)
    # ruleid: menu-sqlalchemy-session-outside-tenancy
    async_sessionmaker(engine)


def session_level_statements(conn: object) -> None:
    # ruleid: menu-set-config-session-scope
    conn.execute("SET ROLE menu_owner")
    # ruleid: menu-set-config-session-scope
    conn.execute("set search_path = public")
    # ruleid: menu-set-config-session-scope
    conn.execute("SET SESSION app.family_id = 'x'")
    # ruleid: menu-set-config-session-scope
    conn.execute("SET SESSION ROLE menu_owner")
    # ruleid: menu-set-config-session-scope
    conn.execute("RESET ROLE")
    # ruleid: menu-set-config-session-scope
    conn.execute("SET SESSION AUTHORIZATION menu_owner")
    # ruleid: menu-set-config-session-scope, menu-set-config-outside-tenancy
    conn.execute("select set_config('app.family_id', 'x', False)")
    # ruleid: menu-set-config-session-scope, menu-set-config-outside-tenancy
    conn.execute("select set_config('app.family_id', cast(:family as text), false)")
    # ruleid: menu-set-config-session-scope, menu-set-config-outside-tenancy
    conn.execute("select set_config('app.family_id', :f, 'off')")
    # ruleid: menu-set-config-session-scope, menu-set-config-outside-tenancy
    conn.execute("select pg_catalog.set_config('app.family_id', :f, (false))")
    # ok: menu-set-config-session-scope
    conn.execute("SET LOCAL search_path = app, pg_temp")
    # ok: menu-set-config-session-scope
    # ruleid: menu-set-config-outside-tenancy
    conn.execute("select set_config('app.family_id', cast(:f as text), true)")
