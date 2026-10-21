"""Controllo degli strati del backend (piano §2.1) con sola analisi `ast`.

Il controllo vive qui, come funzione pura su una cartella, così `test_layers.py` lo applica
a `src/menu` e `test_layers_checker.py` ne prova l'efficacia su alberi sintetici con violazioni.
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

LAYERS: dict[str, int] = {
    "common": 0,
    "platform": 1,
    "tenancy": 2,
    "audit": 3,
    "history": 3,
    "jobs": 3,
    "ratelimit": 4,
    "access": 4,
    "identity": 5,
    "family": 6,
    "catalog": 7,
    "planning": 8,
    "attendance": 9,
    "privacy": 10,
    "views": 11,
    "seeding": 11,
    "console": 11,
    "console_client": 11,
    "app": 12,
}
COMPOSITION_ROOT = "app"
SESSION_FACTORIES = frozenset(
    {
        "Session",
        "AsyncSession",
        "sessionmaker",
        "async_sessionmaker",
        "scoped_session",
        "create_engine",
        "create_async_engine",
    }
)
CLOCK_ATTRS = {
    "datetime": {"now", "utcnow", "today"},
    "date": {"today"},
    "time": {"time", "time_ns"},
}
CLOCK_EXEMPT_MODULES = frozenset({"platform"})  # timestamp dei log, non istanti persistiti
TEST_PACKAGES = frozenset({"tests", "conftest", "support"})
OWNER_ROLE = "menu_owner"


@dataclass(frozen=True)
class ImportEdge:
    source: str  # modulo di primo livello di `menu` (es. "family"), "__main__" o "<root>"
    target: str
    file: str
    line: int


def _top_module(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    if len(rel.parts) == 1:
        return "<root>" if rel.name == "__init__.py" else rel.stem
    return rel.parts[0]


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _package_parts(path: Path, root: Path) -> list[str]:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ["menu", *parts]


def _imported_modules(node: ast.AST, pkg: list[str], is_init: bool) -> list[str]:
    """Nomi assoluti dei moduli importati da `node` (relativi risolti)."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        base_pkg = pkg if is_init else pkg[:-1]
        if node.level:
            keep = len(base_pkg) - (node.level - 1)
            base = ".".join(base_pkg[:keep] + ([node.module] if node.module else []))
        else:
            base = node.module or ""
        if base == "menu":
            return [f"menu.{a.name}" for a in node.names]
        return [base]
    return []


def scan_imports(root: Path) -> list[ImportEdge]:
    edges: list[ImportEdge] = []
    for path in _python_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        source = _top_module(path, root)
        pkg = _package_parts(path, root)
        for node in ast.walk(tree):
            for name in _imported_modules(node, pkg, path.name == "__init__.py"):
                lineno: int = node.lineno  # type: ignore[attr-defined]  # solo nodi di import
                top = name.split(".")[0]
                if top == "menu":
                    parts = name.split(".")
                    target = parts[1] if len(parts) > 1 else "<root>"
                    edges.append(ImportEdge(source, target, str(path), lineno))
                elif top in TEST_PACKAGES:
                    edges.append(ImportEdge(source, f"!{top}", str(path), lineno))
    return edges


def _third_party(root: Path, module: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _python_files(root):
        if _top_module(path, root) != module:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = [node.module or ""]
            else:
                continue
            for n in names:
                top = n.split(".")[0]
                if top and top != "menu" and top not in sys.stdlib_module_names:
                    found.append((str(path), top))
    return found


def _allowed(source: str, target: str) -> bool:
    if source == target or source in {COMPOSITION_ROOT, "__main__"}:
        return True
    if target not in LAYERS:
        return False
    if source == "console_client":
        return target == "common"
    if source == "console":
        return LAYERS[target] <= 3
    if source not in LAYERS:
        return False
    return LAYERS[target] < LAYERS[source]


def layer_violations(edges: list[ImportEdge]) -> list[str]:
    out = []
    for e in edges:
        if e.target.startswith("!"):
            continue
        if e.source == "<root>":
            out.append(f"{e.file}:{e.line}: il pacchetto radice non importa moduli ({e.target})")
        elif not _allowed(e.source, e.target):
            out.append(f"{e.file}:{e.line}: {e.source} non può importare {e.target}")
    return out


def cycles(edges: list[ImportEdge]) -> list[list[str]]:
    graph: dict[str, set[str]] = {}
    for e in edges:
        if e.source != e.target and not e.target.startswith("!"):
            graph.setdefault(e.source, set()).add(e.target)
    found: list[list[str]] = []
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        state[node] = 1
        for nxt in sorted(graph.get(node, ())):
            if state.get(nxt) == 1:
                found.append([*stack[stack.index(nxt) :], nxt] if nxt in stack else [node, nxt])
            elif state.get(nxt) is None:
                visit(nxt, [*stack, nxt])
        state[node] = 2

    for n in sorted(graph):
        if state.get(n) is None:
            visit(n, [n])
    return found


def unknown_modules(root: Path) -> list[str]:
    known = set(LAYERS)
    out = []
    for child in sorted(root.iterdir()):
        if child.name.startswith("__") or child.name == "py.typed":
            continue
        name = child.stem if child.is_file() else child.name
        if name not in known:
            out.append(name)
    return out


def restricted_third_party(root: Path) -> list[str]:
    """`common`: solo libreria standard e Pydantic. `console_client`: solo libreria standard."""
    out = []
    allowed_common = {"pydantic", "typing_extensions", "annotated_types"}
    for path, top in _third_party(root, "common"):
        if top not in allowed_common:
            out.append(f"{path}: common importa {top} (ammessi solo stdlib e Pydantic)")
    for path, top in _third_party(root, "console_client"):
        out.append(f"{path}: console_client importa {top} (ammessa solo la libreria standard)")
    return out


def _call_name(node: ast.Call) -> tuple[str | None, str | None]:
    f = node.func
    if isinstance(f, ast.Name):
        return None, f.id
    if isinstance(f, ast.Attribute):
        owner = f.value
        owner_name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", None)
        return owner_name, f.attr
    return None, None


def session_violations(root: Path) -> list[str]:
    out = []
    for path in _python_files(root):
        if _top_module(path, root) == "tenancy":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                owner, name = _call_name(node)
                if name in SESSION_FACTORIES or (owner == "psycopg" and name == "connect"):
                    out.append(f"{path}:{node.lineno}: {name}() fuori da tenancy (ADR-0003)")
    return out


def clock_violations(root: Path) -> list[str]:
    out = []
    for path in _python_files(root):
        if _top_module(path, root) in CLOCK_EXEMPT_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                owner, name = _call_name(node)
                if owner in CLOCK_ATTRS and name in CLOCK_ATTRS[owner]:
                    out.append(f"{path}:{node.lineno}: {owner}.{name}() (usare app.now_utc())")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "time"
                and any(a.name in {"time", "time_ns"} for a in node.names)
            ):
                out.append(f"{path}:{node.lineno}: import di time.time")
    return out


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ids.add(id(value))
    return ids


def owner_credential_violations(root: Path) -> list[str]:
    """Nessuna stringa `menu_owner` nel codice (docstring escluse) sotto `root`."""
    out = []
    for path in _python_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and OWNER_ROLE in node.value
                and id(node) not in skip
            ):
                out.append(f"{path}:{node.lineno}: riferimento a {OWNER_ROLE}")
    return out
