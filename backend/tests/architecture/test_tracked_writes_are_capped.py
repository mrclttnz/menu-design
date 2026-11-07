"""Ogni scrittura che registra un evento passa dal tetto giornaliero (backlog SL-05, SR-070).

Una rotta tracciata che dimentica `tracked_write` darebbe 500 invece di 429 al 5.001° scritto; una
che dimentica `consume_tracked_write` non conterebbe nulla. La regola vale per ogni funzione dei
sorgenti che chiama `record_change`; il controllo sa fallire (alberi sintetici qui sotto).
SL-06a porta il secondo chiamante (la presenza del pasto), il primo dopo `set_status`.
"""

from pathlib import Path

import pytest

from support.paths import SRC
from support.tracked_scan import untracked_writers

GOOD = """
def write(ctx):
    with ratelimit.tracked_write(ctx), tenancy.family_tx(ctx) as tx:
        ratelimit.consume_tracked_write(tx, ctx)
        record_change(tx, ctx)
"""


def _tree(tmp_path: Path, **files: str) -> Path:
    for name, source in files.items():
        target = tmp_path / name.replace("__", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    return tmp_path


def test_the_real_sources_cap_every_event_writer() -> None:
    assert untracked_writers(SRC) == []


def test_the_checker_accepts_a_correct_writer(tmp_path: Path) -> None:
    assert untracked_writers(_tree(tmp_path, **{"planning__meals.py": GOOD})) == []


@pytest.mark.parametrize(
    ("source", "missing"),
    [
        (GOOD.replace("with ratelimit.tracked_write(ctx), ", "with "), "tracked_write"),
        (
            GOOD.replace("        ratelimit.consume_tracked_write(tx, ctx)\n", ""),
            "consume_tracked_write",
        ),
        ("def w(tx, ctx):\n    record_change(tx, ctx)\n", "tracked_write"),
        (
            "def w(ctx):\n    with family_tx(ctx) as tx:\n        history.record_change(tx, ctx)\n",
            "consume_tracked_write",
        ),
        (
            "def w(ctx):\n    with tracked_write(ctx):\n        pass\n"
            "    def inner(tx):\n        record_change(tx, ctx)\n",
            "tracked_write",
        ),
    ],
)
def test_the_checker_flags_a_writer_that_forgets_the_cap(
    tmp_path: Path, source: str, missing: str
) -> None:
    problems = untracked_writers(_tree(tmp_path, **{"planning__meals.py": source}))
    assert problems, "nessuna violazione trovata"
    assert any(missing in p for p in problems), problems


def test_the_history_package_itself_is_exempt(tmp_path: Path) -> None:
    assert (
        untracked_writers(
            _tree(tmp_path, **{"history__record.py": "def f(tx):\n    record_change(tx)\n"})
        )
        == []
    )
