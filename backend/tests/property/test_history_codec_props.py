"""Proprietà del codec v1 (Hypothesis): invertibilità, compattezza, purezza (SL-05).

ADR-0012: «per ogni campo o voce cambiati si salvano sia il valore prima sia quello dopo. Così lo
stato di un'unità in un istante passato si ricostruisce partendo dallo stato attuale e annullando
a ritroso gli eventi successivi. [...] Un test di proprietà (Hypothesis) verifica che "stato
attuale meno gli eventi successivi a t" coincida con lo stato registrato a t.» (KPI-1, KPI-2);
05-data §4.2: «un test di proprietà verifica che la ricostruzione coincida con lo stato salvato»,
«solo gli elementi e i campi cambiati». 08 §8.2: profilo `ci-small`, derandomizzato.

Il contratto di `menu.history.codec` (`diff`, `apply`, `revert`, `validate`, stati nelle chiavi
brevi) è descritto in `tests/unit/test_history_codec.py`.
"""

import json
from collections.abc import Callable
from copy import deepcopy
from types import ModuleType
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

pytestmark = pytest.mark.property

PROFILE = settings(max_examples=60, derandomize=True, deadline=None)

IDS = [f"{n}{n}{n}{n}{n}{n}{n}{n}-{n}{n}{n}{n}-4{n}{n}{n}-8{n}{n}{n}-{n * 12}" for n in "1234"]
DISHES = [f"d{n}{n}{n}{n}{n}{n}{n}-dddd-4ddd-8ddd-{n * 12}" for n in "0123"]
COURSES = [f"c{n}{n}{n}{n}{n}{n}{n}-cccc-4ccc-8ccc-{n * 12}" for n in "0123"]
MEALS = ("breakfast", "lunch", "snack", "dinner")  # niente `other` (ASM-032)
TEXT = st.text(alphabet=st.characters(blacklist_categories=["Cs"], blacklist_characters="\x00"),
               min_size=1, max_size=20)  # fmt: skip


@st.composite
def item(draw: st.DrawFn) -> dict[str, Any]:
    """Una voce valida: piatto con portata, oppure testo libero (CK di forma di 05-data)."""
    position = draw(st.integers(0, 5))
    if draw(st.booleans()):
        return {
            "p": position,
            "d": draw(st.sampled_from(DISHES)),
            "c": draw(st.sampled_from(COURSES)),
            "t": None,
            "n": draw(st.booleans()),
        }
    return {"p": position, "d": None, "c": None, "t": draw(TEXT), "n": False}


def _meal_content() -> st.SearchStrategy[dict[str, Any]]:
    return st.fixed_dictionaries(
        {
            "i": st.dictionaries(st.sampled_from(IDS), item(), max_size=4),
            "s": st.sampled_from([None, "away", "restaurant", "skipped"]),
            "pr": st.sampled_from(["inherit", "added", "removed"]),
            "nm": st.one_of(st.none(), TEXT),
        }
    )


STATES: dict[str, st.SearchStrategy[dict[str, Any]]] = {
    "dish": st.fixed_dictionaries(
        {"st": st.sampled_from(["to_try", "tested"]), "ar": st.booleans()}
    ),
    "meal_guests": st.fixed_dictionaries(
        {"g": st.integers(0, 20), "gn": st.one_of(st.none(), TEXT)}
    ),
    "attendance": st.fixed_dictionaries({"p": st.sampled_from([True, False, None])}),
    "membership": st.fixed_dictionaries({"r": st.sampled_from(["admin", "planner", "member"])}),
    "typical_week": st.fixed_dictionaries(
        {
            "a": st.sets(st.tuples(st.integers(1, 7), st.sampled_from(MEALS)), max_size=8).map(
                lambda cells: [list(c) for c in sorted(cells)]
            )
        }
    ),
    "meal_content": _meal_content(),
}
# L'operazione con cui si registra il cambiamento di ciascun tipo (basta una valida per tipo).
OPS = {
    "dish": "status_change",
    "meal_guests": "set",
    "attendance": "set",
    "membership": "role_change",
    "typical_week": "set",
    "meal_content": "set",
}
UNITS = sorted(STATES)


@pytest.fixture(scope="module")
def codec() -> ModuleType:
    import importlib

    return importlib.import_module("menu.history.codec")


def _short_keys_of(payload: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(payload, dict):
        keys |= set(payload)
        for value in payload.values():
            keys |= _short_keys_of(value)
    elif isinstance(payload, list):
        for value in payload:
            keys |= _short_keys_of(value)
    return keys


def _changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    return old != new


Prop = Callable[..., None]


def for_each_unit(prop: Prop) -> Prop:
    """Parametrizza per tipo di unità e genera due stati per tipo."""

    @pytest.mark.parametrize("unit", UNITS)
    def run(codec: ModuleType, unit: str) -> None:
        @PROFILE
        @given(old=STATES[unit], new=STATES[unit])
        def inner(old: dict[str, Any], new: dict[str, Any]) -> None:
            prop(codec, unit, old, new)

        inner()

    run.__name__ = prop.__name__
    run.__doc__ = prop.__doc__
    return run


@for_each_unit
def test_a_diff_is_a_valid_v1_payload_and_applying_it_forward_gives_the_new_state(
    codec: ModuleType, unit: str, old: dict[str, Any], new: dict[str, Any]
) -> None:
    assume(_changed(old, new))
    before, after = codec.diff(unit, old, new)
    codec.validate(unit, OPS[unit], before, after)
    assert after["v"] == 1
    assert codec.apply(unit, old, before, after) == new


@for_each_unit
def test_reverting_a_diff_from_the_new_state_gives_the_old_state(
    codec: ModuleType, unit: str, old: dict[str, Any], new: dict[str, Any]
) -> None:
    """Invertibilità (ADR-0012): il `before` basta a tornare indietro, senza altra informazione."""
    assume(_changed(old, new))
    before, after = codec.diff(unit, old, new)
    assert codec.revert(unit, new, before, after) == old


@for_each_unit
def test_a_payload_survives_a_json_round_trip_unchanged(
    codec: ModuleType, unit: str, old: dict[str, Any], new: dict[str, Any]
) -> None:
    """Si salva come jsonb: ciò che si rilegge deve decodificare allo stesso modo."""
    assume(_changed(old, new))
    before, after = codec.diff(unit, old, new)
    stored_before = json.loads(json.dumps(before))
    stored_after = json.loads(json.dumps(after))
    assert codec.revert(unit, new, stored_before, stored_after) == old
    assert codec.apply(unit, old, stored_before, stored_after) == new


@for_each_unit
def test_only_the_documented_short_keys_ever_appear_in_a_payload(
    codec: ModuleType, unit: str, old: dict[str, Any], new: dict[str, Any]
) -> None:
    """SR-047: chiavi brevi del tipo, `v`, `id` delle voci e i campi delle voci; nient'altro."""
    assume(_changed(old, new))
    before, after = codec.diff(unit, old, new)
    allowed = set(codec.KEYS[unit]) | {"v", "id", "p", "d", "c", "t", "n"}
    assert _short_keys_of(before) | _short_keys_of(after) <= allowed
    assert "v" not in (before or {}), "la versione sta solo in `after`"


@for_each_unit
def test_diff_neither_mutates_its_inputs_nor_shares_structure_with_them(
    codec: ModuleType, unit: str, old: dict[str, Any], new: dict[str, Any]
) -> None:
    assume(_changed(old, new))
    snapshot = deepcopy((old, new))
    before, after = codec.diff(unit, old, new)
    assert (old, new) == snapshot
    for payload in (before, after):  # svuotare l'output non deve toccare gli stati di partenza
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    value.clear()
            payload.clear()
    assert (old, new) == snapshot


# --- compattezza: solo ciò che è cambiato (05-data §4.2, stima di spazio §14) --------------------


@given(old=STATES["dish"], new=STATES["dish"])
@PROFILE
def test_a_dish_payload_names_exactly_the_changed_fields(
    codec: ModuleType, old: dict[str, Any], new: dict[str, Any]
) -> None:
    assume(_changed(old, new))
    before, after = codec.diff("dish", old, new)
    changed = {k for k in old if old[k] != new[k]}
    assert set(before) == changed
    assert set(after) == changed | {"v"}
    assert all(before[k] == old[k] and after[k] == new[k] for k in changed)


@given(old=STATES["meal_content"], new=STATES["meal_content"])
@PROFILE
def test_unchanged_items_never_appear_in_a_meal_content_payload(
    codec: ModuleType, old: dict[str, Any], new: dict[str, Any]
) -> None:
    assume(_changed(old, new))
    before, after = codec.diff("meal_content", old, new)
    mentioned = {entry["id"] for p in (before, after) if p for entry in p.get("i", [])}
    unchanged = {i for i in old["i"] if i in new["i"] and old["i"][i] == new["i"][i]}
    assert not mentioned & unchanged
    added = set(new["i"]) - set(old["i"])
    removed = set(old["i"]) - set(new["i"])
    in_before = {e["id"] for e in (before or {}).get("i", [])}
    in_after = {e["id"] for e in after.get("i", [])}
    assert not in_before & added, "una voce aggiunta compare solo in after"
    assert not in_after & removed, "una voce tolta compare solo in before"


@for_each_unit
def test_lists_are_sorted_and_single_value_units_have_before_keys_equal_to_after_keys(
    codec: ModuleType, unit: str, old: dict[str, Any], new: dict[str, Any]
) -> None:
    """V1 fissa l'ordine (`i` per id, `a` per [giorno, pasto]); fuori dalle liste `before` ha
    esattamente le chiavi di `after` meno `v`, così l'evento si annulla."""
    assume(_changed(old, new))
    before, after = codec.diff(unit, old, new)
    for payload in (before, after):
        for entry in (payload or {}).get("i", []):
            assert entry["id"] in IDS
        ids = [e["id"] for e in (payload or {}).get("i", [])]
        assert ids == sorted(ids)
        cells = (payload or {}).get("a", [])
        assert cells == sorted(cells)
    if unit in {"dish", "meal_guests", "attendance", "membership"}:
        assert before is not None
        assert set(before) == set(after) - {"v"}
    if unit == "meal_content":
        scalars_before = set(before or {}) - {"i"}
        assert scalars_before == set(after) - {"i", "v"}


@given(old=STATES["meal_content"], new=STATES["meal_content"])
@PROFILE
def test_null_fields_are_omitted_only_in_added_or_removed_items(
    codec: ModuleType, old: dict[str, Any], new: dict[str, Any]
) -> None:
    """Voce aggiunta o tolta: nessun campo nullo. Voce modificata: solo i campi cambiati, e un
    campo che diventa nullo compare con `null` (assente = invariato)."""
    assume(_changed(old, new))
    before, after = codec.diff("meal_content", old, new)
    added = set(new["i"]) - set(old["i"])
    removed = set(old["i"]) - set(new["i"])
    for payload, gone in ((after, added), ((before or {}), removed)):
        for entry in payload.get("i", []):
            if entry["id"] in gone:
                assert None not in entry.values(), entry
    for entry in after.get("i", []):
        if entry["id"] in old["i"] and entry["id"] in new["i"]:
            changed = {
                k
                for k in new["i"][entry["id"]]
                if new["i"][entry["id"]][k] != old["i"][entry["id"]][k]
            }
            assert set(entry) - {"id"} == changed


# --- ricostruzione di uno stato passato (KPI-1): sequenze di eventi ------------------------------


@pytest.mark.parametrize("unit", UNITS)
def test_the_state_at_any_past_instant_is_rebuilt_by_undoing_the_later_events(
    codec: ModuleType, unit: str
) -> None:
    """«Stato attuale meno gli eventi successivi a t» = stato registrato a t (ADR-0012, KPI-1)."""

    @PROFILE
    @given(history=st.lists(STATES[unit], min_size=2, max_size=8))
    def inner(history: list[dict[str, Any]]) -> None:
        states = [history[0]]
        events = []
        for nxt in history[1:]:
            if nxt == states[-1]:
                continue
            events.append(codec.diff(unit, states[-1], nxt))
            states.append(nxt)
        current = states[-1]
        for k in range(len(states) - 1, 0, -1):
            before, after = events[k - 1]
            current = codec.revert(unit, current, before, after)
            assert current == states[k - 1], f"ricostruzione errata all'evento {k}"
        forward = states[0]
        for before, after in events:
            forward = codec.apply(unit, forward, before, after)
        assert forward == states[-1], "la riapplicazione in avanti non coincide"

    inner()
