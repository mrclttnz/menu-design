"""Percorsi del repository, calcolati dalla posizione di questo file (mai dalla cwd)."""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
SRC = BACKEND / "src" / "menu"
TESTS = BACKEND / "tests"
DOCS = REPO / "docs"
