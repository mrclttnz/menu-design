"""Dati e aiuti del piano della settimana (SL-06a): pasti, voci, orologio, richieste.

Le righe si scrivono con l'helper `owner` (08 §5.1), mai dall'API, così i test non dipendono dalle
rotte sotto prova. Dati sintetici. Il giorno di riferimento è venerdì 2026-10-23 (`T0`, 12:07 UTC
= 14:07 a Roma): la settimana corrente va da lunedì 2026-10-19 a domenica 2026-10-25.

Nomi delle operazioni (`operationId`, proposti dal tester: vedi il rapporto, NEEDS_DECISION N-1).
Se l'implementazione sceglie altri nomi, si cambiano qui e in `tests/security/authz_matrix.yaml`.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from httpx import Response

from support.dishes import Fam
from support.owner import Owner

OP_PLAN = "plan.view.read"
OP_MEAL = "meal.view.read"
OP_PRESENCE = "meal.presence.write"

T0 = datetime(2026, 10, 23, 12, 7, 30, tzinfo=UTC)
TODAY = date(2026, 10, 23)
YESTERDAY = TODAY - timedelta(days=1)
MONDAY = date(2026, 10, 19)
SUNDAY = date(2026, 10, 25)
MEAL_TYPES = ("breakfast", "lunch", "snack", "dinner", "other")
MAX_DAYS = 62


def iso(day: date) -> str:
    return day.isoformat()


def week(start: date = MONDAY) -> list[date]:
    return [start + timedelta(days=n) for n in range(7)]


# --- preparazione dei dati (via owner) -----------------------------------------------------------


def set_defaults(owner: Owner, fam: Fam, types: tuple[str, ...]) -> None:
    owner.execute("delete from app.family_default_meal where family_id = %s", (fam.id,))
    for meal_type in types:
        owner.execute("insert into app.family_default_meal values (%s, %s)", (fam.id, meal_type))


def set_frozen_through(owner: Owner, fam: Fam, day: date) -> None:
    owner.execute("update app.family set frozen_through = %s where id = %s", (day, fam.id))


def set_timezone(owner: Owner, fam: Fam, timezone: str) -> None:
    owner.execute("update app.family set timezone = %s where id = %s", (timezone, fam.id))


def make_meal(
    owner: Owner,
    fam: Fam,
    day: date,
    meal_type: str = "lunch",
    slot: int = 0,
    *,
    presence: str = "added",
    name: str | None = None,
    special: str | None = None,
    content_version: int = 0,
    guests: int = 0,
    guests_note: str | None = None,
    guests_version: int = 0,
    modified_by: str | None = None,
) -> None:
    person = fam.who(modified_by).person if modified_by else None
    owner.execute(
        "insert into app.meal (family_id, meal_date, meal_type, meal_slot, name, presence, "
        "special_kind, content_version, content_modified_by, guests_count, guests_note, "
        "guests_version) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            fam.id,
            day,
            meal_type,
            slot,
            name,
            presence,
            special,
            content_version,
            person,
            guests,
            guests_note,
            guests_version,
        ),
    )


def add_item(
    owner: Owner,
    fam: Fam,
    day: date,
    meal_type: str = "lunch",
    slot: int = 0,
    *,
    dish: UUID | None = None,
    course: str = "first",
    text: str | None = None,
    position: int = 0,
    not_cooked: bool = False,
) -> UUID:
    """Una voce del pasto (che deve esistere). Piatto: `dish`; voce libera: `text`."""
    item = uuid4()
    if dish is not None:
        owner.execute(
            "insert into app.meal_item (id, family_id, meal_date, meal_type, meal_slot, position, "
            "kind, dish_id, course_id, not_cooked) values (%s, %s, %s, %s, %s, %s, 'dish', %s, "
            "%s, %s)",
            (item, fam.id, day, meal_type, slot, position, dish, fam.courses[course], not_cooked),
        )
    else:
        owner.execute(
            "insert into app.meal_item (id, family_id, meal_date, meal_type, meal_slot, position, "
            "kind, free_text) values (%s, %s, %s, %s, %s, %s, 'free_text', %s)",
            (item, fam.id, day, meal_type, slot, position, text),
        )
    return item


MEAL_COLUMNS = (
    "meal_date, meal_type, meal_slot, name, presence, special_kind, content_version, "
    "content_modified_by, guests_count, guests_note, guests_version"
)


def meal_rows(owner: Owner, fam: Fam) -> list[dict[str, Any]]:
    keys = [c.strip() for c in MEAL_COLUMNS.split(",")]
    rows = owner.rows(
        f"select {MEAL_COLUMNS} from app.meal where family_id = %s "  # noqa: S608
        "order by meal_date, meal_type, meal_slot",
        (fam.id,),
    )
    return [dict(zip(keys, r, strict=True)) for r in rows]


def meal_row(
    owner: Owner, fam: Fam, day: date, meal_type: str = "lunch", slot: int = 0
) -> dict[str, Any] | None:
    found = [
        r
        for r in meal_rows(owner, fam)
        if (r["meal_date"], r["meal_type"], r["meal_slot"]) == (day, meal_type, slot)
    ]
    assert len(found) <= 1
    return found[0] if found else None


def item_rows(owner: Owner, fam: Fam) -> list[tuple[Any, ...]]:
    return owner.rows(
        "select meal_date, meal_type, meal_slot, position, kind, dish_id, free_text "
        "from app.meal_item where family_id = %s order by meal_date, meal_type, position",
        (fam.id,),
    )


def planning_state(owner: Owner, fam: Fam) -> str:
    """Impronta di `meal` e `meal_item` di una famiglia: una richiesta li ha toccati?"""
    parts = []
    for table in ("meal", "meal_item"):
        if owner.scalar("select to_regclass(%s) is null", (f"app.{table}",)):
            continue  # prima della migrazione 0009 (SL-06a) non c'è nulla da confrontare
        rows = owner.rows(
            f"select t::text from app.{table} t where family_id = %s order by 1",  # noqa: S608
            (fam.id,),
        )
        parts.append("|".join(r[0] for r in rows))
    return "||".join(parts)


# --- richieste e risposte -------------------------------------------------------------------------

PLAN = "/api/v1/plan"


def meal_url(day: date | str, meal_type: str = "lunch", slot: int | str = 0) -> str:
    return f"/api/v1/meals/{day}/{meal_type}/{slot}"


def presence_url(day: date | str, meal_type: str = "lunch", slot: int | str = 0) -> str:
    return meal_url(day, meal_type, slot) + "/presence"


def plan_query(start: date | str | None = None, end: date | str | None = None) -> str:
    parts = []
    if start is not None:
        parts.append(f"from={start}")
    if end is not None:
        parts.append(f"to={end}")
    return PLAN + ("?" + "&".join(parts) if parts else "")


def days_of(response: Response) -> list[dict[str, Any]]:
    assert response.status_code == 200, (response.status_code, response.text)
    days: list[dict[str, Any]] = response.json()["days"]
    return days


def meals_by_day(response: Response) -> dict[str, list[tuple[str, int]]]:
    """`{data: [(tipo, slot), ...]}` nell'ordine restituito."""
    return {d["date"]: [(m["mealType"], m["slot"]) for m in d["meals"]] for d in days_of(response)}


def set_presence(actor: Any, day: date | str, meal_type: str, present: bool, version: Any) -> Any:
    return actor.put(presence_url(day, meal_type, 0), {"present": present}, if_match=version)
