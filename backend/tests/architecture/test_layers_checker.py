"""Efficacia del controllo degli strati: alberi sintetici con violazioni note.

Un controllo che non rileva mai nulla sarebbe un test che passa sempre.
"""

from pathlib import Path

from support import layers


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "menu"
    for rel, body in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    return root


def test_upward_import_is_flagged(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"common/__init__.py": "from menu.family import x\n"})
    assert layers.layer_violations(layers.scan_imports(root))


def test_same_layer_import_is_flagged(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"audit/__init__.py": "import menu.history\n"})
    assert layers.layer_violations(layers.scan_imports(root))


def test_downward_import_is_allowed(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"family/__init__.py": "from menu.common import x\n"})
    assert layers.layer_violations(layers.scan_imports(root)) == []


def test_relative_upward_import_is_flagged(tmp_path: Path) -> None:
    root = _tree(
        tmp_path, {"platform/a.py": "from ..catalog import x\n", "catalog/__init__.py": ""}
    )
    assert layers.layer_violations(layers.scan_imports(root))


def test_composition_root_may_import_everything(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"app/__init__.py": "from menu.views import x\nimport menu.privacy\n"})
    assert layers.layer_violations(layers.scan_imports(root)) == []


def test_console_may_only_use_layers_up_to_3(tmp_path: Path) -> None:
    ok = _tree(tmp_path / "a", {"console/__init__.py": "from menu.audit import x\n"})
    bad = _tree(tmp_path / "b", {"console/__init__.py": "from menu.identity import x\n"})
    assert layers.layer_violations(layers.scan_imports(ok)) == []
    assert layers.layer_violations(layers.scan_imports(bad))


def test_console_client_may_only_use_common(tmp_path: Path) -> None:
    bad = _tree(tmp_path, {"console_client/__init__.py": "from menu.platform import x\n"})
    assert layers.layer_violations(layers.scan_imports(bad))


def test_cycle_is_detected() -> None:
    edges = [
        layers.ImportEdge("a", "b", "f", 1),
        layers.ImportEdge("b", "c", "f", 1),
        layers.ImportEdge("c", "a", "f", 1),
    ]
    assert layers.cycles(edges)


def test_importing_tests_is_flagged(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"family/__init__.py": "from support.probe import x\n"})
    assert [e for e in layers.scan_imports(root) if e.target.startswith("!")]


def test_unknown_module_is_flagged(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"mystery/__init__.py": "", "common/__init__.py": ""})
    assert layers.unknown_modules(root) == ["mystery"]


def test_common_third_party_restriction(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"common/__init__.py": "import pydantic\nimport sqlalchemy\n"})
    out = layers.restricted_third_party(root)
    assert len(out) == 1
    assert "sqlalchemy" in out[0]


def test_session_outside_tenancy_is_flagged_inside_is_not(tmp_path: Path) -> None:
    body = "from sqlalchemy.orm import Session\ns = Session()\ne = create_engine('x')\n"
    root = _tree(tmp_path, {"family/repo.py": body, "tenancy/__init__.py": body})
    out = layers.session_violations(root)
    assert out
    assert all("family" in o for o in out)


def test_wall_clock_in_domain_is_flagged_platform_exempt(tmp_path: Path) -> None:
    body = "import datetime\nx = datetime.now()\n"
    root = _tree(tmp_path, {"planning/a.py": body, "platform/a.py": body})
    out = layers.clock_violations(root)
    assert out
    assert all("planning" in o for o in out)


def test_time_time_import_is_flagged(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"planning/a.py": "from time import time\n"})
    assert layers.clock_violations(root)


def test_owner_role_string_flagged_but_docstring_is_not(tmp_path: Path) -> None:
    role = layers.OWNER_ROLE
    code = f'"""Cita {role} nella docstring."""\nURL = "postgresql://{role}@h/db"\n'
    root = _tree(tmp_path, {"tenancy/a.py": code})
    out = layers.owner_credential_violations(root)
    assert len(out) == 1
