# Fixture per `semgrep --test .semgrep` (non importato né eseguito).
from sqlalchemy import Session, create_engine, sessionmaker, text


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
    # ruleid: menu-set-config-session-scope
    conn.execute("select set_config('app.tenant_id', 'x', false)")
    # ruleid: menu-set-config-session-scope
    conn.execute("SET app.tenant_id = 'x'")
    # ok: menu-set-config-session-scope
    conn.execute("select set_config('app.tenant_id', 'x', true)")
    # ok: menu-set-config-session-scope
    conn.execute("SET LOCAL app.tenant_id = 'x'")
