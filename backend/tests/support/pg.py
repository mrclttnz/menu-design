"""Cluster PostgreSQL 17 di test: connessioni, database template, un database per worker.

Contratto con l'implementazione di SL-00b (il tester NON scrive questi file):
- `db/bootstrap.sql` (radice del repository): eseguito qui con psycopg come superutente del
  cluster di test, senza comandi `\\`, senza password; idempotente (08 §10 punto 7).
- `backend/alembic.ini` con `script_location = migrations` (`backend/migrations/versions/`),
  tabella `alembic_version` nello schema `app`; `env.py` legge `DATABASE_URL_OWNER`.
- ruoli `menu_owner`, `menu_app`, `menu_console`, `menu_backup` creati da `bootstrap.sql`.

Configurazione del cluster (variabili d'ambiente; `make test-db` le ricava da `compose.yaml`):
  MENU_TEST_PG_HOST (localhost), MENU_TEST_PG_PORT (o MENU_PG_HOST_PORT, 5432),
  MENU_TEST_PG_ADMIN_USER (postgres), MENU_TEST_PG_ADMIN_PASSWORD, MENU_TEST_PG_CA
  (certificato della CA del server: la connessione usa `sslmode=verify-full`, come l'app).

Se il cluster non è raggiungibile la suite si ferma con un messaggio chiaro (08 §4.1): mai
0 test raccolti e verde. I ruoli sono del cluster (condivisi dai database dei worker).
"""

import hashlib
import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql

from .paths import BACKEND, REPO

LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
ROLES = ("menu_owner", "menu_app", "menu_console", "menu_backup")
# Password sintetica dei ruoli nel cluster di test (mai usata altrove; i ruoli reali non hanno
# password nel file `bootstrap.sql`, ADR-0015).
TEST_ROLE_PASSWORD = "synthetic-test-cluster-only"  # noqa: S105
LOCK_TEMPLATE = 727_001
LOCK_CREATE_DB = 727_002
LOCK_BOOTSTRAP = 727_006
LOCK_OWNER_GATE = 727_003  # al più una connessione `menu_owner` alla volta (CONNECTION LIMIT 3)
BOOTSTRAP = REPO / "db" / "bootstrap.sql"
MIGRATIONS = BACKEND / "migrations"
ALEMBIC_INI = BACKEND / "alembic.ini"


@dataclass(frozen=True)
class Cluster:
    host: str
    port: int
    admin_user: str
    admin_password: str
    ca: Path

    def url(self, user: str, password: str, dbname: str, *, driver: str = "postgresql") -> str:
        return (
            f"{driver}://{quote(user)}:{quote(password)}@{self.host}:{self.port}/{dbname}"
            f"?sslmode=verify-full&sslrootcert={quote(str(self.ca))}"
        )

    def conninfo(self, user: str, password: str, dbname: str) -> str:
        return self.url(user, password, dbname)

    def role_url(self, role: str, dbname: str, *, sqlalchemy: bool = False) -> str:
        driver = "postgresql+psycopg" if sqlalchemy else "postgresql"
        return self.url(role, TEST_ROLE_PASSWORD, dbname, driver=driver)


def cluster() -> Cluster:
    host = os.environ.get("MENU_TEST_PG_HOST", "localhost")
    # SEC-SL00b-004: i ruoli di test hanno una password pubblica; mai su un host non locale
    # senza consenso esplicito (`MENU_TEST_PG_ALLOW_REMOTE=1`; la CI usa localhost).
    if host not in LOOPBACK_HOSTS and os.environ.get("MENU_TEST_PG_ALLOW_REMOTE") != "1":
        raise RuntimeError(
            "MENU_TEST_PG_HOST non è locale: la password dei ruoli di test è pubblica. "
            "Impostare MENU_TEST_PG_ALLOW_REMOTE=1 solo per un cluster di test dedicato."
        )
    port = int(os.environ.get("MENU_TEST_PG_PORT") or os.environ.get("MENU_PG_HOST_PORT") or 5432)
    ca = Path(os.environ.get("MENU_TEST_PG_CA", str(REPO / "db" / "dev-certs" / "ca.crt")))
    return Cluster(
        host=host,
        port=port,
        admin_user=os.environ.get("MENU_TEST_PG_ADMIN_USER", "postgres"),
        admin_password=os.environ.get("MENU_TEST_PG_ADMIN_PASSWORD", "postgres"),
        ca=ca,
    )


def worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "master")


def admin_connect(dbname: str = "postgres", *, autocommit: bool = True) -> psycopg.Connection:
    cl = cluster()
    return psycopg.connect(
        cl.conninfo(cl.admin_user, cl.admin_password, dbname), autocommit=autocommit
    )


def connect_as(role: str, dbname: str, *, autocommit: bool = True) -> psycopg.Connection:
    """Connessione TLS verify-full con il ruolo indicato (password sintetica di test)."""
    return psycopg.connect(cluster().role_url(role, dbname), autocommit=autocommit)


def check_cluster_or_exit() -> None:
    """Prerequisito di esecuzione (08 §4.1): messaggio chiaro, nessun verde a vuoto."""
    try:
        with admin_connect() as conn:
            version = conn.execute("show server_version_num").fetchone()
    except psycopg.Error as exc:
        import pytest

        pytest.exit(
            "PostgreSQL di test non raggiungibile (verify-full): avviare il cluster "
            "(compose.yaml) e impostare MENU_TEST_PG_* / MENU_TEST_PG_CA. "
            f"Dettaglio: {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}",
            returncode=3,
        )
    assert version is not None
    if int(version[0]) // 10_000 != 17:
        import pytest

        pytest.exit(f"serve PostgreSQL 17, trovato {version[0]}", returncode=3)


# --- template -----------------------------------------------------------------------------


def _fingerprint() -> str:
    h = hashlib.sha256()
    paths: list[Path] = [BOOTSTRAP, ALEMBIC_INI]
    if MIGRATIONS.is_dir():
        paths += sorted(p for p in MIGRATIONS.rglob("*.py") if "__pycache__" not in p.parts)
    for p in paths:
        h.update(str(p.relative_to(REPO)).encode())
        h.update(p.read_bytes() if p.is_file() else b"<missing>")
    return h.hexdigest()[:10]


def run_bootstrap(dbname: str) -> None:
    """Esegue `db/bootstrap.sql` nel database (come `postgres` nell'editor di Supabase)."""
    script = BOOTSTRAP.read_text(encoding="utf-8")
    # I ruoli sono del cluster: due ALTER ROLE concorrenti dànno "tuple concurrently updated".
    with admin_connect() as gate:
        gate.execute("select pg_advisory_lock(%s)", (LOCK_BOOTSTRAP,))
        with admin_connect(dbname) as conn:
            conn.execute(script.encode())


def set_role_passwords() -> None:
    """Password sintetica ai ruoli già esistenti (fuori dal file di bootstrap, ADR-0015)."""
    with admin_connect() as conn:
        for role in ROLES:
            exists = conn.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone()
            if exists:
                conn.execute(
                    sql.SQL("alter role {} password {}").format(
                        sql.Identifier(role), sql.Literal(TEST_ROLE_PASSWORD)
                    )
                )


def alembic(
    dbname: str, *args: str, role: str = "menu_owner", env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Esegue `alembic -c backend/alembic.ini <args>` come sottoprocesso (env.py reale)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "DATABASE_URL_OWNER": cluster().role_url(role, dbname, sqlalchemy=True),
        "APP_ENV": "test",
    }
    env.update(env_extra or {})
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def create_db(admin: psycopg.Connection, name: str, template: str | None = None) -> None:
    admin.execute("select pg_advisory_lock(%s)", (LOCK_CREATE_DB,))
    try:
        stmt = sql.SQL("create database {}").format(sql.Identifier(name))
        if template:
            stmt = sql.SQL("create database {} template {}").format(
                sql.Identifier(name), sql.Identifier(template)
            )
        admin.execute(stmt)
    finally:
        admin.execute("select pg_advisory_unlock(%s)", (LOCK_CREATE_DB,))


def drop_db(name: str) -> None:
    with admin_connect() as admin, suppress(psycopg.Error):
        admin.execute(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where datname = %s and pid <> pg_backend_pid()",
            (name,),
        )
        admin.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(name)))


def ensure_templates() -> tuple[str, str]:
    """(template con solo bootstrap, template a `alembic upgrade head`), costruiti una volta.

    Se `bootstrap.sql` o le migrazioni non esistono ancora (prima di SL-00b) i template sono
    database vuoti: i test falliscono per asserzione ("ruoli mancanti", "funzione assente"),
    non per un errore di configurazione.
    """
    key = _fingerprint()
    boot, head = f"menu_tpl_boot_{key}", f"menu_tpl_head_{key}"
    with admin_connect() as admin:
        admin.execute("select pg_advisory_lock(%s)", (LOCK_TEMPLATE,))
        try:
            ready = {
                r[0]
                for r in admin.execute(
                    "select datname from pg_database d where shobj_description(d.oid, "
                    "'pg_database') = 'ready'"
                ).fetchall()
            }
            if boot in ready and head in ready:
                return boot, head
            for stale in admin.execute(
                "select datname from pg_database where datname like 'menu_tpl_%'"
            ).fetchall():
                drop_db(stale[0])
            create_db(admin, boot)
            if BOOTSTRAP.is_file():
                run_bootstrap(boot)
                set_role_passwords()
            create_db(admin, head, template=boot)
            if BOOTSTRAP.is_file() and ALEMBIC_INI.is_file():
                proc = alembic(head, "upgrade", "head")
                if proc.returncode != 0:
                    # Nessun database "pronto": ogni test fallisce con questo messaggio.
                    raise RuntimeError(f"alembic upgrade head fallito:\n{proc.stderr[-2000:]}")
            for name in (boot, head):
                admin.execute(
                    sql.SQL("comment on database {} is 'ready'").format(sql.Identifier(name))
                )
            return boot, head
        finally:
            admin.execute("select pg_advisory_unlock(%s)", (LOCK_TEMPLATE,))


LOCK_SCRATCH = 727_005


@contextmanager
def exclusive_scratch_lock() -> Iterator[None]:
    """Blocca tutti i database temporanei degli altri worker (test distruttivi sui ruoli).

    Ogni `scratch_db` tiene il lock condiviso finché esiste; chi lo prende esclusivo aspetta che
    non ce ne siano e impedisce che ne nascano finché non ha finito.
    """
    with admin_connect() as gate:
        gate.execute("select pg_advisory_lock(%s)", (LOCK_SCRATCH,))
        try:
            yield
        finally:
            gate.execute("select pg_advisory_unlock(%s)", (LOCK_SCRATCH,))


@contextmanager
def scratch_db(
    template: str | None = None, *, prefix: str = "menu_s", locked: bool = False
) -> Iterator[str]:
    """Database temporaneo (clone di un template, oppure vuoto); eliminato all'uscita.

    `locked=True` solo dentro `exclusive_scratch_lock()` (altrimenti auto-blocco).
    """
    name = f"{prefix}_{worker_id()}_{secrets.token_hex(4)}"
    with admin_connect() as gate:
        if not locked:
            gate.execute("select pg_advisory_lock_shared(%s)", (LOCK_SCRATCH,))
        with admin_connect() as admin:
            create_db(admin, name, template=template)
        try:
            yield name
        finally:
            drop_db(name)


@contextmanager
def owner_connect(dbname: str) -> Iterator[psycopg.Connection]:
    """Connessione `menu_owner` breve; una sola alla volta nel cluster (limite 3, §3.1)."""
    with admin_connect() as gate:
        gate.execute("select pg_advisory_lock(%s)", (LOCK_OWNER_GATE,))
        with connect_as("menu_owner", dbname) as conn:
            yield conn
