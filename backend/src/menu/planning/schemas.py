"""DTO del pasto (piano §4.2): `MealView` e il corpo della presenza.

Il corpo è chiuso (`extra='forbid'`, SR-010, SR-024) e `present` deve essere un booleano JSON.
Le risposte omettono i campi facoltativi non impostati: `MealView` imposta sempre tutti i propri
(i nulli sono valori), una voce imposta solo i campi del suo tipo. Gli ospiti, le presenze e i
coperti arrivano con M1 (SL-15): il contratto è additivo.
"""

import datetime as dt
from typing import Literal
from uuid import UUID

from pydantic import StrictBool

from menu.catalog.schemas import Body, View

MealType = Literal["breakfast", "lunch", "snack", "dinner", "other"]
SpecialKind = Literal["away", "restaurant", "skipped"]


class MealItemView(View):
    id: UUID
    position: int
    kind: Literal["dish", "free_text"]
    dish_id: UUID | None = None
    course_id: UUID | None = None
    free_text: str | None = None
    not_cooked: bool


class MealView(View):
    date: dt.date
    meal_type: MealType
    slot: int
    name: str | None
    present: bool
    special: SpecialKind | None
    content_version: int
    content_modified_by: UUID | None
    items: list[MealItemView]
    past: bool


class PresenceChange(Body):
    """`PUT .../presence`: aggiungere (`true`) o togliere (`false`) il pasto di quel giorno."""

    present: StrictBool
