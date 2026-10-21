"""Lettura delle tabelle autorevoli dei documenti (fonte unica, OBJ-06)."""

import re

from .paths import DOCS

# docs/07-plan.md §4.1: insieme chiuso dei codici di validazione (errors[].code).
VALIDATION_CODES = frozenset(
    {
        "required",
        "string_too_long",
        "limit_reached",
        "url_invalid",
        "course_required",
        "guests_range",
        "priority_range",
        "date_invalid",
        "range_order",
        "duplicate_course",
        "invalid_value",
        "unknown_field",
        "dish_archived",
    }
)

_CODE_CELL = re.compile(r"\*{0,2}`([a-z_]+)`\*{0,2}")


def error_code_table() -> dict[str, int]:
    """Tabella 'Enumerazione ErrorCode' di ADR-0010: codice -> stato HTTP."""
    path = next(DOCS.glob("adr/ADR-0010-*.md"))
    rows: dict[str, int] = {}
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("| `code` | HTTP"):
            in_table = True
            continue
        if not in_table:
            continue
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        match = _CODE_CELL.fullmatch(cells[0])
        if match is None:
            continue  # riga separatrice
        rows[match.group(1)] = int(cells[1])
    return rows
