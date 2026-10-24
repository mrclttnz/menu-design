"""Come popolare e scrivere ogni tabella di famiglia nel test RLS generico (08 §6.4).

Una voce per tabella con `family_id` (e per `family`): ogni slice che crea una tabella di
famiglia aggiunge qui la sua. SL-02: `family`, `family_default_meal`, `person`,
`family_bootstrap`, `course`. Le righe di prova sono sintetiche (nessun dato reale).
"""

from typing import Any
from uuid import UUID, uuid4

from support.accounts import make_account
from support.inventory import FamilyTableSpec
from support.owner import Owner

FROZEN = "2026-01-01"
FAMILY_SQL = "insert into app.family (id, name, frozen_through) values (%s, %s, %s)"


def ensure_family(owner: Owner, family: UUID) -> None:
    owner.execute(
        FAMILY_SQL + " on conflict do nothing", (family, f"CANARY-{str(family)[:8]}", FROZEN)
    )


def person_sql(family: UUID, role: str = "admin") -> tuple[str, tuple[Any, ...]]:
    # SL-03a: `person.account_id` ha la FK verso `account`; chi esegue questo INSERT con `owner`
    # usa `seed_person` (che crea prima l'account). L'INSERT di `menu_app` in un'altra famiglia
    # è respinto dalla RLS prima del controllo della FK.
    return (
        "insert into app.person (family_id, kind, status, account_id, role, joined_on) "
        "values (%s, 'account', 'active', %s, %s, %s)",
        (family, uuid4(), role, FROZEN),
    )


def bootstrap_sql(family: UUID) -> tuple[str, tuple[Any, ...]]:
    return (
        "insert into app.family_bootstrap (family_id, email_sha256, created_at, expires_at) "
        "values (%s, %s, '2026-01-01T00:00:00Z', '2026-01-08T00:00:00Z')",
        (family, bytes(32)),
    )


def seed_person(owner: Owner, family: UUID) -> None:
    ensure_family(owner, family)
    account = make_account(owner)
    owner.execute(
        "insert into app.person (family_id, kind, status, account_id, role, joined_on) "
        "values (%s, 'account', 'active', %s, 'admin', %s)",
        (family, account, FROZEN),
    )


def _seed(sql_for: Any, *, with_family: bool = True) -> Any:
    def seed(owner: Owner, family: UUID) -> None:
        if with_family:
            ensure_family(owner, family)
        query, params = sql_for(family)
        owner.execute(query, params)

    return seed


def seed_dish(owner: Owner, family: UUID) -> None:
    """Un piatto con portata e fonte (SL-04), con la persona e la portata che richiede."""
    ensure_family(owner, family)
    account = make_account(owner)
    person = uuid4()
    owner.execute(
        "insert into app.person (id, family_id, kind, status, account_id, role, joined_on) "
        "values (%s, %s, 'account', 'active', %s, 'planner', %s)",
        (person, family, account, FROZEN),
    )
    course = uuid4()
    owner.execute(
        "insert into app.course (id, family_id, base_code) values (%s, %s, 'second')",
        (course, family),
    )
    dish = uuid4()
    owner.execute(
        "insert into app.dish (id, family_id, name, created_by) values (%s, %s, 'Frittata', %s)",
        (dish, family, person),
    )
    owner.execute(
        "insert into app.dish_course (family_id, dish_id, course_id) values (%s, %s, %s)",
        (family, dish, course),
    )
    owner.execute(
        "insert into app.dish_source (family_id, dish_id, position, kind, reference) "
        "values (%s, %s, 0, 'other', 'dal nonno')",
        (family, dish),
    )


FAMILY_TABLE_SPECS: dict[str, FamilyTableSpec] = {
    "family": FamilyTableSpec(
        seed=lambda o, f: ensure_family(o, f),
        insert_sql=lambda f: (FAMILY_SQL, (f, "X", FROZEN)),
        key_column="id",
    ),
    "family_default_meal": FamilyTableSpec(
        seed=_seed(lambda f: ("insert into app.family_default_meal values (%s, 'lunch')", (f,))),
        insert_sql=lambda f: ("insert into app.family_default_meal values (%s, 'dinner')", (f,)),
    ),
    "person": FamilyTableSpec(seed=seed_person, insert_sql=person_sql),
    "family_bootstrap": FamilyTableSpec(seed=_seed(bootstrap_sql), insert_sql=bootstrap_sql),
    "course": FamilyTableSpec(
        seed=_seed(
            lambda f: ("insert into app.course (family_id, base_code) values (%s, 'starter')", (f,))
        ),
        insert_sql=lambda f: (
            "insert into app.course (family_id, base_code) values (%s, 'first')",
            (f,),
        ),
    ),
    # SL-04: piatti, portate dei piatti, fonti. Gli INSERT di prova puntano a righe che la RLS
    # respinge prima di ogni FK, quindi gli identificativi possono essere casuali.
    "dish": FamilyTableSpec(
        seed=lambda o, f: seed_dish(o, f),
        insert_sql=lambda f: (
            "insert into app.dish (family_id, name, created_by) values (%s, 'X', %s)",
            (f, uuid4()),
        ),
    ),
    "dish_course": FamilyTableSpec(
        seed=lambda o, f: seed_dish(o, f),
        insert_sql=lambda f: (
            "insert into app.dish_course (family_id, dish_id, course_id) values (%s, %s, %s)",
            (f, uuid4(), uuid4()),
        ),
    ),
    "dish_source": FamilyTableSpec(
        seed=lambda o, f: seed_dish(o, f),
        insert_sql=lambda f: (
            "insert into app.dish_source (family_id, dish_id, position, kind, reference) "
            "values (%s, %s, 0, 'other', 'x')",
            (f, uuid4()),
        ),
    ),
}


# SL-05: `change_event` (sola aggiunta). Nessuna FK su `actor_person_id` e `dish_id`: gli
# identificativi possono essere casuali. Il CK di forma per `dish` richiede `dish_id`.
EVENT_INSERT = (
    "insert into app.change_event (family_id, actor_kind, actor_person_id, actor_role, "
    "unit_type, op, dish_id, before, after) "
    "values (%s, 'person', %s, 'planner', 'dish', 'status_change', %s, "
    """'{"st":"to_try"}'::jsonb, '{"v":1,"st":"tested"}'::jsonb)"""
)


def event_sql(family: UUID) -> tuple[str, tuple[Any, ...]]:
    return EVENT_INSERT, (family, uuid4(), uuid4())


FAMILY_TABLE_SPECS["change_event"] = FamilyTableSpec(seed=_seed(event_sql), insert_sql=event_sql)
