"""Controllo statico: ogni funzione che scrive un evento di modifica passa dal tetto giornaliero.

Backlog SL-05 (CR-SL05-004): una rotta tracciata che dimentica `tracked_write` risponderebbe 500
invece di 429 oltre il limite, e una che dimentica `consume_tracked_write` non conterebbe le
scritture (SR-070). La regola (ratelimit/tracked.py): chi chiama `record_change` usa, nella STESSA
funzione, `with tracked_write(...)` (fuori dalla transazione) e `consume_tracked_write(...)`.
Funzione pura su una cartella di sorgenti, provata su alberi sintetici in
`tests/architecture/test_tracked_writes_are_capped.py`.
"""

import ast
from pathlib import Path

EXEMPT_PACKAGES = frozenset({"history"})  # definisce `record_change`, non lo usa per scrivere


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _with_item_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.With | ast.AsyncWith):
            for item in sub.items:
                names |= _called_names(item.context_expr)
    return names


def untracked_writers(root: Path) -> list[str]:
    """`file:line funzione: manca ...` per ogni funzione che chiama `record_change` senza tetto."""
    problems: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in EXEMPT_PACKAGES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            body_calls = _called_names(fn)
            if "record_change" not in body_calls:
                continue
            missing = []
            if "tracked_write" not in _with_item_names(fn):
                missing.append("`with tracked_write(ctx)`")
            if "consume_tracked_write" not in body_calls:
                missing.append("`consume_tracked_write(tx, ctx)`")
            if missing:
                problems.append(f"{rel}:{fn.lineno} {fn.name}: manca {' e '.join(missing)}")
    return problems
