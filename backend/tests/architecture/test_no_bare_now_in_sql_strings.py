"""Estensione del controllo "nessun now() nudo" alle stringhe SQL del codice Python
(05-data §11.1 proposta al tester; piano §5.5; THR-048). Il catalogo non vede lo SQL scritto
in `src/` e nelle migrazioni: lo si cerca con `ast`.
"""

import ast
from pathlib import Path

from support.inventory import forbidden_time_expressions
from support.paths import BACKEND, SRC

ALLOWED_LINE = 'NOW_UTC_BODY = "select now()"  # allow-bare-now: corpo di app.now_utc()'
_SQL_HINT = ("select ", "insert ", "update ", "delete ", "create ", "alter ", " from ", "default ")


def sql_clock_violations(root: Path) -> list[str]:
    out = []
    for path in sorted(root.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in ast.walk(ast.parse("\n".join(lines))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == "select now()" and lines[node.lineno - 1].strip() == ALLOWED_LINE:
                    continue  # unica eccezione: corpo di app.now_utc() in 0001
                value = node.value.lower()
                if any(h in value for h in _SQL_HINT) and (
                    bad := forbidden_time_expressions(node.value)
                ):
                    out.append(f"{path}:{node.lineno}: {bad}")
    return out


def test_no_bare_time_expressions_in_application_sql() -> None:
    assert sql_clock_violations(SRC) == []


def test_no_bare_time_expressions_in_migration_sources() -> None:
    migrations = BACKEND / "migrations"
    assert migrations.is_dir(), "backend/migrations assente (SL-00b)"
    assert sql_clock_violations(migrations) == []


def test_checker_detects_synthetic_offenders(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text(
        "q = 'select now()'\nr = \"insert into t values (CURRENT_TIMESTAMP)\"\n"
        "ok = 'select app.now_utc()'\nnot_sql = 'now() is a word'\n",
        encoding="utf-8",
    )
    found = sql_clock_violations(tmp_path)
    assert len(found) == 2
