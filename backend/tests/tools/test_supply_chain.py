"""SR-076 / THR-090: cooldown sulle nuove versioni e dipendenze riproducibili."""

import tomllib
from typing import Any

from support.paths import BACKEND, REPO


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))


def test_pyproject_has_exclude_newer_cooldown() -> None:
    value = _pyproject()["tool"]["uv"]["exclude-newer"]
    assert isinstance(value, str)
    assert value.strip()


def test_exclude_newer_cooldown_is_at_least_seven_days() -> None:
    """SR-076: durata relativa di almeno 7 giorni (V-7)."""
    import re

    value = str(_pyproject()["tool"]["uv"]["exclude-newer"])
    m = re.fullmatch(r"(\d+)\s*(day|days|week|weeks)", value.strip())
    assert m, f"formato inatteso: {value!r}"
    days = int(m.group(1)) * (7 if m.group(2).startswith("week") else 1)
    assert days >= 7


def test_lockfile_is_committed() -> None:
    assert (BACKEND / "uv.lock").is_file()


def test_ci_uses_frozen_lockfile() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "sync --frozen" in makefile
    assert "run --frozen" in makefile


def _makefile() -> str:
    return (REPO / "Makefile").read_text(encoding="utf-8")


def test_lockfile_checked_in_lint() -> None:
    """CR-SL00a-004: uv.lock non deve essere obsoleto rispetto a pyproject."""
    assert "uv lock --check" in _makefile() or "$(UV) lock --check" in _makefile()


def test_scan_tools_installed_with_pinned_version_and_cooldown() -> None:
    """SEC-SL00a-003: semgrep/zizmor fissati, con cooldown, una sola fonte (Makefile)."""
    import re

    mk = _makefile()
    cooldown = re.search(r"^TOOL_COOLDOWN\s*:=\s*(\d+) days$", mk, re.M)
    assert cooldown
    assert int(cooldown.group(1)) >= 7
    for tool in ("semgrep", "zizmor"):
        assert re.search(rf"^{tool.upper()}_VERSION\s*:=\s*\d+\.\d+\.\d+$", mk, re.M)
        pin = rf'"{tool}==\$\({tool.upper()}_VERSION\)"'
        head = r'tool install --force --exclude-newer "\$\(TOOL_COOLDOWN\)" '
        optional_exception = r'(?:--exclude-newer-package "[^"]+" )?'
        assert re.search(head + optional_exception + pin, mk)


def test_ci_does_not_install_tools_outside_makefile() -> None:
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "uv tool install" not in ci
    assert "SEMGREP_VERSION" not in ci
    assert "ZIZMOR_VERSION" not in ci
    assert "make tools-semgrep" in ci
    assert "make tools-zizmor" in ci


def test_sast_runs_custom_rule_tests_and_path_check() -> None:
    """CR-SL00a-005: fixture --test per tutte le regole + verifica dei filtri paths."""
    mk = _makefile()
    assert "scan-sast: scan-rules" in mk
    for yaml_name in ("sql", "frontend", "migrations-now"):
        assert f"semgrep --test --metrics=off --config .semgrep/{yaml_name}.yaml" in mk
    assert "scripts/check_semgrep_rules.py" in mk


def test_gitleaks_does_not_allowlist_env_example() -> None:
    cfg = (REPO / ".gitleaks.toml").read_text(encoding="utf-8")
    assert ".env" not in cfg


def test_semgrep_install_pins_certifi_past_ghsa_6q48() -> None:
    """SEC-SL00a-010: il cooldown non deve risolvere certifi 2026.7.22 (GHSA-6q48-6c7w-9gw2)."""
    import re

    mk = _makefile()
    m = re.search(r"^TOOL_CERTIFI_EXCEPTION\s*:=\s*certifi=(\d{4}-\d{2}-\d{2})T", mk, re.M)
    assert m
    # certifi 2026.10.19 (fix) è stato caricato il 2026-10-20: con una data precedente
    # uv risolve ancora la 2026.10.18 vulnerabile.
    assert m.group(1) >= "2026-10-21"
    line = next(ln for ln in mk.splitlines() if "tool install" in ln and "semgrep==" in ln)
    assert '--exclude-newer-package "$(TOOL_CERTIFI_EXCEPTION)"' in line
