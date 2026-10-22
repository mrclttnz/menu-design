"""`db/bootstrap.sql` (plan SL-00b, 05-data §3.1/§12, 08 §10.7; SR-075, THR-040/042).

Compatibile con l'editor SQL di Supabase e con un PostgreSQL locale: nessun comando `\\`,
nessuna password né verificatore nel file, idempotente, revoche verso `anon`/`authenticated`
solo se quei ruoli esistono.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager

from support import pg
from support.inventory import schema_create_grantees, schema_snapshot
from support.paths import REPO

BOOTSTRAP = REPO / "db" / "bootstrap.sql"


def _script() -> str:
    assert BOOTSTRAP.is_file(), "db/bootstrap.sql non esiste (SL-00b)"
    return BOOTSTRAP.read_text(encoding="utf-8")


def test_bootstrap_file_exists() -> None:
    assert BOOTSTRAP.is_file(), "db/bootstrap.sql non esiste (SL-00b)"


def test_bootstrap_has_no_psql_meta_commands() -> None:
    """Va incollato nell'editor SQL di Supabase: niente `\\connect`, `\\set`, ... (SL-00b)."""
    offenders = [ln for ln in _script().splitlines() if re.match(r"\s*\\[A-Za-z!?]", ln)]
    assert offenders == []


def test_bootstrap_contains_no_password_or_verifier() -> None:
    """THR-042 / ADR-0015: né password né verificatore SCRAM nel file."""
    script = _script()
    assert not re.search(r"(?i)\bpassword\b", re.sub(r"--[^\n]*", "", script)), (
        "il file non deve impostare password (ALTER ROLE ... PASSWORD si esegue fuori dal file)"
    )
    assert "SCRAM-SHA-256$" not in script
    assert not re.search(r"(?i)md5[0-9a-f]{32}", script)


def test_bootstrap_creates_roles_without_bypassrls_or_superuser_attributes() -> None:
    script = re.sub(r"--[^\n]*", "", _script())
    assert not re.search(r"(?i)(?<!no)bypassrls", script), "BYPASSRLS non deve comparire"
    assert not re.search(r"(?i)(?<!no)superuser|(?<!no)createrole|(?<!no)createdb", script)
    for role in pg.ROLES:
        assert role in script


@contextmanager
def _fresh_db() -> Iterator[str]:
    pg.check_cluster_or_exit()
    with pg.scratch_db() as name:
        yield name


def test_bootstrap_runs_on_an_empty_database_and_creates_the_prerequisites() -> None:
    with _fresh_db() as name:
        pg.run_bootstrap(name)
        with pg.admin_connect(name) as conn:
            exts: dict[str, str] = dict(
                conn.execute(
                    "select e.extname, n.nspname from pg_extension e "
                    "join pg_namespace n on n.oid = e.extnamespace "
                    "where e.extname in ('unaccent', 'pg_trgm')"
                ).fetchall()
            )
            owner = conn.execute(
                "select pg_get_userbyid(nspowner) from pg_namespace where nspname = 'app'"
            ).fetchone()
    assert exts == {"unaccent": "extensions", "pg_trgm": "extensions"}
    assert owner == ("menu_owner",)


def test_bootstrap_is_idempotent_08_10_7() -> None:
    """Due esecuzioni di fila: nessun errore e stesso stato (08 §10 punto 7)."""
    with _fresh_db() as name:
        pg.run_bootstrap(name)
        with pg.admin_connect(name) as conn:
            first = schema_snapshot(conn)
        pg.run_bootstrap(name)
        with pg.admin_connect(name) as conn:
            second = schema_snapshot(conn)
    assert first == second
    assert first, "lo snapshot non può essere vuoto dopo il bootstrap"


SUPABASE_ROLES = ("anon", "authenticated")


@contextmanager
def _supabase_roles_serialized() -> Iterator[None]:
    """`anon`/`authenticated` sono del cluster: i test che li creano o li presuppongono assenti
    prendono il lock ESCLUSIVO sui database temporanei (nessun altro worker ne ha uno aperto,
    quindi nessuna gara) e ripuliscono residui di esecuzioni precedenti prima e dopo."""
    pg.check_cluster_or_exit()
    with pg.exclusive_scratch_lock():
        _drop_supabase_roles()
        try:
            yield
        finally:
            _drop_supabase_roles()


def _drop_supabase_roles() -> None:
    with pg.admin_connect() as conn:
        present = [
            r[0]
            for r in conn.execute(
                "select rolname from pg_roles where rolname = any(%s)", (list(SUPABASE_ROLES),)
            ).fetchall()
        ]
        if not present:
            return
        # Con il lock esclusivo i soli database temporanei esistenti sono residui: si ripuliscono.
        leftovers = [
            r[0]
            for r in conn.execute(
                "select datname from pg_database where datname like 'menu\\_s\\_%'"
            ).fetchall()
        ]
        databases = [*leftovers, "postgres"]
    for database in databases:
        with pg.admin_connect(database) as db_conn:
            for role in present:
                db_conn.execute(f"drop owned by {role}".encode())
    with pg.admin_connect() as conn:
        for role in present:
            conn.execute(f"drop role {role}".encode())


def test_bootstrap_revokes_supabase_default_roles_when_they_exist() -> None:
    """`anon`/`authenticated` (Supabase) non hanno accesso né CREATE su `app`/`public`."""
    with _supabase_roles_serialized():
        with pg.admin_connect() as cluster_conn:
            for role in SUPABASE_ROLES:
                cluster_conn.execute(f"create role {role} nologin".encode())
        with pg.scratch_db(locked=True) as name:
            with pg.admin_connect(name) as conn:
                conn.execute(b"grant create, usage on schema public to anon, authenticated")
            pg.run_bootstrap(name)
            with pg.admin_connect(name) as conn:
                grants = {
                    (role, schema, priv): conn.execute(
                        "select has_schema_privilege(%s, %s, %s)", (role, schema, priv)
                    ).fetchone()
                    for role in SUPABASE_ROLES
                    for schema in ("app", "public")
                    for priv in ("CREATE", "USAGE")
                    if not (schema == "public" and priv == "USAGE")
                }
                created_in_public = schema_create_grantees(conn, "public")
    assert {k: v for k, v in grants.items() if v != (False,)} == {}
    assert not {"anon", "authenticated", "PUBLIC"} & created_in_public


def test_bootstrap_runs_when_supabase_roles_are_absent() -> None:
    """Percorso opposto: PostgreSQL locale senza `anon`/`authenticated`."""
    with _supabase_roles_serialized():
        with pg.admin_connect() as conn:
            present = conn.execute(
                "select count(*) from pg_roles where rolname = any(%s)", (list(SUPABASE_ROLES),)
            ).fetchone()
        assert present == (0,)
        with pg.scratch_db(locked=True) as name:
            pg.run_bootstrap(name)
