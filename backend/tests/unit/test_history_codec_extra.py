"""Rigore del codec v1 oltre gli esempi dei test di SL-05: stati incoerenti e `record_change`."""

from typing import Any
from uuid import uuid4

import pytest

from menu.common import RequestContext
from menu.history import EventKey, codec, record_change

ID1 = "11111111-1111-4111-8111-111111111111"
ID2 = "22222222-2222-4222-8222-222222222222"
D1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
C1 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _ctx(role: str | None = "planner") -> RequestContext:
    return RequestContext(
        correlation_id=uuid4(),
        account_id=uuid4(),
        session_id=uuid4(),
        auth_time=None,
        family_id=uuid4(),
        person_id=uuid4(),
        role=role,  # type: ignore[arg-type]
        family_status="active",
    )


def test_diff_of_identical_states_is_refused() -> None:
    with pytest.raises(codec.CodecError):
        codec.diff("dish", {"st": "to_try", "ar": False}, {"st": "to_try", "ar": False})
    with pytest.raises(codec.CodecError):
        codec.diff("typical_week", {"a": [[1, "lunch"]]}, {"a": [[1, "lunch"]]})


@pytest.mark.parametrize(
    "after",
    [
        {"v": 1, "a": []},
        {"v": 1, "a": [[1, "lunch"]]},
    ],
)
def test_typical_week_cells_cannot_be_both_removed_and_added_or_empty(after: Any) -> None:
    with pytest.raises(codec.CodecError):
        codec.validate("typical_week", "set", {"a": [[1, "lunch"]]}, after)


def test_an_empty_event_is_refused() -> None:
    with pytest.raises(codec.CodecError):
        codec.validate("meal_content", "set", None, {"v": 1})
    with pytest.raises(codec.CodecError):
        codec.validate("typical_week", "set", None, {"v": 1})


def test_duplicate_item_ids_and_whole_items_with_nulls_are_refused() -> None:
    item = {"id": ID1, "p": 0, "d": D1, "c": C1, "n": False}
    with pytest.raises(codec.CodecError):
        codec.validate("meal_content", "set", None, {"v": 1, "i": [item, item]})
    with pytest.raises(codec.CodecError):
        codec.validate("meal_content", "set", None, {"v": 1, "i": [{**item, "t": None}]})
    with pytest.raises(codec.CodecError):
        codec.validate("meal_content", "set", None, {"v": 1, "i": [{**item, "t": "Pane"}]})


def test_a_modified_item_must_name_the_same_changed_fields_on_both_sides() -> None:
    with pytest.raises(codec.CodecError):
        codec.validate(
            "meal_content",
            "set",
            {"i": [{"id": ID1, "p": 0}]},
            {"v": 1, "i": [{"id": ID1, "n": True}]},
        )
    with pytest.raises(codec.CodecError):
        codec.validate(
            "meal_content",
            "set",
            {"i": [{"id": ID1, "p": 1}]},
            {"v": 1, "i": [{"id": ID1, "p": 1}]},
        )


def test_applying_an_event_to_an_incoherent_state_is_refused() -> None:
    item = {"id": ID1, "p": 0, "d": D1, "c": C1, "n": False}
    with pytest.raises(codec.CodecError):
        codec.apply("meal_content", {"i": {}}, {"i": [item]}, {"v": 1})
    with pytest.raises(codec.CodecError):
        codec.revert("meal_content", {"i": {ID2: {}}}, None, {"v": 1, "i": [item]})


def test_record_change_validates_before_touching_the_database() -> None:
    with pytest.raises(codec.CodecError):
        record_change(
            None,  # type: ignore[arg-type]
            _ctx(),
            unit_type="dish",
            op="status_change",
            key=EventKey(dish_id=uuid4()),
            before={"st": "to_try"},
            after={"v": 1, "st": "cooked"},
        )


def test_record_change_needs_an_author_with_a_role() -> None:
    with pytest.raises(ValueError, match="persona"):
        record_change(
            None,  # type: ignore[arg-type]
            _ctx(role=None),
            unit_type="dish",
            op="status_change",
            key=EventKey(dish_id=uuid4()),
            before={"st": "to_try"},
            after={"v": 1, "st": "tested"},
        )
