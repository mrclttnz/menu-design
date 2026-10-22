"""Controllo statico del contesto di sessione nel codice SQL (THR-027, SR-042; SEC-SL00b-002).

Tollera le parentesi annidate (`cast(:x as text)`) e le stringhe Python concatenate; accetta come
terzo argomento di `set_config` SOLO `true` (qualunque altra scrittura di "false" o un valore
non letterale è un errore); vieta SET/RESET di sessione di role, authorization, search_path,
`app.*` e ALL.
"""

import re

_JOIN = re.compile(r"""(["'])\s*\n\s*\1""")
_SESSION_STATEMENT = re.compile(
    r"\b(?:SET|RESET)\s+(?!LOCAL\b)(?:SESSION\s+)?"
    r"(?:ROLE|SESSION\s+AUTHORIZATION|AUTHORIZATION|SEARCH_PATH|APP\.\w+|ALL)\b",
    re.IGNORECASE,
)


def _arguments(text: str, start: int) -> list[str] | None:
    """Argomenti di primo livello della chiamata che si apre prima di `start`."""
    depth = 1
    args: list[str] = []
    current: list[str] = []
    for ch in text[start:]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append("".join(current))
                return args
        if ch == "," and depth == 1:
            args.append("".join(current))
            current = []
        else:
            current.append(ch)
    return None


def session_scope_violations(code: str) -> list[str]:
    normalised = _JOIN.sub("", code)
    found = []
    for match in re.finditer(r"set_config\s*\(", normalised, re.IGNORECASE):
        args = _arguments(normalised, match.end())
        if args is not None and args[0].strip() == "...":
            continue  # citazione in un commento o docstring
        if args is None or len(args) != 3:
            found.append(
                f"set_config con argomenti non analizzabili: {normalised[match.start() :][:60]!r}"
            )
            continue
        third = re.sub(r"""["'\s()]""", "", args[2]).lower()
        if third != "true":
            found.append(f"set_config con terzo argomento {args[2].strip()!r} (solo true)")
    for statement in _SESSION_STATEMENT.finditer(normalised):
        found.append(f"istruzione di sessione: {statement.group(0)!r}")
    return found
