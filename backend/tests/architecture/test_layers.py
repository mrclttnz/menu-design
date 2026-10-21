"""Test d'architettura sugli strati (piano §2.1; SR-009 base, ADR-0003, THR-110).

Applicano i controlli di `support.layers` al codice reale di `src/menu`.
"""

from support import layers
from support.paths import SRC


def test_imports_respect_layer_table() -> None:
    assert layers.layer_violations(layers.scan_imports(SRC)) == []


def test_no_import_cycles() -> None:
    assert layers.cycles(layers.scan_imports(SRC)) == []


def test_every_top_level_module_is_in_layer_table() -> None:
    assert layers.unknown_modules(SRC) == []


def test_all_planned_modules_exist() -> None:
    present = {p.name for p in SRC.iterdir() if p.is_dir()}
    assert set(layers.LAYERS) <= present


def test_common_and_console_client_use_only_allowed_third_party() -> None:
    assert layers.restricted_third_party(SRC) == []


def test_sqlalchemy_sessions_only_in_tenancy() -> None:
    assert layers.session_violations(SRC) == []


def test_src_never_imports_tests() -> None:
    edges = layers.scan_imports(SRC)
    assert [e for e in edges if e.target.startswith("!")] == []


def test_src_never_references_owner_role() -> None:
    assert layers.owner_credential_violations(SRC) == []


def test_domain_does_not_read_wall_clock() -> None:
    assert layers.clock_violations(SRC) == []
