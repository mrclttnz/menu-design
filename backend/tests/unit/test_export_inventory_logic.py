"""Registro `ExportContributor` e controllo d'inventario (plan §2.2, OBJ-02; 08 §6.8). SL-02.

Il controllo `export_inventory_problems` deve SAPER fallire (un inventario che non sa fallire non
vale nulla): qui è provato con dati sintetici. Il confronto con le tabelle reali sta in
`tests/db/test_export_inventory.py`.

Contratto assunto per il registro (in `menu.common`, strato 0, solo libreria standard):
`ExportContributor` (Protocol con `tables: frozenset[str]`, `export_family(tx)`,
`export_self(tx, account_id, person_id)`), `register_export_contributor(c)` e
`export_contributors() -> tuple[ExportContributor, ...]`. I contributori si registrano
all'import del proprio modulo (`menu.family`, `menu.catalog`).
"""

import importlib
import pkgutil
from typing import Any

from support.export_inventory import (
    FORBIDDEN_EXPORT_COLUMNS,
    NOT_EXPORTED,
    export_inventory_problems,
    forbidden_columns_in,
)

TABLES = {"family", "course", "person"}


def test_inventory_accepts_a_complete_and_exclusive_declaration() -> None:
    declared = {"family.F": {"family", "person"}, "catalog.C": {"course"}}
    assert export_inventory_problems(declared, TABLES, {}) == []


def test_inventory_flags_a_family_table_without_contributor() -> None:
    declared = {"family.F": {"family", "person"}}
    assert export_inventory_problems(declared, TABLES, {}) == [
        "course: tabella di famiglia senza ExportContributor"
    ]


def test_inventory_flags_a_table_declared_by_two_contributors() -> None:
    declared = {"a.A": {"family", "person", "course"}, "b.B": {"course"}}
    problems = export_inventory_problems(declared, TABLES, {})
    assert problems == ["course: dichiarata da più contributori ['a.A', 'b.B']"]


def test_inventory_flags_a_contributor_claiming_a_non_family_table() -> None:
    declared = {"a.A": TABLES | {"security_event"}}
    assert export_inventory_problems(declared, TABLES, {}) == [
        "security_event: dichiarata da ['a.A'] ma non è di famiglia"
    ]


def test_inventory_accepts_the_self_scope_tables_of_identity_once() -> None:
    """SL-03a: `account` e `session` non sono di famiglia ma entrano nel perimetro `self`."""
    declared = {"family.F": TABLES, "identity.I": {"account", "session"}}
    assert export_inventory_problems(declared, TABLES, {}) == []
    twice = {**declared, "other.O": {"account"}}
    assert export_inventory_problems(twice, TABLES, {}) == [
        "account: dichiarata da più contributori ['identity.I', 'other.O']"
    ]
    assert export_inventory_problems(declared, TABLES, {}, non_family_exported=()) == [
        "account: dichiarata da ['identity.I'] ma non è di famiglia",
        "session: dichiarata da ['identity.I'] ma non è di famiglia",
    ]


def test_inventory_still_rejects_other_non_family_tables_next_to_identity() -> None:
    declared = {"family.F": TABLES, "identity.I": {"account", "session", "auth_flow"}}
    assert export_inventory_problems(declared, TABLES, {}) == [
        "auth_flow: dichiarata da ['identity.I'] ma non è di famiglia"
    ]


def test_inventory_requires_a_reason_for_every_exclusion_and_rejects_exported_exclusions() -> None:
    declared = {"a.A": TABLES}
    assert export_inventory_problems(declared, TABLES, {"person": "motivo"}) == [
        "person: esclusa dall'export ma dichiarata da ['a.A']"
    ]
    assert export_inventory_problems({"a.A": TABLES}, TABLES, {"ghost": "x"}) == [
        "ghost: voce di NOT_EXPORTED senza tabella di famiglia"
    ]


def test_every_exclusion_carries_a_reason() -> None:
    assert NOT_EXPORTED
    assert all(len(reason) > 20 for reason in NOT_EXPORTED.values())


def test_forbidden_columns_detector_flags_each_excluded_column() -> None:
    for column in sorted(FORBIDDEN_EXPORT_COLUMNS):
        assert forbidden_columns_in({"person": [{"id": 1, column: "x"}]}) == [f"person.{column}"]
    assert forbidden_columns_in({"person": [{"id": 1, "display_name": "x"}], "course": []}) == []
    assert {"email", "last_visit_at", "dish_sort_preference", "auth_subject", "ip"} <= (
        FORBIDDEN_EXPORT_COLUMNS
    )


# --- registro reale -------------------------------------------------------------------------------


def _registry() -> Any:
    """`menu.common.export_contributors` (contratto assunto), letto senza import statico."""
    return importlib.import_module("menu.common").export_contributors


def _import_every_menu_module() -> None:
    import menu

    for info in pkgutil.walk_packages(menu.__path__, "menu."):
        if info.name.endswith("__main__"):
            continue
        importlib.import_module(info.name)


def test_registry_api_exists_in_common() -> None:
    import menu.common as common

    for name in ("ExportContributor", "register_export_contributor", "export_contributors"):
        assert hasattr(common, name), f"menu.common.{name} assente (registro OBJ-02)"


def test_family_and_catalog_register_a_contributor_with_their_tables() -> None:
    """Plan SL-02: contributori di `family` e `catalog` (`course`), registrati all'import."""
    export_contributors = _registry()

    _import_every_menu_module()
    contributors = export_contributors()
    assert isinstance(contributors, tuple)
    by_package: dict[str, set[str]] = {}
    for c in contributors:
        package = type(c).__module__.split(".")[1]
        by_package.setdefault(package, set()).update(c.tables)
    assert {"family", "family_default_meal", "person"} <= by_package.get("family", set())
    assert "course" in by_package.get("catalog", set())


def test_every_contributor_declares_tables_and_both_scopes() -> None:
    export_contributors = _registry()

    _import_every_menu_module()
    assert export_contributors(), "nessun ExportContributor registrato"
    for c in export_contributors():
        assert isinstance(c.tables, frozenset)
        assert c.tables
        assert all(isinstance(t, str) and t for t in c.tables)
        assert callable(c.export_family)
        assert callable(c.export_self)
