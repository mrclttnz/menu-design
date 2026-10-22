"""0001: orologio del database, funzioni di contesto, search_norm, controllo dei prerequisiti.

Revisione: 0001 (M0, SL-00b). docs/05-data.md §3.1, §3.2, §6.1, §11.1, §12.

- Controlla i prerequisiti di `db/bootstrap.sql` e fallisce dicendo quale manca.
- `app.now_utc()`: unica sorgente di "adesso" nel database (D-T1). STABLE, PARALLEL SAFE.
- `app.current_family_id()`, `app.current_account_id()`: contesto locale alla transazione.
- `app.search_norm(text)`: IMMUTABLE STRICT PARALLEL SAFE, `extensions.unaccent` con dizionario
  esplicito.

Tutte LANGUAGE sql, SECURITY INVOKER e senza clausola SET, così restano inlinabili (§11.1).
Non dipendono dal search_path del chiamante: ogni funzione, tipo e dizionario è qualificato con
lo schema (`pg_catalog`, `extensions`). Unica eccezione l'orologio della transazione nel corpo
di `now_utc`, che PostgreSQL risolve sempre in `pg_catalog` (cercato prima di ogni schema per le
funzioni; `pg_temp` non è mai cercato per le funzioni; nessun ruolo può creare in `public`).
EXECUTE revocato a PUBLIC e concesso al solo `menu_app` (§3.2). Nessuna SECURITY DEFINER.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_ROLE = "menu_owner"
LOGIN_ROLES = ("menu_owner", "menu_app", "menu_console", "menu_backup")
REQUIRED_EXTENSIONS = ("unaccent", "pg_trgm")

# Unica eccezione ammessa alla regola "nessun orologio nudo" (05-data §11.1: "elenco chiuso
# delle eccezioni: il corpo di app.now_utc()"). La riga è riconosciuta dal marcatore
# `allow-bare-now`: semgrep (`menu-bare-now-in-migrations`) e tests/db/test_migrations.py
# accettano ESATTAMENTE questa riga, una sola volta nell'intero albero delle migrazioni.
NOW_UTC_BODY = "select now()"  # allow-bare-now: corpo di app.now_utc()

FUNCTIONS: tuple[tuple[str, str], ...] = (
    (
        "app.now_utc()",
        "create function app.now_utc() returns timestamptz "
        "language sql stable parallel safe "
        f"as $$ {NOW_UTC_BODY} $$",
    ),
    (
        "app.current_family_id()",
        "create function app.current_family_id() returns uuid "
        "language sql stable parallel safe "
        "as $$ select nullif(pg_catalog.current_setting('app.family_id', true), '')"
        "::pg_catalog.uuid $$",
    ),
    (
        "app.current_account_id()",
        "create function app.current_account_id() returns uuid "
        "language sql stable parallel safe "
        "as $$ select nullif(pg_catalog.current_setting('app.account_id', true), '')"
        "::pg_catalog.uuid $$",
    ),
    (
        "app.search_norm(text)",
        "create function app.search_norm(value text) returns text "
        "language sql immutable strict parallel safe "
        "as $$ select pg_catalog.lower(extensions.unaccent("
        "'extensions.unaccent'::pg_catalog.regdictionary, value)) $$",
    ),
)


def _check_prerequisites() -> None:
    """05-data §3.1/§12: ruoli, schema e estensioni li crea `db/bootstrap.sql`, non Alembic."""
    bind = op.get_bind()
    problems: list[str] = []

    found = {
        r[0]: r[1:]
        for r in bind.exec_driver_sql(
            "select rolname, rolcanlogin, rolsuper or rolcreaterole or rolcreatedb "
            "or rolreplication or rolbypassrls from pg_catalog.pg_roles "
            "where rolname in ('menu_owner', 'menu_app', 'menu_console', 'menu_backup')"
        ).all()
    }
    for role in LOGIN_ROLES:
        if role not in found:
            problems.append(f"ruolo {role} assente")
            continue
        can_login, privileged = found[role]
        if not can_login:
            problems.append(f"ruolo {role} senza LOGIN")
        if privileged:
            problems.append(
                f"ruolo {role} con attributi privilegiati "
                "(SUPERUSER/CREATEROLE/CREATEDB/REPLICATION/BYPASSRLS)"
            )

    schema_owner = bind.exec_driver_sql(
        "select pg_catalog.pg_get_userbyid(nspowner) from pg_catalog.pg_namespace "
        "where nspname = 'app'"
    ).one_or_none()
    if schema_owner is None:
        problems.append("schema app assente")
    elif schema_owner[0] != OWNER_ROLE:
        problems.append(f"schema app di proprietà di {schema_owner[0]}, atteso {OWNER_ROLE}")

    extensions: dict[str, str] = {
        r[0]: r[1]
        for r in bind.exec_driver_sql(
            "select e.extname, n.nspname from pg_catalog.pg_extension e "
            "join pg_catalog.pg_namespace n on n.oid = e.extnamespace "
            "where e.extname in ('unaccent', 'pg_trgm')"
        ).all()
    }
    for ext in REQUIRED_EXTENSIONS:
        if ext not in extensions:
            problems.append(f"estensione {ext} assente")
        elif extensions[ext] != "extensions":
            problems.append(
                f"estensione {ext} nello schema {extensions[ext]}, attesa nello schema extensions"
            )

    if problems:
        raise RuntimeError(
            "Prerequisiti del database mancanti (eseguire db/bootstrap.sql, docs/05-data.md "
            "§3.1): " + "; ".join(problems)
        )


def upgrade() -> None:
    _check_prerequisites()
    for signature, ddl in FUNCTIONS:
        op.execute(ddl)
        # I privilegi predefiniti di bootstrap.sql tolgono già EXECUTE a PUBLIC: la revoca
        # esplicita rende la migrazione corretta anche da sola.
        op.execute(f"revoke all on function {signature} from public")
        op.execute(f"grant execute on function {signature} to menu_app")


def downgrade() -> None:
    for signature, _ in reversed(FUNCTIONS):
        op.execute(f"drop function {signature}")
