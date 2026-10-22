"""SEC-SL00b-002: il controllo statico del contesto sa fallire, anche con parentesi annidate."""

import pytest

from support.paths import SRC
from support.sqlscan import session_scope_violations

CONTEXT_LINE = "set_config('app.family_id', cast(:family as text), true)"


@pytest.mark.parametrize(
    "bad",
    [
        "set_config('app.family_id', :f, false)",
        "set_config('app.family_id', cast(:family as text), false)",
        "set_config('app.family_id', cast(:family as text), FALSE)",
        "set_config('app.family_id', :f, 'off')",
        "set_config('app.family_id', :f, 'f')",
        "set_config('app.family_id', :f, 'no')",
        "set_config('app.family_id', :f, '0')",
        "set_config('app.family_id', :f, 0)",
        "pg_catalog.set_config('app.family_id', :f, (false))",
        "set_config('app.family_id', coalesce(:f, '') , false )",
        "set_config('app.family_id', :f, :flag)",
        "set_config('app.family_id', :f)",
        "SET app.family_id = 'x'",
        "SET SESSION app.family_id = 'x'",
        "SET ROLE menu_owner",
        "set role menu_owner",
        "SET SESSION ROLE menu_owner",
        "SET SESSION AUTHORIZATION menu_owner",
        "SET search_path = public",
        "RESET ROLE",
        "RESET SESSION AUTHORIZATION",
        "RESET ALL",
        "reset app.family_id",
        '"select set_config(\'app.x\', cast(:a as text), "\n"false)"',
    ],
)
def test_checker_flags_every_session_scoped_spelling(bad: str) -> None:
    assert session_scope_violations(bad) != [], bad


@pytest.mark.parametrize(
    "good",
    [
        CONTEXT_LINE,
        "select set_config('app.family_id', cast(:f as text), true), "
        "set_config('app.role', cast(:r as text), true)",
        "pg_catalog.set_config('app.family_id', :f, TRUE)",
        "SET LOCAL app.family_id = 'x'",
        "SET LOCAL ROLE x",
        "select 1",
    ],
)
def test_checker_accepts_transaction_local_forms(good: str) -> None:
    assert session_scope_violations(good) == []


def test_real_tenancy_sources_are_clean_and_do_set_the_context() -> None:
    code = "\n".join(p.read_text(encoding="utf-8") for p in (SRC / "tenancy").rglob("*.py"))
    assert "set_config" in code
    assert session_scope_violations(code) == []


@pytest.mark.parametrize("replacement", ["false", "'off'", "(false)", "'f'", "0"])
def test_checker_goes_red_on_a_mutated_copy_of_the_real_tenancy_source(replacement: str) -> None:
    """Mutazione in memoria (nessun file toccato): l'ultimo argomento del contesto non è true."""
    code = "\n".join(p.read_text(encoding="utf-8") for p in (SRC / "tenancy").rglob("*.py"))
    assert session_scope_violations(code) == []
    marker = "as text), true)"
    assert marker in code, "forma del contesto in engine.py cambiata: aggiornare il test"
    mutated = code.replace(marker, f"as text), {replacement})", 1)
    assert session_scope_violations(mutated) != []
    assert session_scope_violations(code + "\n# SET ROLE menu_owner\n") != []
