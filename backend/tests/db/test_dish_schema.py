"""Tabelle `dish`, `dish_course`, `dish_source` (migrazione 0007, SL-04): 05-data §4.2, §6.1, §3.2.

SR-008/SR-041 (le FK composite impediscono un riferimento a un'altra famiglia), SR-024 (CHECK
sugli URL), SR-060 (al massimo 10 fonti nel database), FR-029 (si archivia solo un piatto già
pianificato; `ever_planned` non torna falso), FR-030 (`name_search` minuscolo e senza accenti).
Le colonne M1/M2 (`priority`, `promotion_dismissed_on`, `dish_tag`, `dish_like`) NON esistono.
Gli isolamenti tra famiglie, l'RLS e i privilegi generici sono negli inventari
(`test_inventory_rls`,
`test_console_privileges`), aggiornati allo stato finale di SL-04.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors

from support.dishes import World, bulk_dishes, make_dish
from support.owner import Owner

Connect = Callable[..., psycopg.Connection]

DISH_COLUMNS = {
    "id": ("uuid", "NO"),
    "family_id": ("uuid", "NO"),
    "name": ("character varying", "NO"),
    "name_search": ("text", "NO"),
    "status": ("text", "NO"),
    "notes": ("character varying", "YES"),
    "prep_time": ("text", "YES"),
    "archived_at": ("timestamp with time zone", "YES"),
    "ever_planned": ("boolean", "NO"),
    "created_by": ("uuid", "NO"),
    "created_at": ("timestamp with time zone", "NO"),
    "version": ("integer", "NO"),
    "modified_by": ("uuid", "YES"),
    "modified_at": ("timestamp with time zone", "NO"),
}


def _columns(catalog: psycopg.Connection, table: str) -> dict[str, tuple[Any, ...]]:
    rows = catalog.execute(
        "select column_name, data_type, is_nullable, character_maximum_length, column_default, "
        "is_generated, generation_expression from information_schema.columns "
        "where table_schema = 'app' and table_name = %s",
        (table,),
    ).fetchall()
    return {r[0]: r[1:] for r in rows}


# --- struttura ----------------------------------------------------------------------------------


def test_dish_has_exactly_the_m0_columns(catalog: psycopg.Connection) -> None:
    cols = _columns(catalog, "dish")
    assert cols, "tabella app.dish assente (migrazione 0007)"
    assert set(cols) == set(DISH_COLUMNS), "né priority né promotion_dismissed_on prima di M2"
    for name, (data_type, nullable) in DISH_COLUMNS.items():
        assert cols[name][:2] == (data_type, nullable), name
    assert cols["name"][2] == 120
    assert cols["notes"][2] == 2000
    assert cols["status"][3] == "'to_try'::text"
    assert cols["ever_planned"][3] == "false"
    assert cols["version"][3] == "1"


def test_dish_name_search_is_a_generated_column_over_search_norm(
    catalog: psycopg.Connection,
) -> None:
    cols = _columns(catalog, "dish")
    assert cols["name_search"][4] == "ALWAYS"
    assert "search_norm" in cols["name_search"][5]


def test_dish_defaults_use_now_utc_and_no_bare_time(catalog: psycopg.Connection) -> None:
    cols = _columns(catalog, "dish")
    for name in ("created_at", "modified_at"):
        assert "now_utc" in (cols[name][3] or ""), name


def test_dish_course_and_dish_source_columns(catalog: psycopg.Connection) -> None:
    course = _columns(catalog, "dish_course")
    assert set(course) == {"family_id", "dish_id", "course_id"}, "dish_tag arriva con M2"
    source = _columns(catalog, "dish_source")
    assert set(source) == {
        "id",
        "family_id",
        "dish_id",
        "position",
        "kind",
        "reference",
        "page",
        "note",
    }
    assert source["reference"][2] == 500
    assert source["page"][2] == 20
    assert source["note"][2] == 500
    assert source["position"][0] == "smallint"


def test_m1_and_m2_tables_do_not_exist_yet(catalog: psycopg.Connection) -> None:
    present = {
        r[0]
        for r in catalog.execute(
            "select relname from pg_class where relnamespace = 'app'::regnamespace and relkind='r'"
        ).fetchall()
    }
    assert {"dish", "dish_course", "dish_source"} <= present
    assert not present & {"dish_tag", "dish_like", "tag", "change_event", "meal", "meal_item"}


def test_dish_primary_and_unique_keys(catalog: psycopg.Connection) -> None:
    keys = catalog.execute(
        "select conrelid::regclass::text, contype, pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid in ('app.dish'::regclass, 'app.dish_course'::regclass, "
        "'app.dish_source'::regclass) and contype in ('p', 'u')"
    ).fetchall()
    assert ("app.dish", "p", "PRIMARY KEY (id)") in keys
    assert any(t == "app.dish" and k == "u" and "(family_id, id)" in d for t, k, d in keys)
    assert ("app.dish_course", "p", "PRIMARY KEY (family_id, dish_id, course_id)") in keys
    assert any(
        t == "app.dish_source" and k == "u" and "family_id, dish_id" in d and "position" in d
        for t, k, d in keys
    ), keys


def test_the_source_position_uniqueness_is_deferrable_initially_immediate(
    catalog: psycopg.Connection,
) -> None:
    row = catalog.execute(
        "select condeferrable, condeferred from pg_constraint where conrelid = "
        "'app.dish_source'::regclass and contype = 'u' and pg_get_constraintdef(oid) like "
        "'%position%'"
    ).fetchone()
    assert row == (True, False), "05-data §4.2: DEFERRABLE INITIALLY IMMEDIATE"


# --- vincoli di dominio ---------------------------------------------------------------------------


def _dish(owner: Owner, world: World, **cols: Any) -> UUID:
    dish = uuid4()
    values: dict[str, Any] = {
        "id": dish,
        "family_id": world.alfa.id,
        "name": "Pasta e ceci",
        "created_by": world.alfa.who("planner").person,
    }
    values.update(cols)
    owner.execute(
        f"insert into app.dish ({', '.join(values)}) values ({', '.join(['%s'] * len(values))})",  # noqa: S608
        tuple(values.values()),
    )
    return dish


@pytest.mark.parametrize("name", ["", "x" * 121])
def test_dish_name_length_is_1_to_120(owner: Owner, world: World, name: str) -> None:
    with pytest.raises((errors.CheckViolation, errors.StringDataRightTruncation)):
        _dish(owner, world, name=name)


def test_dish_name_of_120_characters_is_accepted(owner: Owner, world: World) -> None:
    _dish(owner, world, name="x" * 120)


@pytest.mark.parametrize(
    ("column", "bad"),
    [("status", "done"), ("prep_time", "forever"), ("version", 0)],
)
def test_dish_check_constraints(owner: Owner, world: World, column: str, bad: Any) -> None:
    with pytest.raises(errors.CheckViolation):
        _dish(owner, world, **{column: bad})


def test_notes_longer_than_2000_are_refused_by_the_database(owner: Owner, world: World) -> None:
    with pytest.raises(errors.StringDataRightTruncation):
        _dish(owner, world, notes="n" * 2001)
    _dish(owner, world, notes="n" * 2000)


def test_ac_004_name_search_is_lowercase_and_unaccented(owner: Owner, world: World) -> None:
    """FR-030, ASM-047: `name_search = app.search_norm(name)`."""
    dish = _dish(owner, world, name="Purè di PATATE")
    assert (
        owner.scalar("select name_search from app.dish where id = %s", (dish,)) == "pure di patate"
    )


def test_only_a_planned_dish_can_be_archived(owner: Owner, world: World) -> None:
    """FR-029, AC-007.7: `ck_dish_archived_requires_planned`."""
    with pytest.raises(errors.CheckViolation) as raised:
        _dish(owner, world, archived_at="2026-10-01T00:00:00Z", ever_planned=False)
    assert raised.value.diag.constraint_name == "ck_dish_archived_requires_planned"
    _dish(owner, world, archived_at="2026-10-01T00:00:00Z", ever_planned=True)


def test_ever_planned_never_goes_back_to_false(owner: Owner, world: World) -> None:
    """`tg_dish_ever_planned_monotonic` (lettura letterale di FR-029)."""
    dish = _dish(owner, world, ever_planned=True)
    with pytest.raises(psycopg.Error):
        owner.execute("update app.dish set ever_planned = false where id = %s", (dish,))
    never = _dish(owner, world, ever_planned=False)
    owner.execute("update app.dish set ever_planned = true where id = %s", (never,))
    assert owner.scalar("select ever_planned from app.dish where id = %s", (never,)) is True


def test_created_by_must_be_a_person(owner: Owner, world: World) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        _dish(owner, world, created_by=uuid4())


# --- fonti ------------------------------------------------------------------------------------


def _source(owner: Owner, world: World, dish: UUID, position: int = 0, **cols: Any) -> None:
    values: dict[str, Any] = {
        "id": uuid4(),
        "family_id": world.alfa.id,
        "dish_id": dish,
        "position": position,
        "kind": "link",
        "reference": "https://ricette.example.test/frittata",
    }
    values.update(cols)
    owner.execute(
        f"insert into app.dish_source ({', '.join(values)}) "  # noqa: S608
        f"values ({', '.join(['%s'] * len(values))})",
        tuple(values.values()),
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "video"},
        {"position": 10},
        {"position": -1},
        {"reference": "javascript:alert(1)"},
        {"reference": "ftp://x.example.test/a"},
        {"reference": "ricette.example.test"},
        {"kind": "link", "page": "12"},
        {"kind": "other", "reference": "dal nonno", "page": "3"},
    ],
)
def test_dish_source_check_constraints(owner: Owner, world: World, bad: dict[str, Any]) -> None:
    """SR-024: solo http/https per i link; la pagina solo per libro e rivista."""
    dish = make_dish(owner, world.alfa, "Frittata")
    with pytest.raises(errors.CheckViolation):
        _source(owner, world, dish, **bad)


def test_dish_source_accepts_http_https_case_insensitively_and_book_page(
    owner: Owner, world: World
) -> None:
    dish = make_dish(owner, world.alfa, "Frittata")
    _source(owner, world, dish, 0, reference="HTTP://ricette.example.test/a")
    _source(owner, world, dish, 1, kind="book", reference="Il cucchiaio", page="142")
    _source(owner, world, dish, 2, kind="magazine", reference="Rivista", page="9")


def test_a_dish_has_at_most_ten_sources_in_the_database(owner: Owner, world: World) -> None:
    """FR-024, 05-data: posizioni 0-9, UNIQUE (family_id, dish_id, position)."""
    dish = make_dish(owner, world.alfa, "Frittata")
    for position in range(10):
        _source(owner, world, dish, position)
    with pytest.raises(psycopg.Error):
        _source(owner, world, dish, 10)
    with pytest.raises(errors.UniqueViolation):
        _source(owner, world, dish, 3)


def test_source_reference_longer_than_500_is_refused(owner: Owner, world: World) -> None:
    dish = make_dish(owner, world.alfa, "Frittata")
    with pytest.raises(errors.StringDataRightTruncation):
        _source(owner, world, dish, 0, kind="other", reference="r" * 501)


# --- chiavi composite e cascate (SR-041) ----------------------------------------------------------


def test_dish_course_refuses_a_course_of_another_family(owner: Owner, world: World) -> None:
    dish = make_dish(owner, world.alfa, "Frittata")
    with pytest.raises(errors.ForeignKeyViolation):
        owner.execute(
            "insert into app.dish_course (family_id, dish_id, course_id) values (%s, %s, %s)",
            (world.alfa.id, dish, world.beta.courses["first"]),
        )


def test_dish_course_refuses_a_dish_of_another_family(owner: Owner, world: World) -> None:
    dish = make_dish(owner, world.beta, "Lasagne")
    with pytest.raises(errors.ForeignKeyViolation):
        owner.execute(
            "insert into app.dish_course (family_id, dish_id, course_id) values (%s, %s, %s)",
            (world.alfa.id, dish, world.alfa.courses["first"]),
        )


def test_dish_source_refuses_a_dish_of_another_family(owner: Owner, world: World) -> None:
    dish = make_dish(owner, world.beta, "Lasagne")
    with pytest.raises(errors.ForeignKeyViolation):
        _source(owner, world, dish)


def test_dish_created_by_refuses_a_person_of_another_family(owner: Owner, world: World) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        _dish(owner, world, created_by=world.beta.who("planner").person)


def test_deleting_a_dish_removes_its_courses_and_sources(owner: Owner, world: World) -> None:
    dish = make_dish(
        owner,
        world.alfa,
        "Frittata",
        courses=("first", "second"),
        sources=({"kind": "link", "reference": "https://ricette.example.test/a"},),
    )
    owner.execute("delete from app.dish where id = %s", (dish,))
    assert owner.scalar("select count(*) from app.dish_course where dish_id = %s", (dish,)) == 0
    assert owner.scalar("select count(*) from app.dish_source where dish_id = %s", (dish,)) == 0


def test_a_course_in_use_cannot_be_deleted(owner: Owner, world: World) -> None:
    """AC-033.3: `dish_course -> course` è NO ACTION."""
    make_dish(owner, world.alfa, "Frittata", courses=("second",))
    with pytest.raises(errors.ForeignKeyViolation):
        owner.execute("delete from app.course where id = %s", (world.alfa.courses["second"],))


def test_deleting_the_family_cascades_to_dishes(owner: Owner, world: World) -> None:
    """Cascata `family` -> `dish` (SR-018). Le persone non bloccano la cascata."""
    make_dish(owner, world.beta, "Lasagne", courses=("first",))
    owner.execute("delete from app.family where id = %s", (world.beta.id,))
    assert owner.scalar("select count(*) from app.dish where family_id = %s", (world.beta.id,)) == 0


# --- privilegi e indici ---------------------------------------------------------------------------


def _in_family(conn: psycopg.Connection, family: UUID) -> None:
    conn.execute("select set_config('app.family_id', %s, true)", (str(family),))


@pytest.mark.parametrize("table", ["dish", "dish_course", "dish_source"])
def test_menu_app_has_full_dml_on_dish_tables_inside_its_family(
    connect_app: Connect, owner: Owner, world: World, table: str
) -> None:
    """05-data §3.2: tabelle di famiglia SELECT/INSERT/UPDATE/DELETE, sempre sotto RLS."""
    dish = make_dish(owner, world.alfa, "Frittata", courses=("first",),
                     sources=({"kind": "other", "reference": "dal nonno"},))  # fmt: skip
    with connect_app(autocommit=False) as conn:
        _in_family(conn, world.alfa.id)
        assert conn.execute(f"select count(*) from app.{table}").fetchone()[0] >= 1  # type: ignore[index]  # noqa: S608
        if table == "dish":
            conn.execute("update app.dish set notes = 'n' where id = %s", (dish,))
        conn.execute(f"delete from app.{table} where family_id = %s", (world.alfa.id,))  # noqa: S608


def test_menu_console_cannot_read_dishes(connect_app: Connect, world: World, owner: Owner) -> None:
    """SR-012, SR-040: il Gestore non legge i contenuti."""
    make_dish(owner, world.alfa, "CANARY-ALFA-DISH-1")
    with connect_app("menu_console") as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("select count(*) from app.dish")


def test_indexes_for_listing_and_course_filter_exist(catalog: psycopg.Connection) -> None:
    """05-data §8: `ix_dish_family_name (family_id, name_search)` e `ix_dish_course_course`."""
    rows = {
        r[0]: r[1]
        for r in catalog.execute(
            "select indexname, indexdef from pg_indexes where schemaname = 'app' "
            "and tablename in ('dish', 'dish_course')"
        ).fetchall()
    }
    assert "ix_dish_family_name" in rows, rows
    assert "(family_id, name_search)" in rows["ix_dish_family_name"]
    assert "ix_dish_course_course" in rows, rows
    assert "(family_id, course_id)" in rows["ix_dish_course_course"]


def test_listing_by_name_uses_the_index_not_a_sort_of_the_whole_family(
    owner: Owner, world: World, catalog: psycopg.Connection
) -> None:
    """Q4/paginazione: con molti piatti l'ordine per nome si appoggia a `ix_dish_family_name`."""
    bulk_dishes(owner, world.alfa, 1500)
    owner.execute("analyze app.dish")
    plan = "\n".join(
        r[0]
        for r in catalog.execute(
            "explain select id from app.dish where family_id = %s "
            "order by name_search, id limit 51",
            (world.alfa.id,),
        ).fetchall()
    )
    assert "ix_dish_family_name" in plan, plan
