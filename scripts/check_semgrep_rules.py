"""Verifica che le regole custom di .semgrep/ scattino sui percorsi attesi.

`semgrep --test` ignora i filtri `paths` delle regole: un `include` sbagliato non
verrebbe rilevato. Qui si esegue una vera scansione su un albero temporaneo con la
stessa struttura del repository e si confrontano le regole scattate per file.
Uso: python3 scripts/check_semgrep_rules.py  (da root repo; richiede semgrep nel PATH)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SESSION = "from sqlalchemy import create_engine\ncreate_engine('postgresql://x')\n"
SET_CFG = "q = \"select set_config('app.tenant_id', 'x', false)\"\n"
SET_CFG_TRUE = "q = \"select set_config('app.family_id', cast(:f as text), true)\"\n"
SET_CFG_NESTED = "q = \"select set_config('app.family_id', cast(:f as text), false)\"\n"
NOW = 'op.execute("insert into t values (now())")\n'
NOW_ALLOWED = 'NOW_UTC_BODY = "select now()"  # allow-bare-now: corpo di app.now_utc()\n'
NOW_OTHER = 'OTHER = "select now()"\n'

ASYNC = "from sqlalchemy.ext.asyncio import create_async_engine\ncreate_async_engine('postgresql+psycopg://x')\n"
TEXT_VAR = "q = f'select {x}'\ntext(q)\n"

# percorso relativo -> (contenuto, regole attese)
CASES: dict[str, tuple[str, set[str]]] = {
    "backend/src/menu/orders/repo.py": (SESSION, {"menu-sqlalchemy-session-outside-tenancy"}),
    "backend/src/menu/tenancy/db.py": (SESSION, set()),
    "backend/src/menu/console_client/db.py": (SESSION, set()),
    "backend/tests/unit/test_x.py": (SESSION, set()),
    "backend/src/menu/orders/async_repo.py": (ASYNC, {"menu-sqlalchemy-session-outside-tenancy"}),
    "backend/src/menu/tenancy/async_db.py": (ASYNC, set()),
    "backend/src/menu/orders/text_var.py": (TEXT_VAR, {"menu-sqlalchemy-text-formatted"}),
    "backend/src/menu/orders/cfg.py": (
        SET_CFG,
        {"menu-set-config-session-scope", "menu-set-config-outside-tenancy"},
    ),
    "backend/src/menu/orders/cfg_true.py": (SET_CFG_TRUE, {"menu-set-config-outside-tenancy"}),
    "backend/src/menu/tenancy/cfg_true.py": (SET_CFG_TRUE, set()),
    "backend/src/menu/tenancy/cfg_nested.py": (SET_CFG_NESTED, {"menu-set-config-session-scope"}),
    "backend/tests/unit/test_cfg.py": (SET_CFG, set()),
    "backend/migrations/versions/0001_x.py": (NOW, {"menu-bare-now-in-migrations"}),
    "backend/src/menu/orders/now.py": (NOW, set()),
    "backend/migrations/versions/0001_allowed.py": (NOW_ALLOWED, set()),
    "backend/migrations/versions/0002_y.py": (NOW_OTHER, {"menu-bare-now-in-migrations"}),
}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, (content, _) in CASES.items():
            f = root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content, encoding="utf-8")
        proc = subprocess.run(
            ["semgrep", "scan", "--metrics=off", "--json", "--quiet",
             "--config", str(REPO / ".semgrep" / "sql.yaml"),
             "--config", str(REPO / ".semgrep" / "migrations-now.yaml"), str(root)],
            capture_output=True, text=True, check=False, cwd=root,
        )  # fmt: skip
        if proc.returncode not in (0, 1):
            print(proc.stderr, file=sys.stderr)
            return 2
        found: dict[str, set[str]] = {rel: set() for rel in CASES}
        for r in json.loads(proc.stdout)["results"]:
            rel = Path(r["path"]).resolve().relative_to(root.resolve()).as_posix()
            found.setdefault(rel, set()).add(r["check_id"].rsplit(".", 1)[-1])
    bad = 0
    for rel, (_, expected) in CASES.items():
        if found[rel] != expected:
            bad += 1
            print(f"ERRORE {rel}: attese {sorted(expected)}, trovate {sorted(found[rel])}", file=sys.stderr)
    if bad:
        return 1
    print(f"regole custom: {len(CASES)} casi di percorso OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
