"""`CI_TIERS` di scripts/ci.sh contro la tabella delle slice di docs/STATUS.md.

08 §18.1 / piano §6.1 (OBJ-13): ogni livello di una slice DONE è attivo e nessun livello è
attivo prima della sua slice. Una slice IN PROGRESS può già aver attivato i propri livelli.
"""

import re
import subprocess

import pytest

from support.paths import DOCS, REPO

# Piano §6.1, tabella "Livelli attivati": slice -> livelli aggiunti a CI_TIERS.
SLICE_TIERS: dict[str, set[str]] = {
    "SL-00a": {"lint", "unit", "contract", "scan"},
    "SL-00b": {"db", "container"},
    "SL-01": {"web", "e2e"},
}
CI_SH = REPO / "scripts" / "ci.sh"
MAKEFILE = REPO / "Makefile"


def _ci_tiers() -> list[str]:
    match = re.search(r"^CI_TIERS=\(([^)]*)\)", CI_SH.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, "CI_TIERS non trovato in scripts/ci.sh"
    return match.group(1).split()


def _slice_status() -> dict[str, str]:
    status: dict[str, str] = {}
    for line in (DOCS / "STATUS.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) >= 3 and re.fullmatch(r"SL-\d+[a-z]?", cells[0]):
            status[cells[0]] = cells[2]
    return status


def test_status_table_lists_all_slices_with_tiers() -> None:
    assert set(SLICE_TIERS) <= set(_slice_status())


def test_ci_tiers_has_no_duplicates() -> None:
    tiers = _ci_tiers()
    assert len(tiers) == len(set(tiers))


def test_every_ci_tier_is_known() -> None:
    known = set().union(*SLICE_TIERS.values())
    assert set(_ci_tiers()) <= known


def test_done_slices_have_their_tiers_active() -> None:
    status = _slice_status()
    required = set().union(*(t for s, t in SLICE_TIERS.items() if status[s] == "DONE"))
    assert required <= set(_ci_tiers())


def test_no_tier_active_before_its_slice_started() -> None:
    status = _slice_status()
    allowed = set().union(*(t for s, t in SLICE_TIERS.items() if status[s] != "TODO"))
    assert set(_ci_tiers()) <= allowed


def test_every_ci_tier_has_a_make_target_mapping() -> None:
    text = CI_SH.read_text(encoding="utf-8")
    for tier in _ci_tiers():
        assert re.search(rf"\[{tier}\]=", text), tier


def test_ci_lists_placeholder_targets_nowhere() -> None:
    """Un livello attivo non punta mai a un segnaposto ('disponibile da SL-xx')."""
    targets = dict(re.findall(r"\[(\w+)\]=\"([\w-]+)\"", CI_SH.read_text(encoding="utf-8")))
    for tier in _ci_tiers():
        dry = subprocess.run(  # noqa: S603
            ["make", "-n", "--no-print-directory", "-C", str(REPO), targets[tier]],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert dry.returncode == 0, dry.stderr
        assert "non è ancora disponibile" not in dry.stdout, f"{tier} -> segnaposto"


@pytest.mark.parametrize("target", ["perf", "smoke", "lighthouse", "dast"])
def test_placeholder_target_fails_loudly_when_called_directly(target: str) -> None:
    """Piano §6.1: un segnaposto fallisce con messaggio esplicito, mai verde a vuoto.

    SL-01: `e2e` è uscito dall'elenco perché da questa slice è un livello attivo
    (modifica prevista dal piano §6.1, non un indebolimento del controllo)."""
    proc = subprocess.run(  # noqa: S603
        ["make", "--no-print-directory", "-C", str(REPO), target],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode != 0
    assert "disponibile da" in proc.stderr


def test_ci_summary_declares_executed_tiers() -> None:
    """08 §18.1: il riepilogo di `make ci` elenca i livelli eseguiti."""
    assert "livelli eseguiti" in CI_SH.read_text(encoding="utf-8")


# --- SL-00b: i livelli `db` e `container` diventano attivi (piano §6.1, 08 §18.1) -------------


def test_sl_00b_tiers_are_active_in_ci_sh() -> None:
    assert {"db", "container"} <= set(_ci_tiers())


@pytest.mark.parametrize(
    "target", ["test-db", "test-int", "test-sec", "test-prop", "test-conc", "scan-container", "dev"]
)
def test_sl_00b_targets_are_no_longer_placeholders(target: str) -> None:
    dry = subprocess.run(  # noqa: S603
        ["make", "-n", "--no-print-directory", "-C", str(REPO), target],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert dry.returncode == 0, dry.stderr
    assert "non è ancora disponibile" not in dry.stdout, f"{target} è ancora un segnaposto"


def test_db_tier_runs_every_database_backed_suite() -> None:
    """Il livello `db` copre db, integrazione, sicurezza, proprietà e concorrenza."""
    targets = dict(re.findall(r"\[(\w+)\]=\"([\w-]+)\"", CI_SH.read_text(encoding="utf-8")))
    assert "db" in targets, "livello db non mappato in scripts/ci.sh"
    dry = subprocess.run(  # noqa: S603
        ["make", "-n", "--no-print-directory", "-C", str(REPO), targets["db"]],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    for folder in ("tests/db", "tests/integration", "tests/security", "tests/property",
                   "tests/concurrency"):  # fmt: skip
        assert folder in dry.stdout, f"{folder} non è eseguito dal livello db"


def test_container_tier_runs_hadolint_build_and_trivy() -> None:
    targets = dict(re.findall(r"\[(\w+)\]=\"([\w-]+)\"", CI_SH.read_text(encoding="utf-8")))
    assert "container" in targets
    dry = subprocess.run(  # noqa: S603
        ["make", "-n", "--no-print-directory", "-C", str(REPO), targets["container"]],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    for needle in ("hadolint", "docker build", "trivy image", "trivy config"):
        assert needle in dry.stdout, f"{needle} manca dal livello container"


ACTIVATED_BY_SL_00B = (
    "test-db",
    "test-int",
    "test-sec",
    "test-prop",
    "test-conc",
    "scan-container",
)


def help_sections(help_text: str) -> tuple[str, str]:
    """(testo prima della riga 'Segnaposto', riga/e dei segnaposto che la seguono)."""
    lines = help_text.splitlines()
    idx = next(i for i, ln in enumerate(lines) if ln.lower().startswith("segnaposto"))
    return "\n".join(lines[:idx]), "\n".join(lines[idx:])


def activated_targets_listed_as_placeholders(help_text: str) -> list[str]:
    _, placeholders = help_sections(help_text)
    words = set(placeholders.replace("(", " ").replace(")", " ").split())
    return [t for t in ACTIVATED_BY_SL_00B if t in words]


def test_make_help_lists_activated_targets_as_active() -> None:
    """CR-SL00a-013 / CR-SL00b-001: dopo SL-00b i livelli DB non sono 'segnaposto'."""
    out = subprocess.run(  # noqa: S603
        ["make", "--no-print-directory", "-C", str(REPO), "help"],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    ).stdout
    active, placeholders = help_sections(out)
    assert placeholders.strip(), "sezione segnaposto vuota o non trovata"
    for target in ACTIVATED_BY_SL_00B:
        assert target in active, f"{target} non è elencato tra i target attivi"
    assert activated_targets_listed_as_placeholders(out) == []


def test_help_check_goes_red_when_an_activated_target_is_a_placeholder() -> None:
    """Mutazione sintetica del testo di `make help`: il controllo deve segnalare test-db."""
    mutated = (
        "Target attivi: sync lint\n"
        "Segnaposto ('disponibile da SL-xx', falliscono se chiamati):\n"
        "        e2e perf test-db\n"
    )
    assert activated_targets_listed_as_placeholders(mutated) == ["test-db"]


# --- SL-01: i livelli `web` ed `e2e` diventano attivi (piano §6.1, 08 §18.1) -------------------


def test_sl_01_tiers_are_active_in_ci_sh() -> None:
    assert {"web", "e2e"} <= set(_ci_tiers())


def test_sl_01_tiers_map_to_real_targets_that_run_pnpm_and_playwright() -> None:
    text = CI_SH.read_text(encoding="utf-8")
    targets = dict(re.findall(r"\[(\w+)\]=\"([\w-]+)\"", text))
    assert {"web", "e2e"} <= set(targets)
    web = subprocess.run(  # noqa: S603
        ["make", "-n", "--no-print-directory", "-C", str(REPO), targets["web"]],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    e2e = subprocess.run(  # noqa: S603
        ["make", "-n", "--no-print-directory", "-C", str(REPO), targets["e2e"]],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert web.returncode == 0, web.stderr
    assert e2e.returncode == 0, e2e.stderr
    assert "non è ancora disponibile" not in web.stdout + e2e.stdout
    assert "pnpm" in web.stdout
    assert "playwright" in e2e.stdout or "test:e2e" in e2e.stdout
