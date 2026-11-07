"""`app.effective_meals(p_from, p_to)` (migrazione 0009, SL-06a): 05-data §7.1, ADR-0007, FR-036.

I pasti esistenti di una famiglia in un intervallo:
- giorni <= `frozen_through`: solo le righe `meal` con `presence = 'added'`;
- giorni successivi: `presence = 'added'`, oppure `meal_slot = 0` con `presence = 'inherit'` (o
  nessuna riga) e il tipo in `family_default_meal`; le occorrenze con `meal_slot > 0` esistono
  solo come righe `added`;
- una riga `removed` non conta mai, e la funzione non guarda voci né ospiti.
È `LANGUAGE sql`, `STABLE`, `SECURITY INVOKER` (inlinabile, 05-data §11.1): lavora nel contesto di
famiglia e sotto RLS.
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import psycopg
import pytest

from support.dishes import World
from support.inventory import APP_ROLE, app_functions
from support.meals import add_item, make_meal, set_defaults, set_frozen_through
from support.owner import Owner

Connect = Callable[..., psycopg.Connection]
FROZEN = date(2026, 10, 22)
D1 = date(2026, 10, 23)  # primo giorno non congelato
D2 = date(2026, 10, 24)


def effective(
    connect_app: Connect, world: World, start: date, end: date, *, which: str = "alfa"
) -> set[tuple[date, str, int]]:
    fam = world.fam(which)
    with connect_app(APP_ROLE, autocommit=False) as conn:
        conn.execute("select set_config('app.family_id', %s, true)", (str(fam.id),))
        rows = conn.execute(
            "select meal_date, meal_type, meal_slot from app.effective_meals(%s, %s)",
            (start, end),
        ).fetchall()
    assert len(rows) == len(set(rows)), "nessun pasto duplicato"
    return {(r[0], r[1], r[2]) for r in rows}


@pytest.fixture
def setup(world: World, owner: Owner) -> World:
    set_defaults(owner, world.alfa, ("lunch", "dinner"))
    set_defaults(owner, world.beta, ("breakfast", "snack"))
    for fam in (world.alfa, world.beta):
        set_frozen_through(owner, fam, FROZEN)
    return world


# --- struttura ------------------------------------------------------------------------------------


@pytest.mark.sqlfunc("effective_meals")
def test_effective_meals_is_a_stable_security_invoker_sql_function(
    catalog: psycopg.Connection,
) -> None:
    by_name = {f["name"]: f for f in app_functions(catalog)}
    assert "effective_meals" in by_name, "funzione app.effective_meals assente (migrazione 0009)"
    function = by_name["effective_meals"]
    assert function["language"] == "sql"
    assert function["volatility"] == "s"
    assert function["secdef"] is False
    assert function["owner"] == "menu_owner"


@pytest.mark.sqlfunc("effective_meals")
def test_effective_meals_signature_and_result_columns(catalog: psycopg.Connection) -> None:
    row = catalog.execute(
        "select pg_get_function_arguments(p.oid), pg_get_function_result(p.oid), p.proretset "
        "from pg_proc p where p.pronamespace = 'app'::regnamespace "
        "and p.proname = 'effective_meals'"
    ).fetchone()
    assert row is not None, "funzione app.effective_meals assente (migrazione 0009)"
    args, result, is_set = row
    assert args.replace(" ", "") == "p_fromdate,p_todate"
    assert is_set is True
    flat = result.replace(" ", "")
    assert "meal_datedate" in flat
    assert "meal_typetext" in flat
    assert "meal_slotsmallint" in flat


@pytest.mark.sqlfunc("effective_meals")
def test_effective_meals_is_executable_by_the_application_role_only_in_the_family_context(
    catalog: psycopg.Connection,
) -> None:
    got = catalog.execute(
        "select has_function_privilege('menu_app', 'app.effective_meals(date, date)', 'EXECUTE'), "
        "has_function_privilege('menu_console', 'app.effective_meals(date, date)', 'EXECUTE')"
    ).fetchone()
    assert got is not None
    assert got[0] is True
    assert got[1] is False, "menu_console non legge dati di famiglia (SR-040)"


# --- giorni successivi al congelamento ------------------------------------------------------------


@pytest.mark.sqlfunc("effective_meals")
def test_without_rows_the_default_types_exist_in_slot_zero(
    connect_app: Connect, setup: World
) -> None:
    assert effective(connect_app, setup, D1, D1) == {(D1, "lunch", 0), (D1, "dinner", 0)}


@pytest.mark.sqlfunc("effective_meals")
def test_a_range_covers_every_day_inclusive(connect_app: Connect, setup: World) -> None:
    got = effective(connect_app, setup, D1, D1 + timedelta(days=6))
    assert {d for d, _, _ in got} == {D1 + timedelta(days=n) for n in range(7)}
    assert len(got) == 14


@pytest.mark.sqlfunc("effective_meals")
def test_an_empty_or_reversed_range_returns_nothing_and_never_fails(
    connect_app: Connect, setup: World
) -> None:
    assert effective(connect_app, setup, D2, D1) == set()


@pytest.mark.sqlfunc("effective_meals")
def test_a_family_without_default_meals_has_only_the_added_rows(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    set_defaults(owner, setup.alfa, ())
    assert effective(connect_app, setup, D1, D2) == set()
    make_meal(owner, setup.alfa, D2, "dinner", presence="added")
    assert effective(connect_app, setup, D1, D2) == {(D2, "dinner", 0)}


@pytest.mark.sqlfunc("effective_meals")
def test_an_added_row_of_a_non_default_type_exists(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.alfa, D2, "snack", presence="added")
    assert (D2, "snack", 0) in effective(connect_app, setup, D2, D2)


@pytest.mark.sqlfunc("effective_meals")
def test_a_removed_row_hides_a_default_meal_only_on_that_day(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.alfa, D2, "dinner", presence="removed")
    got = effective(connect_app, setup, D1, D2)
    assert (D2, "dinner", 0) not in got
    assert (D1, "dinner", 0) in got
    assert (D2, "lunch", 0) in got


@pytest.mark.sqlfunc("effective_meals")
def test_an_inherit_row_follows_the_defaults(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.alfa, D2, "lunch", presence="inherit")  # di default: esiste
    make_meal(owner, setup.alfa, D2, "snack", presence="inherit")  # non di default: nascosta
    got = effective(connect_app, setup, D2, D2)
    assert (D2, "lunch", 0) in got
    assert (D2, "snack", 0) not in got


@pytest.mark.sqlfunc("effective_meals")
def test_content_and_guests_do_not_decide_whether_a_meal_exists(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    """La funzione è una regola pura sui default e su `presence` (05-data §7.1)."""
    make_meal(owner, setup.alfa, D2, "snack", presence="inherit", guests=3, special="away")
    add_item(owner, setup.alfa, D2, "snack", text="Biscotti")
    assert (D2, "snack", 0) not in effective(connect_app, setup, D2, D2)


@pytest.mark.sqlfunc("effective_meals")
def test_other_meals_with_slot_above_zero_exist_only_as_added_rows(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    set_defaults(owner, setup.alfa, ("lunch", "other"))
    make_meal(owner, setup.alfa, D2, "other", 1, presence="added", name="Dopocena")
    make_meal(owner, setup.alfa, D2, "other", 2, presence="removed", name="Tolto")
    got = effective(connect_app, setup, D2, D2)
    assert (D2, "other", 0) in got, "lo slot 0 di «other» segue i default"
    assert (D2, "other", 1) in got
    assert (D2, "other", 2) not in got
    assert not {s for _, t, s in got if t == "other"} - {0, 1}


# --- giorni congelati -----------------------------------------------------------------------------


@pytest.mark.sqlfunc("effective_meals")
def test_frozen_days_have_only_the_added_rows_not_the_defaults(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.alfa, FROZEN, "lunch", presence="added")
    make_meal(owner, setup.alfa, FROZEN, "dinner", presence="removed")
    make_meal(owner, setup.alfa, FROZEN, "snack", presence="added")
    got = effective(connect_app, setup, FROZEN - timedelta(days=1), FROZEN)
    assert got == {(FROZEN, "lunch", 0), (FROZEN, "snack", 0)}


@pytest.mark.sqlfunc("effective_meals")
def test_an_inherit_row_on_a_frozen_day_does_not_count(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.alfa, FROZEN, "lunch", presence="inherit")
    assert effective(connect_app, setup, FROZEN, FROZEN) == set()


@pytest.mark.sqlfunc("effective_meals")
def test_the_boundary_is_exactly_frozen_through(connect_app: Connect, setup: World) -> None:
    got = effective(connect_app, setup, FROZEN, D1)
    assert {d for d, _, _ in got} == {D1}, "frozen_through è congelato, il giorno dopo no"


@pytest.mark.sqlfunc("effective_meals")
def test_a_range_across_the_freeze_boundary_mixes_both_rules(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.alfa, FROZEN, "dinner", presence="added")
    got = effective(connect_app, setup, FROZEN, D1)
    assert got == {(FROZEN, "dinner", 0), (D1, "lunch", 0), (D1, "dinner", 0)}


@pytest.mark.sqlfunc("effective_meals")
def test_changing_the_defaults_does_not_alter_the_frozen_past(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.alfa, FROZEN, "lunch", presence="added")
    set_defaults(owner, setup.alfa, ("breakfast",))
    assert effective(connect_app, setup, FROZEN, FROZEN) == {(FROZEN, "lunch", 0)}
    assert effective(connect_app, setup, D1, D1) == {(D1, "breakfast", 0)}


# --- famiglia e RLS -------------------------------------------------------------------------------


@pytest.mark.sqlfunc("effective_meals")
def test_each_family_sees_only_its_own_defaults_and_rows(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.beta, D2, "dinner", presence="added")
    assert effective(connect_app, setup, D1, D2, which="alfa") == {
        (D1, "lunch", 0),
        (D1, "dinner", 0),
        (D2, "lunch", 0),
        (D2, "dinner", 0),
    }
    beta = effective(connect_app, setup, D2, D2, which="beta")
    assert beta == {(D2, "breakfast", 0), (D2, "snack", 0), (D2, "dinner", 0)}


@pytest.mark.sqlfunc("effective_meals")
def test_without_a_family_context_nothing_is_returned(
    connect_app: Connect, setup: World, owner: Owner
) -> None:
    make_meal(owner, setup.alfa, D2, "snack", presence="added")
    with connect_app(APP_ROLE, autocommit=False) as conn:
        rows: list[Any] = conn.execute(
            "select * from app.effective_meals(%s, %s)", (D1, D2)
        ).fetchall()
    assert rows == []


@pytest.mark.sqlfunc("effective_meals")
def test_sixty_two_days_come_back_in_one_call(connect_app: Connect, setup: World) -> None:
    got = effective(connect_app, setup, D1, D1 + timedelta(days=61))
    assert len(got) == 62 * 2


@pytest.mark.sqlfunc("effective_meals")
def test_the_function_is_used_inline_in_a_from_clause(connect_app: Connect, setup: World) -> None:
    """05-data §11.1: inlinata quando compare in FROM (niente `Function Scan` opaco)."""
    with connect_app(APP_ROLE, autocommit=False) as conn:
        conn.execute("select set_config('app.family_id', %s, true)", (str(setup.alfa.id),))
        plan = "\n".join(
            r[0]
            for r in conn.execute(
                "explain select * from app.effective_meals(%s, %s)", (D1, D2)
            ).fetchall()
        )
    assert "Function Scan on effective_meals" not in plan, plan
