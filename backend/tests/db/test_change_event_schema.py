"""Tabella `change_event` (migrazione 0008, SL-05): 05-data §4.2 e §3.2, §6.1, §6.3; ADR-0012.

US-049: AC-049.2 (nessun nome o email, solo identificativi), AC-049.3 (nessun account può
creare, modificare o cancellare un evento direttamente: `menu_app` ha solo SELECT e INSERT e un
trigger rifiuta ogni UPDATE, anche del proprietario). SR-022 e SR-057 (sola aggiunta), SR-047
(pseudonimizzazione), SR-042 (identificativi non sequenziali), THR-117 (evento alterato o negato),
THR-026 (RLS). Le cancellazioni avvengono solo per cascata con la famiglia.
"""

import secrets
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors

from support.family_specs import ensure_family
from support.owner import Owner

Connect = Callable[..., psycopg.Connection]

COLUMNS = {
    "id": ("uuid", "NO"),
    "family_id": ("uuid", "NO"),
    "occurred_at": ("timestamp with time zone", "NO"),
    "actor_kind": ("text", "NO"),
    "actor_person_id": ("uuid", "YES"),
    "actor_role": ("text", "YES"),
    "unit_type": ("text", "NO"),
    "op": ("text", "NO"),
    "meal_date": ("date", "YES"),
    "meal_type": ("text", "YES"),
    "meal_slot": ("smallint", "YES"),
    "subject_person_id": ("uuid", "YES"),
    "dish_id": ("uuid", "YES"),
    "before": ("jsonb", "YES"),
    "after": ("jsonb", "NO"),  # NOT NULL: ogni evento porta `v` (decisione 2026-10-23)
    "correlation_id": ("uuid", "YES"),
}
INSERT_DISH = (
    "insert into app.change_event (family_id, actor_kind, actor_person_id, actor_role, "
    "unit_type, op, dish_id, before, after) values (%s, 'person', %s, 'planner', 'dish', "
    """'status_change', %s, '{"st":"to_try"}', '{"v":1,"st":"tested"}') returning id"""
)


def _event(owner: Owner, family: UUID | None = None) -> tuple[UUID, UUID]:
    family = family or uuid4()
    ensure_family(owner, family)
    rows = owner.rows(INSERT_DISH, (family, uuid4(), uuid4()))
    return family, rows[0][0]


def _insert_raw(owner: Owner, **cols: Any) -> None:
    """INSERT diretto (via owner) di una riga con le colonne indicate; il resto è valido."""
    family = uuid4()
    ensure_family(owner, family)
    row: dict[str, Any] = {
        "family_id": family,
        "actor_kind": "person",
        "actor_person_id": uuid4(),
        "actor_role": "planner",
        "unit_type": "dish",
        "op": "status_change",
        "dish_id": uuid4(),
        "before": '{"st":"to_try"}',
        "after": '{"v":1,"st":"tested"}',
    }
    row.update(cols)
    names = ", ".join(row)
    marks = ", ".join(["%s"] * len(row))
    owner.execute(f"insert into app.change_event ({names}) values ({marks})", tuple(row.values()))  # noqa: S608  (colonne scelte dal test)


# --- struttura ------------------------------------------------------------------------------------


def test_change_event_has_exactly_the_documented_columns(catalog: psycopg.Connection) -> None:
    rows = catalog.execute(
        "select column_name, data_type, is_nullable from information_schema.columns "
        "where table_schema = 'app' and table_name = 'change_event'"
    ).fetchall()
    assert rows, "tabella app.change_event assente (migrazione 0008)"
    assert {r[0]: (r[1], r[2]) for r in rows} == COLUMNS


def test_no_column_can_hold_a_name_or_an_email(catalog: psycopg.Connection) -> None:
    """AC-049.2, SR-047: le persone si indicano solo con l'identificativo."""
    columns = {
        r[0]
        for r in catalog.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'app' and table_name = 'change_event'"
        ).fetchall()
    }
    assert columns, "tabella app.change_event assente (migrazione 0008)"
    assert not {c for c in columns if "name" in c or "email" in c or "label" in c}
    text_columns = {
        r[0]
        for r in catalog.execute(
            "select column_name from information_schema.columns where table_schema = 'app' "
            "and table_name = 'change_event' and data_type in ('text', 'character varying')"
        ).fetchall()
    }
    assert text_columns == {"actor_kind", "actor_role", "unit_type", "op", "meal_type"}, (
        "le sole colonne di testo sono codici di un elenco chiuso (CHECK)"
    )


def test_primary_key_and_non_sequential_id(owner: Owner, catalog: psycopg.Connection) -> None:
    """SR-042: `id` è un UUID casuale (`gen_random_uuid()`), non un contatore."""
    key = catalog.execute(
        "select a.attname from pg_index i join pg_attribute a on a.attrelid = i.indrelid "
        "and a.attnum = any(i.indkey) where i.indrelid = 'app.change_event'::regclass "
        "and i.indisprimary"
    ).fetchall()
    assert key == [("id",)]
    default = catalog.execute(
        "select column_default from information_schema.columns where table_schema = 'app' "
        "and table_name = 'change_event' and column_name = 'id'"
    ).fetchone()
    assert default is not None
    assert "gen_random_uuid" in default[0]
    _, first = _event(owner)
    _, second = _event(owner)
    assert first.version == 4
    assert second.version == 4


def test_occurred_at_defaults_to_the_database_utc_clock(
    owner: Owner, frozen_now: Callable[..., None]
) -> None:
    """Tutti gli eventi di una transazione condividono l'istante (`app.now_utc()`, 05-data)."""
    from datetime import UTC, datetime

    instant = datetime(2026, 10, 23, 12, 7, 30, tzinfo=UTC)
    frozen_now(instant)
    family, event = _event(owner)
    assert owner.scalar("select occurred_at from app.change_event where id = %s", (event,)) == (
        instant
    )
    default = owner.scalar(
        "select column_default from information_schema.columns where table_schema = 'app' "
        "and table_name = 'change_event' and column_name = 'occurred_at'"
    )
    assert "now_utc" in default
    assert family


def test_indexes_of_the_history_queries_exist(catalog: psycopg.Connection) -> None:
    """05-data §5: cronologia paginata a cursore e cronologia per giorno e pasto."""
    rows: dict[str, str] = dict(
        catalog.execute(
            "select indexname, indexdef from pg_indexes where schemaname = 'app' "
            "and tablename = 'change_event'"
        ).fetchall()
    )
    time_idx = rows.get("ix_change_event_family_time")
    day_idx = rows.get("ix_change_event_family_day")
    assert time_idx, rows
    assert day_idx, rows
    flat = time_idx.replace(" ", "")
    assert "(family_id,occurred_atDESC,id)" in flat
    assert "(family_id,meal_date)" in day_idx.replace(" ", "")
    assert "WHERE (meal_date IS NOT NULL)" in day_idx


# --- vincoli CHECK -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"actor_kind": "account"},
        {"actor_kind": "robot"},
        {"actor_role": "owner"},
        {"unit_type": "meal"},
        {"unit_type": "dish_like"},
        {"op": "delete"},
        {"op": "update"},
        # (actor_kind = 'person') = (actor_person_id IS NOT NULL), in entrambi i sensi
        {"actor_person_id": None},
        {"actor_kind": "system", "actor_person_id": uuid4()},
        {"actor_kind": "platform_operator", "actor_person_id": uuid4()},
        # chiave di forma per tipo: `dish` richiede `dish_id`
        {"dish_id": None},
    ],
)
def test_check_constraints_refuse_malformed_events(owner: Owner, override: dict[str, Any]) -> None:
    with pytest.raises(errors.CheckViolation):
        _insert_raw(owner, **override)


@pytest.mark.parametrize(
    "override",
    [
        {"actor_kind": "system", "actor_person_id": None, "actor_role": None},
        {"actor_kind": "platform_operator", "actor_person_id": None, "actor_role": None},
        {"actor_role": "admin"},
        {"actor_role": "member"},
    ],
)
def test_check_constraints_accept_the_documented_variants(
    owner: Owner, override: dict[str, Any]
) -> None:
    _insert_raw(owner, **override)
    assert owner.scalar("select count(*) from app.change_event") == 1


@pytest.mark.parametrize(
    ("unit_type", "op", "missing"),
    [
        ("meal_content", "set", {"meal_date": None}),
        ("meal_content", "set", {"meal_type": None}),
        ("meal_content", "set", {"meal_slot": None}),
        ("meal_guests", "set", {"meal_date": None}),
        ("attendance", "set", {"subject_person_id": None}),
        ("typical_week", "set", {"subject_person_id": None}),
        ("membership", "role_change", {"subject_person_id": None}),
    ],
)
def test_the_key_shape_check_requires_the_keys_of_each_unit_type(
    owner: Owner, unit_type: str, op: str, missing: dict[str, Any]
) -> None:
    keys = {
        "dish_id": None,
        "meal_date": "2026-10-23",
        "meal_type": "lunch",
        "meal_slot": 0,
        "subject_person_id": uuid4(),
    }
    ok = {"unit_type": unit_type, "op": op, "before": None, "after": '{"v":1}'} | keys
    _insert_raw(owner, **ok)  # completa: accettata
    with pytest.raises(errors.CheckViolation):
        _insert_raw(owner, **(ok | missing))


def test_before_plus_after_above_20480_bytes_is_refused(owner: Owner) -> None:
    """CK `coalesce(pg_column_size(before), 0) + pg_column_size(after) <= 20480` (05-data v10)."""
    huge = '{"v":1,"st":"' + secrets.token_hex(10300) + '"}'  # ~20,6 kB, non comprimibile
    with pytest.raises(errors.CheckViolation):
        _insert_raw(owner, after=huge)


def test_actor_person_and_dish_have_no_foreign_key(
    owner: Owner, catalog: psycopg.Connection
) -> None:
    """Riga di sola aggiunta: il piatto può sparire ("piatto eliminato"), la persona diventa
    tombstone; nessun riferimento deve impedirlo né riscrivere l'evento."""
    fks = catalog.execute(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid = 'app.change_event'::regclass and contype = 'f'"
    ).fetchall()
    assert len(fks) == 1, fks
    assert "REFERENCES app.family(id) ON DELETE CASCADE" in fks[0][0]
    _insert_raw(owner)  # persona e piatto inesistenti: accettato


# --- immutabilità: privilegi e trigger (AC-049.3, SR-022, SR-057) --------------------------------


@pytest.mark.parametrize(
    ("role", "privilege", "expected"),
    [
        ("menu_app", "SELECT", True),
        ("menu_app", "INSERT", True),
        ("menu_app", "UPDATE", False),
        ("menu_app", "DELETE", False),
        ("menu_app", "TRUNCATE", False),
        ("menu_app", "REFERENCES", False),
        ("menu_app", "TRIGGER", False),
        ("menu_console", "SELECT", False),
        ("menu_console", "INSERT", False),
        ("menu_console", "UPDATE", False),
        ("menu_console", "DELETE", False),
        ("menu_backup", "SELECT", True),
        ("menu_backup", "INSERT", False),
        ("menu_backup", "UPDATE", False),
        ("menu_backup", "DELETE", False),
    ],
)
def test_privileges_on_change_event(
    catalog: psycopg.Connection, role: str, privilege: str, expected: bool
) -> None:
    assert catalog.execute("select to_regclass('app.change_event')").fetchone() != (None,), (
        "tabella app.change_event assente (migrazione 0008)"
    )
    got = catalog.execute(
        "select has_table_privilege(%s, 'app.change_event'::regclass, %s)", (role, privilege)
    ).fetchone()
    assert got == (expected,), (role, privilege)


def test_menu_app_cannot_update_or_delete_an_event(owner: Owner, connect_app: Connect) -> None:
    family, event = _event(owner)
    with connect_app() as conn:
        conn.autocommit = False
        conn.execute("select set_config('app.family_id', %s, true)", (str(family),))
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("update app.change_event set op = 'archive' where id = %s", (event,))
        conn.rollback()
        conn.execute("select set_config('app.family_id', %s, true)", (str(family),))
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("delete from app.change_event where id = %s", (event,))
        conn.rollback()
        conn.execute("select set_config('app.family_id', %s, true)", (str(family),))
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("truncate app.change_event")
    assert owner.scalar("select count(*) from app.change_event") == 1


def test_the_immutability_trigger_refuses_every_update_even_for_the_owner(owner: Owner) -> None:
    """`tg_change_event_immutable BEFORE UPDATE` solleva sempre (05-data, THR-117)."""
    _, event = _event(owner)
    triggers = owner.rows(
        "select tgname, tgtype & 2 = 2 as before_row, tgtype & 16 = 16 as on_update "
        "from pg_trigger where tgrelid = 'app.change_event'::regclass and not tgisinternal"
    )
    assert ("tg_change_event_immutable", True, True) in triggers, triggers
    for statement in (
        "update app.change_event set op = 'archive' where id = %s",
        "update app.change_event set after = '{}' where id = %s",
        "update app.change_event set family_id = family_id where id = %s",
        "update app.change_event set op = op where id = %s",
    ):
        with pytest.raises(psycopg.Error) as raised:
            owner.execute(statement, (event,))
        assert "immutable" in str(raised.value).lower() or "append" in str(raised.value).lower(), (
            statement,
            str(raised.value),
        )
    assert owner.scalar("select op from app.change_event where id = %s", (event,)) == (
        "status_change"
    )


def test_events_disappear_only_with_the_family_by_cascade(owner: Owner) -> None:
    family, _ = _event(owner)
    _event(owner, family)
    other, _ = _event(owner)
    assert (
        owner.scalar("select count(*) from app.change_event where family_id = %s", (family,)) == 2
    )
    owner.execute("delete from app.family where id = %s", (family,))
    assert (
        owner.scalar("select count(*) from app.change_event where family_id = %s", (family,)) == 0
    )
    assert owner.scalar("select count(*) from app.change_event where family_id = %s", (other,)) == 1


# --- RLS: p_family_select e p_family_insert, nessuna policy FOR ALL (THR-026) --------------------


def test_policies_are_split_into_select_and_insert_for_menu_app(
    catalog: psycopg.Connection,
) -> None:
    rows = catalog.execute(
        "select polname, polcmd, polroles::regrole[]::text, "
        "coalesce(pg_get_expr(polqual, polrelid), ''), "
        "coalesce(pg_get_expr(polwithcheck, polrelid), '') "
        "from pg_policy where polrelid = 'app.change_event'::regclass order by polname"
    ).fetchall()
    by_name = {r[0]: r for r in rows}
    assert {"p_family_select", "p_family_insert", "p_owner", "p_backup"} <= set(by_name), by_name
    assert "p_family" not in by_name, "una policy FOR ALL permetterebbe UPDATE e DELETE"
    assert by_name["p_family_select"][1] == "r"
    assert by_name["p_family_insert"][1] == "a"
    assert "family_id = app.current_family_id()" in by_name["p_family_select"][3]
    assert "family_id = app.current_family_id()" in by_name["p_family_insert"][4]
    forced = catalog.execute(
        "select relrowsecurity, relforcerowsecurity from pg_class "
        "where oid = 'app.change_event'::regclass"
    ).fetchone()
    assert forced == (True, True)


def test_menu_app_reads_only_the_events_of_the_family_in_context(
    owner: Owner, connect_app: Connect
) -> None:
    mine, _ = _event(owner)
    theirs, _ = _event(owner)
    with connect_app() as conn:
        conn.autocommit = False
        assert conn.execute("select count(*) from app.change_event").fetchone() == (0,), (
            "senza contesto di famiglia nessuna riga"
        )
        conn.execute("select set_config('app.family_id', %s, true)", (str(mine),))
        families = {r[0] for r in conn.execute("select family_id from app.change_event")}
        assert families == {mine}
        assert theirs not in families


def test_menu_app_inserts_only_into_the_family_in_context(
    owner: Owner, connect_app: Connect
) -> None:
    mine, _ = _event(owner)
    theirs, _ = _event(owner)
    with connect_app() as conn:
        conn.autocommit = False
        with pytest.raises(errors.InsufficientPrivilege):  # nessun contesto
            conn.execute(INSERT_DISH, (mine, uuid4(), uuid4()))
        conn.rollback()
        conn.execute("select set_config('app.family_id', %s, true)", (str(mine),))
        with pytest.raises(errors.InsufficientPrivilege):  # famiglia diversa dal contesto
            conn.execute(INSERT_DISH, (theirs, uuid4(), uuid4()))
        conn.rollback()
        conn.execute("select set_config('app.family_id', %s, true)", (str(mine),))
        conn.execute(INSERT_DISH, (mine, uuid4(), uuid4()))
        conn.commit()
    assert owner.scalar("select count(*) from app.change_event where family_id = %s", (mine,)) == 2
    assert (
        owner.scalar("select count(*) from app.change_event where family_id = %s", (theirs,)) == 1
    )


def test_a_failed_insert_leaves_no_row_behind(owner: Owner, connect_app: Connect) -> None:
    family, _ = _event(owner)
    with connect_app() as conn:
        conn.autocommit = False
        conn.execute("select set_config('app.family_id', %s, true)", (str(family),))
        with pytest.raises(errors.CheckViolation):
            conn.execute(
                INSERT_DISH.replace("'status_change'", "'delete'"), (family, uuid4(), uuid4())
            )
    assert owner.scalar("select count(*) from app.change_event") == 1
