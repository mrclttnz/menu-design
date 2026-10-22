"""Helper `owner` (piano §5.5, 08 §4.1): operazioni privilegiate dei test su un database.

Usa `menu_owner` per preparare dati e leggere lo stato; non è mai usato dal codice dell'app.
`set_test_now` è l'UNICO modo di spostare l'orologio (D-T1): sostituisce `app.now_utc()` con
`CREATE OR REPLACE`, nessun gancio nel codice di produzione. `menu_owner` ha un limite di 3
connessioni nel cluster: ogni operazione apre e chiude la propria (`owner_connect`).
"""

from datetime import datetime
from typing import Any

import psycopg
from psycopg import sql

from . import pg


class Owner:
    def __init__(self, dbname: str) -> None:
        self.dbname = dbname

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        with pg.owner_connect(self.dbname) as conn:
            conn.execute(query.encode(), params)

    def script(self, text: str) -> None:
        """Più istruzioni nella stessa connessione (nessun parametro)."""
        with pg.owner_connect(self.dbname) as conn:
            conn.execute(text.encode())

    def rows(self, query: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        with pg.owner_connect(self.dbname) as conn:
            return conn.execute(query.encode(), params).fetchall()

    def scalar(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        found = self.rows(query, params)
        assert len(found) == 1, f"attesa una riga, trovate {len(found)}"
        return found[0][0]

    # --- orologio (D-T1) -------------------------------------------------------------------
    def now_utc_source(self) -> str | None:
        found = self.rows(
            "select prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'app' and p.proname = 'now_utc'"
        )
        return found[0][0] if found else None

    def set_test_now(self, instant: datetime) -> None:
        """Sostituisce `app.now_utc()` mantenendo firma e volatilità (STABLE)."""
        assert instant.tzinfo is not None, "istante naive: usare datetime con fuso"
        stmt = sql.SQL(
            "create or replace function app.now_utc() returns timestamptz "
            "language sql stable parallel safe as {}"
        ).format(sql.Literal(f"select '{instant.isoformat()}'::timestamptz"))
        with pg.owner_connect(self.dbname) as conn:
            conn.execute(stmt)

    def restore_now(self, original_source: str) -> None:
        stmt = sql.SQL(
            "create or replace function app.now_utc() returns timestamptz "
            "language sql stable parallel safe as {}"
        ).format(sql.Literal(original_source))
        with pg.owner_connect(self.dbname) as conn:
            conn.execute(stmt)

    # --- pulizia tra i test ----------------------------------------------------------------
    def truncate_data_tables(self) -> None:
        with pg.owner_connect(self.dbname) as conn:
            tables = conn.execute(
                "select quote_ident(schemaname) || '.' || quote_ident(tablename) "
                "from pg_tables where schemaname = 'app' and tablename <> 'alembic_version'"
            ).fetchall()
            if tables:
                conn.execute(("truncate " + ", ".join(t[0] for t in tables) + " cascade").encode())


def can_connect_as_owner(dbname: str) -> bool:
    try:
        with pg.connect_as("menu_owner", dbname):
            return True
    except psycopg.OperationalError:
        return False
