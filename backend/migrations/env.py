"""Ambiente Alembic (docs/05-data.md §12; THR-043, THR-044, SR-075).

- URL da `DATABASE_URL_OWNER` (mai da `alembic.ini`), solo `sslmode=verify-full`.
- Solo `menu_owner` può migrare: controllo sul nome utente dell'URL e, dopo la connessione,
  su `current_user` e `session_user`, prima di qualunque modifica.
- `lock_timeout` 5s e `statement_timeout` 60s, locali alla transazione della migrazione.
- `alembic_version` nello schema `app`; tutte le revisioni in un'unica transazione.
- Nessun messaggio d'errore contiene l'URL (che contiene la password).
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.exc import ArgumentError

OWNER_ROLE = "menu_owner"
REQUIRED_SSLMODE = "verify-full"
APP_SCHEMA = "app"
URL_ENV = "DATABASE_URL_OWNER"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


class MigrationEnvError(RuntimeError):
    """Configurazione del job di migrazione non accettabile: nessuna modifica eseguita."""


def owner_url() -> URL:
    raw = os.environ.get(URL_ENV, "").strip()
    if not raw:
        raise MigrationEnvError(f"{URL_ENV} non impostata: serve l'URL di {OWNER_ROLE}.")
    try:
        url = make_url(raw)
    except ArgumentError:
        # Il messaggio originale ripete l'URL (con la password): non lo si propaga.
        raise MigrationEnvError(f"{URL_ENV} non è un URL di database valido.") from None
    if url.get_backend_name() != "postgresql":
        raise MigrationEnvError(f"{URL_ENV} deve puntare a PostgreSQL.")
    if url.username != OWNER_ROLE:
        raise MigrationEnvError(
            f"le migrazioni si eseguono solo come {OWNER_ROLE} (utente dell'URL: {url.username!r})."
        )
    sslmode = url.query.get("sslmode")
    if sslmode != REQUIRED_SSLMODE:
        raise MigrationEnvError(
            f"{URL_ENV} deve avere sslmode={REQUIRED_SSLMODE} (THR-043); trovato: {sslmode!r}."
        )
    return url.set(drivername="postgresql+psycopg")


def prepare_transaction(connection: Connection) -> None:
    """Timeout locali alla transazione e controlli di identità, prima di ogni modifica."""
    connection.exec_driver_sql(
        "select pg_catalog.set_config('lock_timeout', '5s', true), "
        "pg_catalog.set_config('statement_timeout', '60s', true)"
    )
    row = connection.exec_driver_sql("select current_user, session_user").one()
    if row[0] != OWNER_ROLE or row[1] != OWNER_ROLE:
        raise MigrationEnvError(
            f"le migrazioni si eseguono solo come {OWNER_ROLE} "
            f"(current_user={row[0]!r}, session_user={row[1]!r})."
        )
    found = connection.exec_driver_sql(
        "select pg_catalog.pg_get_userbyid(nspowner) from pg_catalog.pg_namespace "
        "where nspname = 'app'"
    ).one_or_none()
    if found is None:
        raise MigrationEnvError("schema app assente: eseguire prima db/bootstrap.sql.")
    if found[0] != OWNER_ROLE:
        raise MigrationEnvError(
            f"lo schema app appartiene a {found[0]!r}, deve appartenere a {OWNER_ROLE} "
            "(rieseguire db/bootstrap.sql)."
        )


def run_migrations_offline() -> None:
    raise MigrationEnvError(
        "modalità offline (--sql) non supportata: i controlli di ruolo e prerequisiti "
        "richiedono una connessione come menu_owner."
    )


def run_migrations_online() -> None:
    engine = create_engine(
        owner_url(),
        poolclass=pool.NullPool,
        hide_parameters=True,
        # Compatibile con il pooler in modalità transazione (ADR-0003, ADR-0014).
        connect_args={"prepare_threshold": None},
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                version_table_schema=APP_SCHEMA,
                transaction_per_migration=False,
            )
            with context.begin_transaction():
                prepare_transaction(connection)
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
