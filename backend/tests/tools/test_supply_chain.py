"""SR-076 / THR-090: cooldown sulle nuove versioni e dipendenze riproducibili."""

import tomllib
from typing import Any

import pytest

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


def _tool_exception(tool: str) -> str:
    """INFO-14: nessuna eccezione al cooldown ammessa sugli strumenti."""
    return ""


def tool_lines_comply(mk: str) -> bool:
    """True se le righe `tool install` rispettano la regola INFO-14 (usato anche in negativo)."""
    import re

    for tool in ("semgrep", "zizmor"):
        pin = rf'"{tool}==\$\({tool.upper()}_VERSION\)"'
        head = r'tool install --force --exclude-newer "\$\(TOOL_COOLDOWN\)" '
        if not re.search(head + _tool_exception(tool) + pin, mk):
            return False
    return True


_SG = '"semgrep==$(SEMGREP_VERSION)"'
_ZZ = '"zizmor==$(ZIZMOR_VERSION)"'
_OTHER = '--exclude-newer-package "requests=2099-01-01T00:00:00Z" '
_CERT_LITERAL = '--exclude-newer-package "certifi=2099-01-01T00:00:00Z" '


@pytest.mark.parametrize(
    "mutation",
    [(_SG, _OTHER + _SG), (_ZZ, _CERT_LITERAL + _ZZ)],
    ids=["other-package-on-semgrep", "certifi-exception-on-zizmor"],
)
def test_tool_cooldown_guard_rejects_any_cooldown_exception(
    mutation: tuple[str, str],
) -> None:
    """INFO-14: il controllo sa fallire (mutazioni sintetiche del Makefile)."""
    mk = _makefile()
    assert tool_lines_comply(mk), "il Makefile reale deve essere conforme"
    old, new = mutation
    assert old in mk
    assert not tool_lines_comply(mk.replace(old, new, 1))


def test_backend_has_no_cooldown_exception() -> None:
    """CR-SL00a-011: l'eccezione certifi è scaduta (2026-10-27) e va rimossa."""
    assert not _pyproject()["tool"]["uv"].get("exclude-newer-package")
    assert "TOOL_CERTIFI_EXCEPTION" not in _makefile()


def test_precommit_hooks_use_frozen_uv_run() -> None:
    """CR-SL00a-010: un commit non deve rifare il lock né sincronizzare l'ambiente."""
    cfg = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    runs = [ln for ln in cfg.splitlines() if "uv run" in ln]
    assert runs, "nessun hook con uv run"
    assert all("uv run --frozen" in ln for ln in runs), runs


def test_scan_deps_cleans_up_even_when_pip_audit_fails() -> None:
    """CR-SL00a-009: con `-e` il `rc=$$?; rm` non gira mai; serve `trap` o `|| rc=`."""
    mk = _makefile()
    body = mk.split("scan-deps:", 1)[1].split("\n\n", 1)[0]
    assert "trap " in body or "|| rc=" in body or "mktemp" in body
    assert not ("rc=$$?" in body and "trap " not in body and "|| rc=" not in body)


def test_pull_request_target_guard_matches_every_form_of_the_trigger() -> None:
    """CR-SL00a-013: il grep di ci.yml deve riconoscere anche `on: pull_request_target`."""
    import re
    import subprocess

    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    pattern = re.search(r"grep -RnE '([^']*pull_request_targe[^']*)'", ci)
    assert pattern, "controllo pull_request_target non trovato in ci.yml"
    samples = [
        "on: pull_request_target",
        "on: [push, pull_request_target]",
        "  pull_request_target:",
        "on:\n  pull_request_target:\n    branches: [main]",
    ]
    for sample in samples:
        found = subprocess.run(  # noqa: S603
            ["grep", "-E", pattern.group(1)],  # noqa: S607
            input=sample,
            capture_output=True,
            text=True,
            check=False,
        )
        assert found.returncode == 0, f"non riconosciuto: {sample!r}"


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
        assert re.search(head + _tool_exception(tool) + pin, mk)


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
