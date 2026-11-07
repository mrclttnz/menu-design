"""Il pasto: lettura (singolo e intervallo) e presenza (SL-06a; US-008, ADR-0007, ADR-0009).

Un pasto si indirizza per (data, tipo, slot) e la famiglia viene sempre dal contesto: nessun
identificativo di famiglia entra da fuori (SR-008). «Presente» non è una colonna: lo decide
`app.effective_meals()` (05-data §7.1) dai pasti di default e dalle righe `meal`, quindi un pasto
mai scritto è presente alla versione `0` se è di default, e assente se non lo è. Una lettura non
crea righe. Il contenuto di un pasto assente (`removed`) resta nella riga ma non si mostra.

La presenza è una scrittura tracciata: riga bloccata, `412` se la versione è superata, tetto
giornaliero (`429`), poi modifica ed evento nella stessa transazione (ADR-0012). Il contenuto dei
pasti non esce mai in log.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text

from menu import ratelimit, tenancy
from menu.common import AppError, ErrorCode, RequestContext, ValidationCode
from menu.history import EventKey, codec, record_change
from menu.planning.schemas import MealItemView, MealView
from menu.platform.http.problem import field_error
from menu.tenancy import Tx

MAX_DAYS = 62
MEAL_ORDER = ("breakfast", "lunch", "snack", "dinner", "other")
OTHER_SLOTS = 5

_FAMILY_CLOCK = text(
    "select timezone, app.family_today() as today from app.family where id = :family"
)
_ENSURE_ROW = text(
    "insert into app.meal (family_id, meal_date, meal_type, meal_slot, presence) "
    "select :family, :day, cast(:type as text), cast(:slot as smallint), "
    "case when cast(:slot as smallint) = 0 and exists ("
    "select 1 from app.family_default_meal d where d.family_id = :family and d.meal_type = :type"
    ") then 'inherit' else 'removed' end "
    "on conflict (family_id, meal_date, meal_type, meal_slot) do nothing"
)
_LOCK_MEAL = text(
    "select presence, special_kind, name, content_version, content_modified_by, "
    "content_modified_at, guests_count, guests_note from app.meal "
    "where family_id = :family and meal_date = :day and meal_type = :type and meal_slot = :slot "
    "for update"
)
_IS_PRESENT = text(
    "select exists (select 1 from app.effective_meals(:day, :day) e "
    "where e.meal_type = :type and e.meal_slot = :slot)"
)
_MEAL_ROW = text(
    "select exists (select 1 from app.effective_meals(:day, :day) e "
    "where e.meal_type = :type and e.meal_slot = :slot) as present, "
    "m.name, m.special_kind, m.content_version, m.content_modified_by, "
    "app.family_today() as today "
    "from (select 1) one left join app.meal m on m.family_id = :family "
    "and m.meal_date = :day and m.meal_type = :type and m.meal_slot = :slot"
)
_MEAL_ITEMS = text(
    "select id, position, kind, dish_id, course_id, free_text, not_cooked from app.meal_item "
    "where family_id = :family and meal_date = :day and meal_type = :type and meal_slot = :slot "
    "order by position"
)
_RANGE_MEALS = text(
    "select e.meal_date, e.meal_type, e.meal_slot, m.name, m.special_kind, "
    "coalesce(m.content_version, 0) as content_version, m.content_modified_by "
    "from app.effective_meals(:start, :end) e "
    "left join app.meal m on m.family_id = :family and m.meal_date = e.meal_date "
    "and m.meal_type = e.meal_type and m.meal_slot = e.meal_slot "
    "order by e.meal_date, array_position(array['breakfast', 'lunch', 'snack', 'dinner', "
    "'other'], e.meal_type), e.meal_slot"
)
_RANGE_ITEMS = text(
    "select id, meal_date, meal_type, meal_slot, position, kind, dish_id, course_id, free_text, "
    "not_cooked from app.meal_item "
    "where family_id = :family and meal_date between :start and :end "
    "order by meal_date, meal_type, meal_slot, position"
)
_UPDATE_PRESENCE = text(
    "update app.meal set presence = :presence, content_version = content_version + 1, "
    "content_modified_by = :person, content_modified_at = app.now_utc() "
    "where family_id = :family and meal_date = :day and meal_type = :type and meal_slot = :slot"
)
_EMPTY_CONTENT = text(
    "update app.meal set special_kind = null, name = null "
    "where family_id = :family and meal_date = :day and meal_type = :type and meal_slot = :slot"
)
_EMPTY_GUESTS = text(
    "update app.meal set guests_count = 0, guests_note = null, "
    "guests_version = guests_version + 1, guests_modified_by = :person, "
    "guests_modified_at = app.now_utc() "
    "where family_id = :family and meal_date = :day and meal_type = :type and meal_slot = :slot"
)
_DELETE_ITEMS = text(
    "delete from app.meal_item "
    "where family_id = :family and meal_date = :day and meal_type = :type and meal_slot = :slot "
    "returning id, position, dish_id, course_id, free_text, not_cooked"
)


@dataclass(frozen=True)
class MealKey:
    day: dt.date
    meal_type: str
    slot: int

    @property
    def is_valid(self) -> bool:
        """Lo slot è 0 per i tipi standard e 0-4 per «altro» (ADR-0009)."""
        if self.meal_type == "other":
            return 0 <= self.slot < OTHER_SLOTS
        return self.slot == 0

    def params(self, family: UUID) -> dict[str, Any]:
        return {"family": family, "day": self.day, "type": self.meal_type, "slot": self.slot}


@dataclass(frozen=True)
class PlanData:
    start: dt.date
    end: dt.date
    today: dt.date
    timezone: str
    days: list[tuple[dt.date, list[MealView]]]


def _family(ctx: RequestContext) -> UUID:
    if ctx.family_id is None or ctx.person_id is None:
        raise AppError(ErrorCode.FORBIDDEN)
    return ctx.family_id


def _item(row: Any) -> MealItemView:
    if row["kind"] == "dish":
        return MealItemView(
            id=row["id"],
            position=row["position"],
            kind="dish",
            dish_id=row["dish_id"],
            course_id=row["course_id"],
            not_cooked=row["not_cooked"],
        )
    return MealItemView(
        id=row["id"],
        position=row["position"],
        kind="free_text",
        free_text=row["free_text"],
        not_cooked=row["not_cooked"],
    )


def _view(
    key: MealKey, row: Any, items: list[MealItemView], today: dt.date, *, present: bool
) -> MealView:
    """Un pasto assente non mostra contenuto: né voci, né stato speciale, né nome."""
    return MealView(
        date=key.day,
        meal_type=key.meal_type,
        slot=key.slot,
        name=row["name"] if present else None,
        present=present,
        special=row["special_kind"] if present else None,
        content_version=row["content_version"] or 0,
        content_modified_by=row["content_modified_by"],
        items=items if present else [],
        past=key.day < today,
    )


def _load(tx: Tx, family: UUID, key: MealKey) -> MealView:
    params = key.params(family)
    row = tx.execute(_MEAL_ROW, params).mappings().one()
    present = bool(row["present"])
    items = [_item(r) for r in tx.execute(_MEAL_ITEMS, params).mappings()] if present else []
    return _view(key, row, items, row["today"], present=present)


def read_meal(ctx: RequestContext, key: MealKey) -> MealView:
    family = _family(ctx)
    with tenancy.family_tx(ctx) as tx:
        return _load(tx, family, key)


def _resolve_range(
    start: dt.date | None, end: dt.date | None, today: dt.date
) -> tuple[dt.date, dt.date]:
    """Un estremo mancante vale quello della settimana corrente (lunedì-domenica, SR-060)."""
    monday = today - dt.timedelta(days=today.weekday())
    first = monday if start is None else start
    last = monday + dt.timedelta(days=6) if end is None else end
    if last < first:
        raise AppError(
            ErrorCode.VALIDATION,
            {"errors": [field_error("to", ValidationCode.RANGE_ORDER)]},
        )
    if (last - first).days + 1 > MAX_DAYS:
        raise AppError(ErrorCode.RANGE_TOO_LARGE, {"maxDays": MAX_DAYS})
    return first, last


def read_plan(tx: Tx, ctx: RequestContext, start: dt.date | None, end: dt.date | None) -> PlanData:
    """I pasti di un intervallo (al massimo 62 giorni) con le loro voci, nella transazione data."""
    family = _family(ctx)
    clock = tx.execute(_FAMILY_CLOCK, {"family": family}).mappings().first()
    if clock is None:
        raise AppError(ErrorCode.FORBIDDEN)
    today: dt.date = clock["today"]
    first, last = _resolve_range(start, end, today)
    params = {"family": family, "start": first, "end": last}
    items: dict[tuple[dt.date, str, int], list[MealItemView]] = defaultdict(list)
    for row in tx.execute(_RANGE_ITEMS, params).mappings():
        items[(row["meal_date"], row["meal_type"], row["meal_slot"])].append(_item(row))
    by_day: dict[dt.date, list[MealView]] = {
        first + dt.timedelta(days=n): [] for n in range((last - first).days + 1)
    }
    for row in tx.execute(_RANGE_MEALS, params).mappings():
        key = MealKey(row["meal_date"], row["meal_type"], row["meal_slot"])
        by_day[key.day].append(
            _view(key, row, items.get((key.day, key.meal_type, key.slot), []), today, present=True)
        )
    return PlanData(first, last, today, clock["timezone"], sorted(by_day.items()))


def _conflict(tx: Tx, family: UUID, key: MealKey, locked: Any) -> AppError:
    """`412` con il pasto corrente, l'autore (ID) e l'istante dell'ultima modifica."""
    at = locked["content_modified_at"]
    return AppError(
        ErrorCode.CONFLICT,
        {
            "current": _load(tx, family, key).model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "modifiedBy": None
            if locked["content_modified_by"] is None
            else str(locked["content_modified_by"]),
            "modifiedAt": None if at is None else at.isoformat().replace("+00:00", "Z"),
        },
    )


def _target_presence(old: str, was_present: bool, present: bool) -> str:
    """La presenza da scrivere. Chiedere lo stato che il pasto ha già lo lascia com'è."""
    if not present:
        return "removed"
    if was_present:
        return old
    return "added"


def _item_state(row: Any) -> dict[str, Any]:
    """Stato di una voce nel formato del codec; `n` solo se vero, i campi nulli omessi."""
    state: dict[str, Any] = {"p": row["position"]}
    if row["dish_id"] is not None:
        state["d"], state["c"] = str(row["dish_id"]), str(row["course_id"])
    else:
        state["t"] = row["free_text"]
    if row["not_cooked"]:
        state["n"] = True
    return state


def set_presence(
    ctx: RequestContext, key: MealKey, present: bool, expected_version: int
) -> MealView:
    """Aggiunge o toglie il pasto di quel giorno e registra l'evento (US-008, ADR-0009).

    La riga si crea al bisogno e si blocca (`FOR UPDATE`): di due richieste con la stessa versione
    ne riesce una sola, anche se la riga non esisteva. Ordine: `412` se la versione è superata,
    tetto giornaliero (`429`), scrittura ed evento; un errore annulla tutto, riga creata compresa.
    Ogni richiesta valida avanza la versione e scrive un evento, anche se lo stato richiesto è
    quello già presente. Rimettere un pasto tolto riusa la riga e lo svuota (voci, stato speciale,
    nome e ospiti, la cui versione cresce sempre): le voci tolte stanno nell'evento, complete; un
    evento `meal_guests` si scrive solo se ospiti o nota cambiano. Un pasto `inherit` nascosto si
    riaccende intatto.
    """
    family = _family(ctx)
    params = key.params(family)
    with ratelimit.tracked_write(ctx), tenancy.family_tx(ctx) as tx:
        tx.execute(_ENSURE_ROW, params)
        row = tx.execute(_LOCK_MEAL, params).mappings().one()
        if row["content_version"] != expected_version:
            raise _conflict(tx, family, key, row)
        ratelimit.consume_tracked_write(tx, ctx)
        was_present = bool(tx.execute(_IS_PRESENT, params).scalar_one())
        old = row["presence"]
        new = _target_presence(old, was_present, present)
        empty = old == "removed" and new == "added"
        old_state: dict[str, Any] = {"pr": old}
        new_state: dict[str, Any] = {"pr": new}
        if empty:
            removed = tx.execute(_DELETE_ITEMS, params).mappings().all()
            old_state |= {
                "i": {str(r["id"]): _item_state(r) for r in removed},
                "s": row["special_kind"],
                "nm": row["name"],
            }
            new_state |= {"i": {}, "s": None, "nm": None}
            tx.execute(_EMPTY_CONTENT, params)
        tx.execute(_UPDATE_PRESENCE, params | {"presence": new, "person": ctx.person_id})
        before: dict[str, Any] | None
        if old == new:
            before, after = {"pr": old}, {"v": codec.CODEC_VERSION, "pr": new}
        else:
            before, after = codec.diff("meal_content", old_state, new_state)
        event_key = EventKey(meal_date=key.day, meal_type=key.meal_type, meal_slot=key.slot)
        record_change(
            tx,
            ctx,
            unit_type="meal_content",
            op="set" if present else "clear",
            key=event_key,
            before=before,
            after=after,
        )
        if empty:
            tx.execute(_EMPTY_GUESTS, params | {"person": ctx.person_id})
        if empty and (row["guests_count"] != 0 or row["guests_note"] is not None):
            guests_before, guests_after = codec.diff(
                "meal_guests",
                {"g": row["guests_count"], "gn": row["guests_note"]},
                {"g": 0, "gn": None},
            )
            record_change(
                tx,
                ctx,
                unit_type="meal_guests",
                op="clear",
                key=event_key,
                before=guests_before,
                after=guests_after,
            )
        return _load(tx, family, key)
