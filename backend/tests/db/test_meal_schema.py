"""Tabelle `meal` e `meal_item` (migrazione 0009, SL-06a): 05-data §4.2, §5, §6.1, §3.2.

AC-052.7 (due «Altro pasto» nello stesso giorno: test di schema della prima slice), AC-008.9 (al
massimo 10 voci nel database), AC-007.6 (la FK `NO ACTION` da `meal_item` rifiuta l'eliminazione
di un piatto assegnato, anche in corsa), SR-008/SR-041 (le FK composite impediscono un
riferimento a un'altra famiglia), SR-060 (limiti nel database), AC-033.3 (una portata in uso non
si elimina). Gli isolamenti tra famiglie, l'RLS e i privilegi generici sono negli inventari
(`test_inventory_rls`, `test_console_privileges`), aggiornati allo stato finale di SL-06a.
"""

from datetime import date
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg import errors

from support.dishes import World, make_dish
from support.meals import add_item, make_meal
from support.owner import Owner

DAY = date(2026, 10, 24)

MEAL_COLUMNS = {
    "family_id": ("uuid", "NO"),
    "meal_date": ("date", "NO"),
    "meal_type": ("text", "NO"),
    "meal_slot": ("smallint", "NO"),
    "name": ("text", "YES"),
    "presence": ("text", "NO"),
    "special_kind": ("text", "YES"),
    "content_version": ("integer", "NO"),
    "content_modified_by": ("uuid", "YES"),
    "content_modified_at": ("timestamp with time zone", "YES"),
    "guests_count": ("smallint", "NO"),
    "guests_note": ("character varying", "YES"),
    "guests_version": ("integer", "NO"),
    "guests_modified_by": ("uuid", "YES"),
    "guests_modified_at": ("timestamp with time zone", "YES"),
}
ITEM_COLUMNS = {
    "id": ("uuid", "NO"),
    "family_id": ("uuid", "NO"),
    "meal_date": ("date", "NO"),
    "meal_type": ("text", "NO"),
    "meal_slot": ("smallint", "NO"),
    "position": ("smallint", "NO"),
    "kind": ("text", "NO"),
    "dish_id": ("uuid", "YES"),
    "course_id": ("uuid", "YES"),
    "free_text": ("character varying", "YES"),
    "not_cooked": ("boolean", "NO"),
}


def _columns(catalog: psycopg.Connection, table: str) -> dict[str, tuple[Any, ...]]:
    rows = catalog.execute(
        "select column_name, data_type, is_nullable, character_maximum_length, column_default "
        "from information_schema.columns where table_schema = 'app' and table_name = %s",
        (table,),
    ).fetchall()
    return {r[0]: r[1:] for r in rows}


def _meal(owner: Owner, world: World, **cols: Any) -> None:
    values: dict[str, Any] = {
        "family_id": world.alfa.id,
        "meal_date": DAY,
        "meal_type": "lunch",
        "meal_slot": 0,
        "presence": "added",
    }
    values.update(cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.meal ({names}) values ({marks})", tuple(values.values()))  # noqa: S608  (colonne scelte dal test)


def _item(owner: Owner, world: World, **cols: Any) -> None:
    values: dict[str, Any] = {
        "family_id": world.alfa.id,
        "meal_date": DAY,
        "meal_type": "lunch",
        "meal_slot": 0,
        "position": 0,
        "kind": "free_text",
        "free_text": "Riso in bianco",
    }
    values.update(cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.meal_item ({names}) values ({marks})", tuple(values.values()))  # noqa: S608  (colonne scelte dal test)


def _dish_item(dish: UUID, course: UUID) -> dict[str, Any]:
    return {"kind": "dish", "dish_id": dish, "course_id": course, "free_text": None}


# --- struttura ------------------------------------------------------------------------------------


def test_meal_has_exactly_the_documented_columns(catalog: psycopg.Connection) -> None:
    cols = _columns(catalog, "meal")
    assert cols, "tabella app.meal assente (migrazione 0009)"
    assert {k: v[:2] for k, v in cols.items()} == MEAL_COLUMNS
    assert cols["guests_note"][2] == 200
    assert cols["meal_slot"][3] == "0"
    assert cols["presence"][3] == "'inherit'::text"
    assert cols["content_version"][3] == "0"
    assert cols["guests_version"][3] == "0"
    assert cols["guests_count"][3] == "0"


def test_meal_item_has_exactly_the_documented_columns(catalog: psycopg.Connection) -> None:
    cols = _columns(catalog, "meal_item")
    assert cols, "tabella app.meal_item assente (migrazione 0009)"
    assert {k: v[:2] for k, v in cols.items()} == ITEM_COLUMNS
    assert cols["free_text"][2] == 200
    assert "gen_random_uuid" in cols["id"][3]
    assert cols["not_cooked"][3] == "false"


def test_meal_and_meal_item_keys(catalog: psycopg.Connection) -> None:
    keys = catalog.execute(
        "select conrelid::regclass::text, contype, pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid in ('app.meal'::regclass, 'app.meal_item'::regclass) "
        "and contype in ('p', 'u')"
    ).fetchall()
    assert (
        "app.meal",
        "p",
        "PRIMARY KEY (family_id, meal_date, meal_type, meal_slot)",
    ) in keys
    assert ("app.meal_item", "p", "PRIMARY KEY (id)") in keys
    assert any(t == "app.meal_item" and k == "u" and "(family_id, id)" in d for t, k, d in keys)
    assert any(
        t == "app.meal_item"
        and k == "u"
        and "position" in d
        and "family_id, meal_date, meal_type, meal_slot" in d
        for t, k, d in keys
    ), keys


def test_the_item_position_uniqueness_is_deferrable_initially_immediate(
    catalog: psycopg.Connection,
) -> None:
    row = catalog.execute(
        "select condeferrable, condeferred from pg_constraint where conrelid = "
        "'app.meal_item'::regclass and contype = 'u' and pg_get_constraintdef(oid) like "
        "'%position%'"
    ).fetchone()
    assert row == (True, False), "05-data §4.2: DEFERRABLE INITIALLY IMMEDIATE"


def test_the_dish_index_for_last_cooked_exists_and_is_partial(catalog: psycopg.Connection) -> None:
    """05-data §5: «ultima volta cucinato», ordinamento per «non cucinato da più tempo»."""
    defs: dict[str, str] = dict(
        catalog.execute(
            "select indexname, indexdef from pg_indexes where schemaname = 'app' "
            "and tablename = 'meal_item'"
        ).fetchall()
    )
    flat = defs.get("ix_meal_item_dish", "").replace(" ", "")
    assert "(family_id,dish_id,meal_date)" in flat, defs
    assert "WHERE(kind='dish'::text)" in flat, defs


def test_foreign_keys_follow_the_on_delete_rule(catalog: psycopg.Connection) -> None:
    """05-data §4 «Regola ON DELETE»: FK diretta verso la famiglia anche sulle parti."""
    fks = {
        (r[0], r[1])
        for r in catalog.execute(
            "select conrelid::regclass::text, pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid in ('app.meal'::regclass, 'app.meal_item'::regclass) and contype = 'f'"
        ).fetchall()
    }
    flat = {(t, d.replace("\n", " ")) for t, d in fks}
    assert (
        "app.meal",
        "FOREIGN KEY (family_id) REFERENCES app.family(id) ON DELETE CASCADE",
    ) in flat
    assert (
        "app.meal_item",
        "FOREIGN KEY (family_id) REFERENCES app.family(id) ON DELETE CASCADE",
    ) in flat
    texts = [d for t, d in flat if t == "app.meal_item"]
    assert any(
        "REFERENCES app.meal(family_id, meal_date, meal_type, meal_slot) ON DELETE CASCADE" in d
        for d in texts
    ), texts
    assert any("REFERENCES app.dish(family_id, id)" in d and "CASCADE" not in d for d in texts)
    assert any("REFERENCES app.course(family_id, id)" in d and "CASCADE" not in d for d in texts)
    persons = [d for t, d in flat if t == "app.meal" and "app.person" in d]
    assert persons, "content_modified_by / guests_modified_by puntano a person"
    assert all("CASCADE" not in d for d in persons)


# --- AC-052.7: vincoli di dominio di `meal` ------------------------------------------------------


def test_ac_052_7_two_other_meals_of_the_same_day_are_accepted(owner: Owner, world: World) -> None:
    _meal(owner, world, meal_type="other", meal_slot=0, name="Aperitivo")
    _meal(owner, world, meal_type="other", meal_slot=1, name="Dopocena")
    assert (
        owner.scalar(
            "select count(*) from app.meal where meal_type = 'other' and meal_date = %s", (DAY,)
        )
        == 2
    )


def test_five_other_meals_fit_in_a_day_and_the_sixth_slot_does_not(
    owner: Owner, world: World
) -> None:
    """ASM-068: al massimo 5 attivi, garantiti dal CHECK perché le righe rimosse si riusano."""
    for slot in range(5):
        _meal(owner, world, meal_type="other", meal_slot=slot)
    with pytest.raises(errors.CheckViolation):
        _meal(owner, world, meal_type="other", meal_slot=5)


def test_the_same_meal_key_twice_is_a_primary_key_violation(owner: Owner, world: World) -> None:
    _meal(owner, world)
    with pytest.raises(errors.UniqueViolation):
        _meal(owner, world)


def test_the_same_key_is_allowed_in_another_family(owner: Owner, world: World) -> None:
    _meal(owner, world)
    _meal(owner, world, family_id=world.beta.id)
    assert owner.scalar("select count(*) from app.meal") == 2


@pytest.mark.parametrize(
    "override",
    [
        {"meal_type": "brunch"},
        {"meal_type": "LUNCH"},
        {"meal_type": "lunch", "meal_slot": 1},
        {"meal_type": "breakfast", "meal_slot": 4},
        {"meal_type": "other", "meal_slot": 5},
        {"meal_type": "other", "meal_slot": -1},
        {"presence": "gone"},
        {"presence": ""},
        {
            "meal_type": "other",
            "meal_slot": 1,
            "presence": "inherit",
        },  # slot > 0 solo `added`/`removed`
        {"special_kind": "holiday"},
        {"content_version": -1},
        {"guests_version": -1},
        {"guests_count": -1},
        {"guests_count": 51},
        {"name": "Aperitivo"},  # nome solo per `other`
        {"meal_type": "dinner", "name": "Cena"},
        {"meal_type": "other", "name": ""},
        {"meal_type": "other", "name": "   "},
        {"meal_type": "other", "name": "x" * 41},
    ],
)
def test_meal_check_constraints_refuse_malformed_rows(
    owner: Owner, world: World, override: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation):
        _meal(owner, world, **override)


@pytest.mark.parametrize(
    "override",
    [
        {"meal_type": "other", "meal_slot": 0, "name": "x"},
        {"meal_type": "other", "meal_slot": 4, "name": "x" * 40},
        {"meal_type": "other", "meal_slot": 0, "name": None},
        {"presence": "inherit"},
        {"presence": "removed"},
        {"special_kind": "away"},
        {"special_kind": "restaurant"},
        {"special_kind": "skipped"},
        {"guests_count": 0},
        {"guests_count": 50},
        {"content_version": 0},
        {"content_version": 2147483647},
    ],
)
def test_meal_check_constraints_accept_the_documented_variants(
    owner: Owner, world: World, override: dict[str, Any]
) -> None:
    _meal(owner, world, **override)
    assert owner.scalar("select count(*) from app.meal") == 1


def test_guests_note_longer_than_200_characters_is_refused(owner: Owner, world: World) -> None:
    _meal(owner, world, guests_note="x" * 200)
    with pytest.raises(errors.StringDataRightTruncation):
        _meal(owner, world, meal_type="dinner", guests_note="x" * 201)


# --- `meal_item`: forma, limite di 10 voci, riordino ---------------------------------------------


def test_an_item_needs_its_meal(owner: Owner, world: World) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        _item(owner, world)
    _meal(owner, world)
    _item(owner, world)


def test_ac_008_9_at_most_ten_items_per_meal_in_the_database(owner: Owner, world: World) -> None:
    _meal(owner, world)
    for position in range(10):
        _item(owner, world, position=position, free_text=f"voce {position}")
    with pytest.raises(errors.CheckViolation):
        _item(owner, world, position=10)
    with pytest.raises(errors.CheckViolation):
        _item(owner, world, position=-1)
    with pytest.raises(errors.UniqueViolation):
        _item(owner, world, position=3)
    assert owner.scalar("select count(*) from app.meal_item") == 10


def test_the_ten_item_limit_is_per_meal_not_per_day(owner: Owner, world: World) -> None:
    _meal(owner, world)
    _meal(owner, world, meal_type="dinner")
    for position in range(10):
        _item(owner, world, position=position)
        _item(owner, world, meal_type="dinner", position=position)
    assert owner.scalar("select count(*) from app.meal_item") == 20


def test_items_can_be_reordered_in_a_transaction_with_deferred_constraints(
    owner: Owner, world: World
) -> None:
    _meal(owner, world)
    _item(owner, world, position=0, free_text="prima")
    _item(owner, world, position=1, free_text="seconda")
    with pytest.raises(errors.UniqueViolation):  # senza rinvio: la prima mossa urta la seconda
        owner.execute("update app.meal_item set position = 1 where position = 0")
    owner.script(
        "begin; set constraints all deferred; "
        "update app.meal_item set position = 1 - position; commit"
    )
    assert owner.rows("select free_text from app.meal_item order by position") == [
        ("seconda",),
        ("prima",),
    ]


def test_ck_shape_dish_item_needs_dish_and_course_and_no_text(owner: Owner, world: World) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    _meal(owner, world)
    course = world.alfa.courses["first"]
    ok: dict[str, Any] = {"kind": "dish", "dish_id": dish, "course_id": course, "free_text": None}
    _item(owner, world, position=0, **ok)
    bad: list[dict[str, Any]] = [
        {"dish_id": None},
        {"course_id": None},
        {"free_text": "anche testo"},
    ]
    for n, over in enumerate(bad, start=1):
        with pytest.raises(errors.CheckViolation):
            _item(owner, world, position=n, **(ok | over))


def test_ck_shape_free_text_item_has_text_and_no_dish_course_or_not_cooked(
    owner: Owner, world: World
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    _meal(owner, world)
    cases: list[dict[str, Any]] = [
        {"free_text": None},
        {"dish_id": dish},
        {"course_id": world.alfa.courses["first"]},
        {"not_cooked": True},
        {"free_text": ""},
        {"kind": "other"},
    ]
    for position, over in enumerate(cases):
        with pytest.raises((errors.CheckViolation, errors.ForeignKeyViolation)):
            _item(owner, world, position=position, **over)
    _item(owner, world, position=9, free_text="x" * 200)
    with pytest.raises((errors.CheckViolation, errors.StringDataRightTruncation)):
        _item(owner, world, position=8, free_text="x" * 201)


def test_a_dish_item_may_be_marked_not_cooked(owner: Owner, world: World) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    _meal(owner, world)
    add_item(owner, world.alfa, DAY, "lunch", dish=dish, not_cooked=True)
    assert owner.scalar("select not_cooked from app.meal_item") is True


# --- chiavi esterne: un riferimento a un'altra famiglia non esiste (SR-008, SR-041) -------------


def test_an_item_cannot_reference_a_dish_or_a_course_of_another_family(
    owner: Owner, world: World
) -> None:
    foreign_dish = make_dish(owner, world.beta, "CANARY-BETA-DISH")
    _meal(owner, world)
    with pytest.raises(errors.ForeignKeyViolation):
        _item(owner, world, **_dish_item(foreign_dish, world.alfa.courses["first"]))
    own_dish = make_dish(owner, world.alfa, "Pasta e ceci")
    with pytest.raises(errors.ForeignKeyViolation):
        _item(owner, world, **_dish_item(own_dish, world.beta.courses["first"]))
    assert owner.scalar("select count(*) from app.meal_item") == 0


def test_a_meal_cannot_point_to_a_person_of_another_family(owner: Owner, world: World) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        _meal(owner, world, content_modified_by=world.beta.who("planner").person)
    _meal(owner, world, content_modified_by=world.alfa.who("planner").person)


def test_ac_007_6_a_dish_in_a_meal_cannot_be_deleted_even_by_the_owner(
    owner: Owner, world: World
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    _meal(owner, world)
    add_item(owner, world.alfa, DAY, "lunch", dish=dish)
    with pytest.raises(errors.ForeignKeyViolation):
        owner.execute("delete from app.dish where id = %s", (dish,))
    assert owner.scalar("select count(*) from app.dish where id = %s", (dish,)) == 1


def test_ac_033_3_a_course_used_by_a_meal_item_cannot_be_deleted(
    owner: Owner, world: World
) -> None:
    dish = make_dish(owner, world.alfa, "Pasta e ceci", courses=("first", "second"))
    _meal(owner, world)
    add_item(owner, world.alfa, DAY, "lunch", dish=dish, course="second")
    with pytest.raises(errors.ForeignKeyViolation):
        owner.execute("delete from app.course where id = %s", (world.alfa.courses["second"],))


def test_the_course_of_an_item_is_not_a_foreign_key_to_dish_course(
    owner: Owner, world: World
) -> None:
    """05-data §4.2: togliere una portata a un piatto non altera i pasti passati."""
    dish = make_dish(owner, world.alfa, "Pasta e ceci", courses=("first", "second"))
    _meal(owner, world)
    add_item(owner, world.alfa, DAY, "lunch", dish=dish, course="second")
    owner.execute(
        "delete from app.dish_course where dish_id = %s and course_id = %s",
        (dish, world.alfa.courses["second"]),
    )
    assert owner.scalar("select count(*) from app.meal_item") == 1


def test_deleting_a_meal_deletes_its_items(owner: Owner, world: World) -> None:
    _meal(owner, world)
    _item(owner, world)
    owner.execute("delete from app.meal")
    assert owner.scalar("select count(*) from app.meal_item") == 0


def test_deleting_the_family_removes_meals_and_items_even_with_dishes_and_courses(
    owner: Owner, world: World
) -> None:
    """La FK diretta verso la famiglia anche sulle parti (05-data §4, SL-04): nessuna
    `foreign_key_violation` per l'ordine delle cascate."""
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    _meal(owner, world)
    add_item(owner, world.alfa, DAY, "lunch", dish=dish)
    _item(owner, world, position=1)
    _meal(owner, world, family_id=world.beta.id)
    owner.execute("delete from app.family where id = %s", (world.alfa.id,))
    assert owner.rows("select distinct family_id from app.meal") == [(world.beta.id,)]
    assert owner.scalar("select count(*) from app.meal_item") == 0


# --- RLS e privilegi (sintesi; i controlli generici sono negli inventari) ------------------------


@pytest.mark.parametrize("table", ["meal", "meal_item"])
def test_policies_and_privileges_of_the_planning_tables(
    table: str, catalog: psycopg.Connection
) -> None:
    assert catalog.execute("select to_regclass(%s)", (f"app.{table}",)).fetchone() != (None,), (
        f"tabella app.{table} assente (migrazione 0009)"
    )
    policies = {
        r[0]
        for r in catalog.execute(
            "select polname from pg_policy where polrelid = %s::regclass", (f"app.{table}",)
        ).fetchall()
    }
    assert policies == {"p_family", "p_owner", "p_backup"}
    forced = catalog.execute(
        "select relrowsecurity, relforcerowsecurity from pg_class where oid = %s::regclass",
        (f"app.{table}",),
    ).fetchone()
    assert forced == (True, True)
    for role, privilege, expected in (
        ("menu_app", "SELECT", True),
        ("menu_app", "INSERT", True),
        ("menu_app", "UPDATE", True),
        ("menu_app", "DELETE", True),
        ("menu_app", "TRUNCATE", False),
        ("menu_backup", "SELECT", True),
        ("menu_backup", "INSERT", False),
        ("menu_console", "SELECT", False),
        ("menu_console", "INSERT", False),
    ):
        got = catalog.execute(
            "select has_table_privilege(%s, %s::regclass, %s)", (role, f"app.{table}", privilege)
        ).fetchone()
        assert got == (expected,), (table, role, privilege)


def test_migration_defaults_use_no_bare_time_function(catalog: psycopg.Connection) -> None:
    for table in ("meal", "meal_item"):
        for name, (_, _, _, default) in _columns(catalog, table).items():
            assert "now()" not in (default or "").lower(), (table, name)


def test_the_id_of_an_item_is_random_not_sequential(owner: Owner, world: World) -> None:
    _meal(owner, world)
    _item(owner, world, position=0)
    _item(owner, world, position=1)
    ids = [r[0] for r in owner.rows("select id from app.meal_item")]
    assert len(set(ids)) == 2
    assert all(isinstance(i, UUID) and i.version == 4 for i in ids)


def test_make_meal_helper_matches_the_schema(owner: Owner, world: World) -> None:
    make_meal(
        owner, world.alfa, DAY, "other", 3, name="Aperitivo", special="away", guests=2,
        guests_note="Zia", guests_version=1, content_version=2, modified_by="planner",
    )  # fmt: skip
    assert owner.scalar("select count(*) from app.meal") == 1
