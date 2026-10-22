"""Inventario RLS e test d'isolamento generico (05-data §6.3-6.4, 08 §6.4; THR-026, THR-048).

SL-02 (prima RLS su tabelle reali): `family`, `family_default_meal`, `person`,
`family_bootstrap`, `course`. L'inventario e il test generico girano su di esse, e la loro
capacità di fallire resta provata con tabelle sintetiche (create e distrutte dal test).
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

import psycopg
import pytest

from support.inventory import (
    EXPECTED_FAMILY_TABLES_NOW,
    EXPECTED_TABLES_NOW,
    FamilyTableSpec,
    app_tables,
    family_isolation_problems,
    family_tables,
    rls_problems,
)
from support.owner import Owner

ProbeFactory = Callable[..., tuple[str, FamilyTableSpec]]


def test_schema_app_exists_and_only_expected_tables_exist(catalog: psycopg.Connection) -> None:
    assert set(app_tables(catalog)) == set(EXPECTED_TABLES_NOW)


def test_family_tables_of_sl_02_exist_and_rls_inventory_is_clean(
    catalog: psycopg.Connection,
) -> None:
    """SR-042, THR-026: tutte le tabelle nuove hanno RLS abilitata e forzata, p_family
    (con WITH CHECK), p_owner e p_backup; nessuna tabella è non classificata."""
    assert set(family_tables(catalog)) == set(EXPECTED_FAMILY_TABLES_NOW)
    assert rls_problems(catalog) == []


def test_family_table_policies_filter_on_the_right_column(catalog: psycopg.Connection) -> None:
    """`family` filtra su `id`, le altre su `family_id` (05-data §4.2): una policy sulla
    colonna sbagliata passerebbe l'ispezione generica ma non isolerebbe nulla."""
    tables = app_tables(catalog)
    assert tables["family"]["policies"]["p_family"]["using"].replace(" ", "").startswith("(id=")
    for name in sorted(EXPECTED_FAMILY_TABLES_NOW - {"family"}):
        using = tables[name]["policies"]["p_family"]["using"].replace(" ", "")
        assert "family_id=app.current_family_id()" in using, (name, using)


def test_alembic_version_lives_in_schema_app(catalog: psycopg.Connection) -> None:
    assert "alembic_version" in app_tables(catalog)


# --- l'inventario sa fallire (THR-026: errori nelle policy) -----------------------------------


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"rls": False, "force": False}, "RLS non abilitata e forzata"),
        ({"force": False}, "RLS non abilitata e forzata"),
        ({"p_owner": False}, "policy p_owner assente"),
        ({"p_backup": False}, "policy p_backup assente"),
        ({"policy_check": None}, "senza WITH CHECK"),
        ({"policy_using": "true", "policy_check": "true"}, "non filtra per famiglia"),
    ],
)
def test_rls_inventory_flags_each_policy_mistake(
    make_probe_table: ProbeFactory,
    catalog: psycopg.Connection,
    kwargs: dict[str, Any],
    expected: str,
) -> None:
    table, _ = make_probe_table(**kwargs)
    problems = rls_problems(catalog)
    assert any(p.startswith(f"{table}:") and expected in p for p in problems), problems


def test_rls_inventory_accepts_a_correct_family_table(
    make_probe_table: ProbeFactory, catalog: psycopg.Connection
) -> None:
    table, _ = make_probe_table()
    assert table in family_tables(catalog)
    assert rls_problems(catalog) == []


def test_rls_inventory_flags_an_unclassified_table(
    make_probe_table: ProbeFactory, catalog: psycopg.Connection
) -> None:
    table, _ = make_probe_table(family_column=False, rls=False, force=False, p_owner=False,
                                p_backup=False)  # fmt: skip
    assert f"{table}: tabella non classificata (né di famiglia né in §6.3)" in rls_problems(catalog)


# --- test d'isolamento generico (08 §6.4) -------------------------------------------------------


def test_generic_isolation_runs_over_every_family_table(
    catalog: psycopg.Connection,
) -> None:
    """Per ogni tabella con `family_id` (e per `family`) esiste una spec in `FAMILY_TABLE_SPECS`."""
    from support.family_specs import FAMILY_TABLE_SPECS

    assert sorted(FAMILY_TABLE_SPECS) == family_tables(catalog)


def test_generic_isolation_passes_for_a_correct_table(
    make_probe_table: ProbeFactory,
    owner: Owner,
    connect_app: Callable[..., psycopg.Connection],
    two_families: tuple[UUID, UUID],
) -> None:
    table, spec = make_probe_table()
    assert family_isolation_problems(table, spec, owner, *two_families, connect_app) == []


def test_generic_isolation_catches_a_permissive_policy(
    make_probe_table: ProbeFactory,
    owner: Owner,
    connect_app: Callable[..., psycopg.Connection],
    two_families: tuple[UUID, UUID],
) -> None:
    table, spec = make_probe_table(policy_using="true", policy_check="true")
    problems = family_isolation_problems(table, spec, owner, *two_families, connect_app)
    assert any("senza contesto legge" in p for p in problems)
    assert any("legge righe di B" in p for p in problems)
    assert any("INSERT con family_id di B accettato" in p for p in problems)


def test_for_all_policy_without_with_check_reuses_using_as_the_check(
    make_probe_table: ProbeFactory,
    owner: Owner,
    connect_app: Callable[..., psycopg.Connection],
    two_families: tuple[UUID, UUID],
) -> None:
    """Comportamento reale di PostgreSQL: `FOR ALL` con solo USING riusa USING come CHECK,
    quindi l'isolamento regge (l'ispezione `senza WITH CHECK` lo vieta comunque)."""
    table, spec = make_probe_table(policy_check=None)
    assert family_isolation_problems(table, spec, owner, *two_families, connect_app) == []


def test_generic_isolation_catches_a_permissive_with_check(
    make_probe_table: ProbeFactory,
    owner: Owner,
    connect_app: Callable[..., psycopg.Connection],
    two_families: tuple[UUID, UUID],
) -> None:
    """USING corretto ma WITH CHECK (true): si può scrivere in un'altra famiglia."""
    table, spec = make_probe_table(policy_check="true")
    problems = family_isolation_problems(table, spec, owner, *two_families, connect_app)
    assert any("INSERT con family_id di B accettato" in p for p in problems), problems


@pytest.mark.parametrize("table", sorted(EXPECTED_FAMILY_TABLES_NOW))
def test_real_family_tables_isolate_families(
    table: str,
    owner: Owner,
    connect_app: Callable[..., psycopg.Connection],
    two_families: tuple[UUID, UUID],
) -> None:
    """08 §6.4 sulle tabelle reali: senza contesto zero righe, A non vede B, INSERT e UPDATE
    verso B rifiutati, DELETE di righe altrui = 0 (THR-020, THR-026, SR-042)."""
    from support.family_specs import FAMILY_TABLE_SPECS

    spec = FAMILY_TABLE_SPECS[table]
    assert family_isolation_problems(table, spec, owner, *two_families, connect_app) == []
