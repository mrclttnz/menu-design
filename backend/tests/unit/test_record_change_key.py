"""`record_change`: l'allow-list di `EventKey` per tipo di unità (CR-SL05-004, SL-06a).

05-data §12: per ogni tipo di unità le colonne chiave ESATTE. Una chiave che non corrisponde
all'unità solleva `ValueError` PRIMA di toccare il database (così l'errore è del chiamante, non un
`CheckViolation` a metà transazione), e non scrive nulla. Il database ha la stessa regola in
`ck_change_event_key` (`tests/db/test_change_event_schema.py`).
"""

from datetime import date
from typing import Any
from uuid import uuid4

import pytest

from menu.common import RequestContext
from menu.history import EventKey, record_change

DAY = date(2026, 10, 24)
PERSON = uuid4()
DISH = uuid4()

AFTER_MEAL = {"v": 1, "pr": "removed"}
BEFORE_MEAL = {"pr": "inherit"}


def _meal_key(**extra: Any) -> EventKey:
    return EventKey(meal_date=DAY, meal_type="dinner", meal_slot=0, **extra)


class RecordingTx:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def execute(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


def _ctx() -> RequestContext:
    return RequestContext(
        correlation_id=uuid4(),
        account_id=uuid4(),
        session_id=None,
        auth_time=None,
        family_id=uuid4(),
        person_id=PERSON,
        role="planner",
        family_status="active",
    )


def _record(unit_type: str, op: str, key: EventKey, before: Any, after: Any) -> RecordingTx:
    tx = RecordingTx()
    record_change(tx, _ctx(), unit_type=unit_type, op=op, key=key, before=before, after=after)  # type: ignore[arg-type]
    return tx


def test_a_meal_content_event_with_the_meal_key_is_written() -> None:
    tx = _record("meal_content", "set", _meal_key(), BEFORE_MEAL, AFTER_MEAL)
    assert len(tx.calls) == 1


def test_a_dish_event_with_only_the_dish_is_written() -> None:
    tx = _record("dish", "status_change", EventKey(dish_id=DISH), {"st": "to_try"},
                 {"v": 1, "st": "tested"})  # fmt: skip
    assert len(tx.calls) == 1


@pytest.mark.parametrize(
    ("unit_type", "op", "key", "before", "after"),
    [
        # `dish` con colonne di un pasto o di una persona
        (
            "dish",
            "status_change",
            EventKey(dish_id=DISH, meal_date=DAY),
            {"st": "to_try"},
            {"v": 1, "st": "tested"},
        ),
        (
            "dish",
            "status_change",
            EventKey(dish_id=DISH, subject_person_id=PERSON),
            {"st": "to_try"},
            {"v": 1, "st": "tested"},
        ),
        (
            "dish",
            "status_change",
            EventKey(dish_id=DISH, meal_slot=3),
            {"st": "to_try"},
            {"v": 1, "st": "tested"},
        ),
        # `meal_content` con una persona o un piatto di troppo, o con una chiave incompleta
        (
            "meal_content",
            "set",
            _meal_key(subject_person_id=PERSON),
            BEFORE_MEAL,
            AFTER_MEAL,
        ),
        ("meal_content", "set", _meal_key(dish_id=DISH), BEFORE_MEAL, AFTER_MEAL),
        (
            "meal_content",
            "set",
            EventKey(meal_date=DAY, meal_type="dinner"),
            BEFORE_MEAL,
            AFTER_MEAL,
        ),
        ("meal_content", "set", EventKey(meal_date=DAY, meal_slot=0), BEFORE_MEAL, AFTER_MEAL),
        ("meal_content", "set", EventKey(), BEFORE_MEAL, AFTER_MEAL),
        # uno slot senza tipo di pasto, o fuori dominio
        (
            "meal_content",
            "set",
            EventKey(meal_date=DAY, meal_type="lunch", meal_slot=1),
            BEFORE_MEAL,
            AFTER_MEAL,
        ),
        (
            "meal_content",
            "set",
            EventKey(meal_date=DAY, meal_type="other", meal_slot=5),
            BEFORE_MEAL,
            AFTER_MEAL,
        ),
        # `membership` con colonne di pasto
        (
            "membership",
            "role_change",
            EventKey(subject_person_id=PERSON, meal_date=DAY),
            {"r": "member"},
            {"v": 1, "r": "planner"},
        ),
        ("membership", "role_change", EventKey(), {"r": "member"}, {"v": 1, "r": "planner"}),
    ],
)
def test_a_key_that_does_not_match_the_unit_type_is_refused_before_any_write(
    unit_type: str, op: str, key: EventKey, before: Any, after: Any
) -> None:
    tx = RecordingTx()
    with pytest.raises(ValueError):  # noqa: PT011  (CodecError e l'errore di chiave sono ValueError)
        record_change(tx, _ctx(), unit_type=unit_type, op=op, key=key, before=before, after=after)  # type: ignore[arg-type]
    assert tx.calls == [], "nessun INSERT con una chiave incoerente"
