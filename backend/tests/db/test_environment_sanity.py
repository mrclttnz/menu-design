"""Segnale di salute (08 §17.1 punto 4): il cluster di test funziona, a prescindere da SL-00b.

Questi test devono passare PRIMA dell'implementazione: dimostrano che i fallimenti degli altri
test sono dovuti a funzionalità mancanti e non all'ambiente.
"""

import subprocess
from pathlib import Path

import psycopg
import pytest

from support import pg


def test_environment_sanity_cluster_is_postgres_17_over_verified_tls() -> None:
    pg.check_cluster_or_exit()
    with pg.admin_connect() as conn:
        version = conn.execute("show server_version_num").fetchone()
        ssl = conn.execute("select ssl from pg_stat_ssl where pid = pg_backend_pid()").fetchone()
    assert version is not None
    assert int(version[0]) // 10_000 == 17
    assert ssl == (True,), "la connessione di test deve usare TLS con verify-full"


def test_environment_sanity_extensions_are_available() -> None:
    pg.check_cluster_or_exit()
    with pg.admin_connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                "select name from pg_available_extensions where name in ('unaccent', 'pg_trgm')"
            ).fetchall()
        }
    assert names == {"unaccent", "pg_trgm"}


def test_environment_sanity_scratch_database_can_be_created_and_dropped() -> None:
    pg.check_cluster_or_exit()
    with pg.scratch_db() as name, pg.admin_connect(name) as conn:
        assert conn.execute("select 1").fetchone() == (1,)
    with pg.admin_connect() as conn:
        left = conn.execute("select 1 from pg_database where datname = %s", (name,)).fetchone()
    assert left is None


def test_environment_sanity_tls_with_foreign_ca_is_refused(tmp_path: Path) -> None:
    """Prova che `verify-full` è davvero attivo nel client di test (una CA estranea fallisce)."""
    pg.check_cluster_or_exit()
    foreign = tmp_path / "foreign-ca.crt"
    key = tmp_path / "foreign-ca.key"
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
            "-out", str(foreign), "-days", "1", "-subj", "/CN=foreign-test-ca",
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    cl = pg.cluster()
    conninfo = (
        f"host={cl.host} port={cl.port} dbname=postgres user={cl.admin_user} "
        f"password={cl.admin_password} sslmode=verify-full sslrootcert={foreign}"
    )
    with pytest.raises(psycopg.OperationalError, match=r"(?i)certificate"):
        psycopg.connect(conninfo)
