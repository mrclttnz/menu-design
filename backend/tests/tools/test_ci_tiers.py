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


@pytest.mark.parametrize("target", ["test-db", "test-int", "test-sec", "e2e", "perf", "smoke"])
def test_placeholder_target_fails_loudly_when_called_directly(target: str) -> None:
    """Piano §6.1: un segnaposto fallisce con messaggio esplicito, mai verde a vuoto."""
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
