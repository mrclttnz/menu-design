"""Migrazioni (05-data §12, 08 §10; THR-048, SR-075): testa unica, a scala, env.py, prerequisiti."""

import re
from pathlib import Path

import psycopg
import pytest

from support import pg
from support.inventory import (
    EXPECTED_SECDEF_NOW,
    SQL_FUNCTIONS_NOW,
    bare_time_problems,
    rls_problems,
    schema_snapshot,
    secdef_problems,
)
from support.paths import BACKEND

VERSIONS = BACKEND / "migrations" / "versions"


def _revisions() -> list[Path]:
    return sorted(p for p in VERSIONS.glob("*.py") if p.name != "__init__.py")


def test_alembic_scaffolding_exists() -> None:
    assert (BACKEND / "alembic.ini").is_file()
    assert (BACKEND / "migrations" / "env.py").is_file()
    assert _revisions(), "nessuna revisione in backend/migrations/versions"


def test_single_head_with_four_digit_revision_ids() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1, script.get_heads()
    ids = [r.revision for r in script.walk_revisions()]
    assert ids
    assert all(re.fullmatch(r"\d{4}", i) for i in ids), ids
    assert "0001" in ids


def test_env_py_sets_timeouts_and_checks_the_owner_role() -> None:
    text = (BACKEND / "migrations" / "env.py").read_text(encoding="utf-8")
    assert re.search(r"lock_timeout\W+5s", text)
    assert re.search(r"statement_timeout\W+60s", text)
    assert "menu_owner" in text


def test_downgrade_is_defined_for_every_revision() -> None:
    assert _revisions(), "nessuna revisione"
    for path in _revisions():
        assert re.search(r"^def downgrade\(", path.read_text(encoding="utf-8"), re.M), path.name


ALLOWED_NOW_LINE = 'NOW_UTC_BODY = "select now()"  # allow-bare-now: corpo di app.now_utc()'


def test_migrations_never_use_bare_time_functions_except_the_now_utc_body() -> None:
    """Rete oltre a semgrep (plan §5.5): elenco chiuso con UNA sola eccezione, il corpo di
    app.now_utc() in 0001, riconosciuta dalla riga esatta (marcatore `allow-bare-now`)."""
    from support.inventory import forbidden_time_expressions

    assert _revisions(), "nessuna revisione"
    allowed: list[tuple[str, int]] = []
    for path in _revisions():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip() == ALLOWED_NOW_LINE:
                allowed.append((path.name, number))
                continue
            assert forbidden_time_expressions(line) == [], f"{path.name}:{number}: {line.strip()}"
    assert len(allowed) == 1, f"l'eccezione deve comparire una sola volta: {allowed}"
    assert allowed[0][0].startswith("0001_")
    assert sum(p.read_text(encoding="utf-8").count("allow-bare-now:") for p in _revisions()) == 1


def _all_inventories(conn: psycopg.Connection, *, with_functions: bool) -> None:
    assert bare_time_problems(conn) == []
    assert rls_problems(conn) == []
    assert secdef_problems(conn, EXPECTED_SECDEF_NOW) == []
    names = {
        r[0]
        for r in conn.execute(
            "select proname from pg_proc where pronamespace = 'app'::regnamespace"
        ).fetchall()
    }
    if with_functions:
        assert names >= SQL_FUNCTIONS_NOW
    else:
        assert names == set(), f"il downgrade ha lasciato funzioni: {names}"


@pytest.mark.slow
def test_ladder_upgrade_downgrade_upgrade_and_base_head_with_inventories() -> None:
    """08 §10.2: upgrade → downgrade -1 → upgrade, poi base ↔ head; inventari a ogni passo."""
    pg.check_cluster_or_exit()
    boot, _ = pg.ensure_templates()
    with pg.scratch_db(boot) as name:

        def step(*args: str) -> None:
            proc = pg.alembic(name, *args)
            assert proc.returncode == 0, f"alembic {' '.join(args)}: {proc.stderr[-1500:]}"

        step("upgrade", "head")
        with pg.admin_connect(name) as conn:
            _all_inventories(conn, with_functions=True)
            at_head = schema_snapshot(conn)
        step("downgrade", "-1")
        with pg.admin_connect(name) as conn:
            _all_inventories(conn, with_functions=False)
        step("upgrade", "head")
        step("downgrade", "base")
        with pg.admin_connect(name) as conn:
            _all_inventories(conn, with_functions=False)
        step("upgrade", "head")
        with pg.admin_connect(name) as conn:
            _all_inventories(conn, with_functions=True)
            assert schema_snapshot(conn) == at_head, "schema diverso dopo il ciclo (08 §10.3)"
        assert at_head


def test_env_py_refuses_to_run_as_a_role_other_than_menu_owner() -> None:
    pg.check_cluster_or_exit()
    _, head = pg.ensure_templates()
    with pg.scratch_db(head) as name:
        proc = pg.alembic(name, "downgrade", "base", role="menu_app")
        assert proc.returncode != 0
        assert "menu_owner" in proc.stderr
        with pg.admin_connect(name) as conn:
            n = conn.execute(
                "select count(*) from pg_proc where pronamespace = 'app'::regnamespace"
            ).fetchone()
        assert n is not None
        assert n[0] >= 4, "nessuna modifica deve essere stata applicata"


@pytest.mark.parametrize("sslmode", ["require", "prefer", "disable", "verify-ca"])
def test_env_py_refuses_an_owner_url_without_verify_full(sslmode: str) -> None:
    """THR-043: anche il job di migrazione rifiuta URL senza `sslmode=verify-full`."""
    pg.check_cluster_or_exit()
    _, head = pg.ensure_templates()
    with pg.scratch_db(head) as name:
        url = pg.cluster().role_url("menu_owner", name, sqlalchemy=True)
        weak = url.replace("sslmode=verify-full", f"sslmode={sslmode}")
        proc = pg.alembic(name, "current", env_extra={"DATABASE_URL_OWNER": weak})
        assert proc.returncode != 0
        assert "verify-full" in proc.stderr


@pytest.mark.parametrize(
    ("breakage", "needle"),
    [
        ("drop extension unaccent", "unaccent"),
        ("drop extension pg_trgm", "pg_trgm"),
    ],
)
def test_0001_fails_clearly_when_a_prerequisite_is_missing(breakage: str, needle: str) -> None:
    """05-data §3.1: la migrazione 0001 controlla i prerequisiti e dice quale manca."""
    pg.check_cluster_or_exit()
    boot, _ = pg.ensure_templates()
    with pg.scratch_db(boot) as name:
        with pg.admin_connect(name) as conn:
            conn.execute(breakage.encode())
        proc = pg.alembic(name, "upgrade", "head")
        assert proc.returncode != 0
        assert needle in proc.stderr
        assert "Traceback" in proc.stderr or "Error" in proc.stderr


def test_0001_fails_clearly_when_schema_app_is_not_owned_by_menu_owner() -> None:
    pg.check_cluster_or_exit()
    boot, _ = pg.ensure_templates()
    with pg.scratch_db(boot) as name:
        with pg.admin_connect(name) as conn:
            conn.execute(b"alter schema app owner to postgres")
        proc = pg.alembic(name, "upgrade", "head")
        assert proc.returncode != 0
        assert re.search(r"(?i)schema app|menu_owner", proc.stderr)
