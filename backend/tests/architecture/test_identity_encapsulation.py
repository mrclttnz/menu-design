"""Le tabelle di identità e `system_tx` restano dentro i moduli previsti (THR-028, THR-044).

THR-028: «`system_tx` solo nel modulo `identity` (controllo statico)»; piano §2.3/§3
(«`system_tx` solo identity, ratelimit, jobs, audit, privacy»); 05-data §6.3 (`account`,
`session`, `auth_flow` si toccano solo dal modulo `identity`). Il controllo è una funzione pura
su una cartella, provata su alberi sintetici: un controllo che non sa fallire non vale nulla.
"""

import ast
import re
from pathlib import Path

import pytest

from support.paths import SRC

SYSTEM_TX_MODULES = frozenset({"tenancy", "identity", "ratelimit", "jobs", "audit", "privacy"})
_TABLE = re.compile(
    r"(?is)\bapp\.(?:account|session|auth_flow)\b"
    r"|\b(?:from|join|into|update)\s+(?:account|session|auth_flow)\b"
)


def _module_of(path: Path, root: Path) -> str:
    parts = path.relative_to(root).parts
    return parts[0].removesuffix(".py")


def system_tx_violations(root: Path) -> list[str]:
    out = []
    for path in sorted(root.rglob("*.py")):
        module = _module_of(path, root)
        if module in SYSTEM_TX_MODULES:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.ImportFrom | ast.Import)
                else []
            )
            used = isinstance(node, ast.Name) and node.id == "system_tx"
            attr = isinstance(node, ast.Attribute) and node.attr == "system_tx"
            if "system_tx" in names or used or attr:
                allowed = sorted(SYSTEM_TX_MODULES)
                line = getattr(node, "lineno", 0)
                out.append(f"{path.relative_to(root)}:{line}: system_tx fuori da {allowed}")
    return out


def identity_table_violations(root: Path) -> list[str]:
    out = []
    for path in sorted(root.rglob("*.py")):
        if _module_of(path, root) in {"identity", "tenancy"}:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _TABLE.search(node.value)
            ):
                out.append(f"{path.relative_to(root)}:{node.lineno}: tabella di identità")
    return out


def test_system_tx_is_used_only_by_the_allowed_modules() -> None:
    assert system_tx_violations(SRC) == []


def test_identity_tables_are_queried_only_from_the_identity_module() -> None:
    assert identity_table_violations(SRC) == []


# --- i controlli sanno fallire ----------------------------------------------------------------


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, code in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "code",
    [
        "from menu.tenancy import system_tx\n",
        "from menu import tenancy\nwith tenancy.system_tx() as tx: pass\n",
        "import menu.tenancy as t\nt.system_tx()\n",
    ],
)
def test_system_tx_check_flags_a_forbidden_module(tmp_path: Path, code: str) -> None:
    root = _tree(tmp_path, {"family/service.py": code, "identity/service.py": code})
    problems = system_tx_violations(root)
    assert problems, "il controllo deve segnalare l'uso fuori elenco"
    assert all(p.startswith("family/") for p in problems), problems


def test_identity_table_check_flags_sql_outside_identity(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "family/repo.py": 'Q = "select email from app.account where id = :i"\n',
            "catalog/repo.py": 'Q = "select * from session"\n',
            "planning/repo.py": 'Q = "select * from app.meal"\n',
            "identity/repo.py": 'Q = "select * from app.account"\n',
        },
    )
    problems = identity_table_violations(root)
    assert sorted(p.split(":")[0] for p in problems) == ["catalog/repo.py", "family/repo.py"]
