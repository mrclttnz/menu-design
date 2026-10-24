"""Codec v1 degli eventi di modifica: validazione, formato permanente, fixture dorate (SL-05).

ADR-0012 (formato compatto e versionato, `"v": 1` in `after`, modelli per `unit_type`/`op`/`v`),
05-data §4.2 (tabella delle chiavi brevi, "elementi cambiati soltanto"), AC-028.5 (il formato v1
è permanente: gli eventi di M0 restano leggibili), SR-047 (nessun nome o email negli eventi),
SR-022. 08 §5.4: le fixture dorate in `tests/fixtures/codec_v1/*.json` sono committate; se il
formato cambia queste prove falliscono.

CONTRATTO ASSUNTO (il piano non fissa i nomi: il backend-developer deve confermarli o
proporre una modifica a QUESTO file prima di scrivere codice; vedi il report del tester):

    menu.history.codec
        CODEC_VERSION == 1
        KEYS: Mapping[str, Collection[str]]   unit_type -> chiavi brevi ammesse (tabella unica)
        class CodecError(ValueError)
        validate(unit_type, op, before, after) -> None       solleva CodecError se non conforme
        diff(unit_type, old_state, new_state) -> (before | None, after)   solo i campi cambiati
        apply(unit_type, state, before, after) -> state      in avanti (usa `after`)
        revert(unit_type, state, before, after) -> state     a ritroso (usa `before`)

Gli stati sono dizionari nelle CHIAVI BREVI, funzioni pure che non modificano gli argomenti:
    dish {st, ar} · meal_guests {g, gn} · attendance {p} · membership {r}
    typical_week {a: [[iso_dow, tipo_pasto], ...] ordinate}
    meal_content {i: {id_voce: {p, d, c, t, n}}, pr, nm}
"""

import importlib
import json
from copy import deepcopy
from types import ModuleType
from typing import Any

import pytest

from support.paths import TESTS

ID1 = "11111111-1111-4111-8111-111111111111"
ID2 = "22222222-2222-4222-8222-222222222222"
D1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
C1 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
FIXTURES = sorted((TESTS / "fixtures" / "codec_v1").glob("*.json"))


@pytest.fixture
def codec() -> ModuleType:
    return importlib.import_module("menu.history.codec")


def _error(codec: ModuleType) -> type[Exception]:
    err: type[Exception] = codec.CodecError
    return err


# --- contratto del modulo -------------------------------------------------------------------------


def test_the_codec_is_version_1_and_the_error_is_a_value_error(codec: ModuleType) -> None:
    assert codec.CODEC_VERSION == 1
    assert issubclass(codec.CodecError, ValueError)


def test_the_short_keys_live_in_one_table_with_the_documented_keys(codec: ModuleType) -> None:
    """05-data §4.2: una sola tabella delle chiavi brevi; l'insieme v1 è permanente."""
    expected = {
        "meal_content": {"i", "s", "pr", "nm"},
        "meal_guests": {"g", "gn"},
        "attendance": {"p"},
        "typical_week": {"a"},
        "dish": {"st", "ar"},
        "membership": {"r"},
    }
    assert {unit: set(keys) for unit, keys in codec.KEYS.items()} == expected


# --- payload conformi -----------------------------------------------------------------------------

VALID = [
    ("dish", "status_change", {"st": "to_try"}, {"v": 1, "st": "tested"}),
    ("dish", "status_change", {"st": "tested"}, {"v": 1, "st": "to_try"}),
    ("dish", "archive", {"ar": False}, {"v": 1, "ar": True}),
    ("dish", "restore", {"ar": True}, {"v": 1, "ar": False}),
    ("attendance", "set", {"p": None}, {"v": 1, "p": True}),
    ("attendance", "clear", {"p": False}, {"v": 1, "p": None}),
    ("meal_guests", "set", {"g": 0}, {"v": 1, "g": 2}),
    ("meal_content", "set", {"pr": "inherit"}, {"v": 1, "pr": "added"}),
    ("meal_content", "set", {"pr": "added"}, {"v": 1, "pr": "removed"}),
    ("meal_content", "set", {"s": None}, {"v": 1, "s": "away"}),
    ("meal_content", "set", {"s": "restaurant"}, {"v": 1, "s": None}),
    ("meal_content", "set", {"s": "skipped", "nm": None}, {"v": 1, "s": None, "nm": "Merenda"}),
    ("typical_week", "set", {"a": [[2, "dinner"]]}, {"v": 1, "a": [[1, "lunch"], [5, "dinner"]]}),
    ("meal_guests", "set", {"g": 2, "gn": None}, {"v": 1, "g": 3, "gn": "due bambini"}),
    ("membership", "role_change", {"r": "member"}, {"v": 1, "r": "planner"}),
    ("typical_week", "set", None, {"v": 1, "a": [[1, "lunch"]]}),
    ("meal_content", "set", None, {"v": 1, "i": [{"id": ID1, "p": 1, "d": D1, "c": C1}]}),
    ("meal_content", "clear", {"i": [{"id": ID1, "p": 1, "d": D1, "c": C1}]}, {"v": 1}),
]


@pytest.mark.parametrize(("unit", "op", "before", "after"), VALID)
def test_conforming_payloads_are_accepted(
    codec: ModuleType, unit: str, op: str, before: Any, after: Any
) -> None:
    assert codec.validate(unit, op, before, after) is None


@pytest.mark.parametrize(("unit", "op", "before", "after"), VALID)
def test_validation_does_not_modify_its_arguments(
    codec: ModuleType, unit: str, op: str, before: Any, after: Any
) -> None:
    b, a = deepcopy(before), deepcopy(after)
    codec.validate(unit, op, before, after)
    assert (before, after) == (b, a)


INVALID = [
    # versione
    ("dish", "status_change", {"st": "to_try"}, {"st": "tested"}, "senza v"),
    ("dish", "status_change", {"st": "to_try"}, {"v": 2, "st": "tested"}, "v sconosciuta"),
    ("dish", "status_change", {"st": "to_try"}, {"v": 0, "st": "tested"}, "v zero"),
    ("dish", "status_change", {"st": "to_try"}, {"v": "1", "st": "tested"}, "v stringa"),
    ("dish", "status_change", {"st": "to_try"}, {"v": True, "st": "tested"}, "v booleano"),
    ("dish", "status_change", {"st": "to_try"}, {"v": 1.0, "st": "tested"}, "v decimale"),
    # forma
    ("dish", "status_change", {"st": "to_try"}, None, "after assente"),
    ("dish", "status_change", {"st": "to_try"}, [], "after non è un oggetto"),
    ("dish", "status_change", None, {"v": 1, "st": "tested"}, "manca il valore prima"),
    ("dish", "status_change", {"st": "to_try"}, {"v": 1}, "after senza il campo cambiato"),
    ("dish", "status_change", {}, {"v": 1, "st": "tested"}, "before vuoto"),
    # chiavi: solo quelle brevi del tipo (SR-047: nessun nome o email nemmeno per sbaglio)
    ("dish", "status_change", {"st": "to_try"}, {"v": 1, "st": "tested", "x": 1}, "chiave ignota"),
    ("dish", "status_change", {"st": "to_try"}, {"v": 1, "st": "tested", "ar": True}, "ar altrui"),
    ("dish", "status_change", {"status": "to_try"}, {"v": 1, "status": "tested"}, "chiave lunga"),
    ("dish", "status_change", {"st": "to_try"}, {"v": 1, "st": "tested", "name": "Pasta"}, "nome"),
    (
        "dish",
        "status_change",
        {"st": "to_try"},
        {"v": 1, "st": "tested", "email": "a@b.c"},
        "email",
    ),
    (
        "membership",
        "role_change",
        {"r": "member", "display_name": "Mario"},
        {"v": 1, "r": "planner"},
        "nome in before",
    ),
    # valori
    ("dish", "status_change", {"st": "to_try"}, {"v": 1, "st": "cooked"}, "stato ignoto"),
    ("dish", "status_change", {"st": "to_try"}, {"v": 1, "st": None}, "stato nullo"),
    ("dish", "archive", {"ar": False}, {"v": 1, "ar": "yes"}, "ar non booleano"),
    ("dish", "archive", {"ar": False}, {"v": 1, "ar": 1}, "ar intero"),
    ("membership", "role_change", {"r": "member"}, {"v": 1, "r": "owner"}, "ruolo ignoto"),
    ("meal_guests", "set", {"g": 0}, {"v": 1, "g": -1}, "ospiti negativi"),
    ("meal_guests", "set", {"g": 0}, {"v": 1, "g": True}, "ospiti booleano"),
    ("meal_guests", "set", {"g": 0}, {"v": 1, "g": "2"}, "ospiti stringa"),
    ("attendance", "set", {"p": None}, {"v": 1, "p": "maybe"}, "presenza ignota"),
    ("typical_week", "set", None, {"v": 1, "a": [[8, "lunch"]]}, "giorno 8"),
    ("typical_week", "set", None, {"v": 1, "a": [[0, "lunch"]]}, "giorno 0"),
    ("typical_week", "set", None, {"v": 1, "a": [[1, "brunch"]]}, "pasto ignoto"),
    ("typical_week", "set", None, {"v": 1, "a": [[1, "other"]]}, "niente other (ASM-032)"),
    ("meal_content", "set", None, {"v": 1, "i": [{"p": 1, "d": D1, "c": C1}]}, "voce senza id"),
    ("meal_content", "set", None, {"v": 1, "i": [{"id": "x", "p": 1}]}, "id non UUID"),
    (
        "meal_content",
        "set",
        None,
        {"v": 1, "i": [{"id": ID1, "dish_name": "Pasta"}]},
        "nome piatto",
    ),
    # unità a valore singolo: `before` ha ESATTAMENTE le chiavi di `after` meno `v` (annullabile)
    ("meal_guests", "set", None, {"v": 1, "g": 2}, "ospiti senza before"),
    ("meal_guests", "set", {"g": 0}, {"v": 1, "g": 2, "gn": "x"}, "before senza gn"),
    ("meal_guests", "set", {"g": 0, "gn": None}, {"v": 1, "g": 2}, "before con gn in più"),
    ("meal_guests", "set", {"gn": None}, {"v": 1, "g": 2}, "chiavi diverse"),
    ("attendance", "set", None, {"v": 1, "p": True}, "presenza senza before"),
    ("membership", "role_change", None, {"v": 1, "r": "planner"}, "ruolo senza before"),
    ("dish", "archive", None, {"v": 1, "ar": True}, "archivio senza before"),
    ("dish", "archive", {"ar": False, "st": "tested"}, {"v": 1, "ar": True}, "before con st"),
    # presenza del pasto (3 valori) e stato speciale (4 valori)
    ("meal_content", "set", {"pr": True}, {"v": 1, "pr": False}, "pr booleano"),
    ("meal_content", "set", {"pr": "inherit"}, {"v": 1, "pr": "maybe"}, "pr ignoto"),
    ("meal_content", "set", {"pr": "inherit"}, {"v": 1, "pr": None}, "pr nullo"),
    ("meal_content", "set", {"s": None}, {"v": 1, "s": "holiday"}, "stato speciale ignoto"),
    # ordine fissato dal formato v1: `i` per id, `a` per [giorno, pasto]
    (
        "meal_content",
        "set",
        None,
        {"v": 1, "i": [{"id": ID2, "p": 1, "n": False}, {"id": ID1, "p": 0, "n": False}]},
        "voci non ordinate per id",
    ),
    (
        "typical_week",
        "set",
        None,
        {"v": 1, "a": [[5, "dinner"], [1, "lunch"]]},
        "celle non ordinate",
    ),
    ("typical_week", "set", None, {"v": 1, "a": [[1, "lunch"], [1, "lunch"]]}, "celle duplicate"),
    # tipo di unità e operazione
    ("meal", "set", None, {"v": 1}, "unità ignota"),
    ("dish", "set", {"st": "to_try"}, {"v": 1, "st": "tested"}, "operazione di un'altra unità"),
    ("membership", "status_change", {"r": "member"}, {"v": 1, "r": "admin"}, "op sbagliata"),
    ("dish", "role_change", {"st": "to_try"}, {"v": 1, "st": "tested"}, "role_change su dish"),
]


@pytest.mark.parametrize(
    ("unit", "op", "before", "after", "why"), INVALID, ids=[row[4] for row in INVALID]
)
def test_non_conforming_payloads_are_refused(
    codec: ModuleType, unit: str, op: str, before: Any, after: Any, why: str
) -> None:
    """Un payload non conforme fa fallire la transazione (ADR-0012): qui, `CodecError`."""
    with pytest.raises(_error(codec)):
        codec.validate(unit, op, before, after)


def test_each_status_change_payload_is_small_and_names_only_the_changed_field(
    codec: ModuleType,
) -> None:
    before, after = codec.diff("dish", {"st": "to_try", "ar": False}, {"st": "tested", "ar": False})
    assert before == {"st": "to_try"}
    assert after == {"v": 1, "st": "tested"}, "il campo non cambiato (ar) non compare (05-data)"
    assert len(json.dumps(before)) + len(json.dumps(after)) < 100


# --- diff, apply, revert: esempi (le proprietà generali sono in tests/property) -------------------


def test_adding_an_item_appears_only_in_after_and_removing_only_in_before(
    codec: ModuleType,
) -> None:
    """Nelle voci aggiunte o tolte i campi nulli si omettono (come nelle fixture dorate)."""
    item = {"p": 0, "d": D1, "c": C1, "t": None, "n": False}
    before, after = codec.diff("meal_content", {"i": {}}, {"i": {ID1: item}})
    assert before is None
    assert after == {"v": 1, "i": [{"id": ID1, "p": 0, "d": D1, "c": C1, "n": False}]}
    before2, after2 = codec.diff("meal_content", {"i": {ID1: item}}, {"i": {}})
    assert before2 == {"i": [{"id": ID1, "p": 0, "d": D1, "c": C1, "n": False}]}
    assert after2 == {"v": 1}


def test_a_free_text_item_omits_its_null_dish_and_course_when_added(codec: ModuleType) -> None:
    item = {"p": 2, "d": None, "c": None, "t": "Pane e olio", "n": False}
    _, after = codec.diff("meal_content", {"i": {}}, {"i": {ID1: item}})
    assert after == {"v": 1, "i": [{"id": ID1, "p": 2, "t": "Pane e olio", "n": False}]}
    assert codec.apply("meal_content", {"i": {}}, None, after) == {"i": {ID1: item}}


def test_a_modified_item_appears_in_both_with_only_the_changed_fields_and_its_id(
    codec: ModuleType,
) -> None:
    old = {"i": {ID1: {"p": 0, "d": D1, "c": C1, "t": None, "n": False}}}
    new = {"i": {ID1: {"p": 2, "d": D1, "c": C1, "t": None, "n": True}}}
    before, after = codec.diff("meal_content", old, new)
    assert before == {"i": [{"id": ID1, "p": 0, "n": False}]}
    assert after == {"v": 1, "i": [{"id": ID1, "p": 2, "n": True}]}


def test_in_a_modified_item_a_field_that_becomes_null_is_written_explicitly(
    codec: ModuleType,
) -> None:
    """Qui un campo assente significa «invariato»: il passaggio a nullo si scrive `null`."""
    old = {"i": {ID1: {"p": 0, "d": D1, "c": C1, "t": None, "n": False}}}
    new = {"i": {ID1: {"p": 0, "d": None, "c": None, "t": "Pane", "n": False}}}
    before, after = codec.diff("meal_content", old, new)
    assert before == {"i": [{"id": ID1, "d": D1, "c": C1, "t": None}]}
    assert after == {"v": 1, "i": [{"id": ID1, "d": None, "c": None, "t": "Pane"}]}
    assert codec.revert("meal_content", new, before, after) == old


def test_list_items_are_sorted_in_v1_items_by_id_and_cells_by_day_then_meal(
    codec: ModuleType,
) -> None:
    item = {"p": 0, "d": D1, "c": C1, "t": None, "n": False}
    new = {"i": {ID2: item, ID1: item}}  # inserite in ordine inverso
    _, after = codec.diff("meal_content", {"i": {}}, new)
    assert [e["id"] for e in after["i"]] == [ID1, ID2]
    before, _ = codec.diff("meal_content", new, {"i": {}})
    assert [e["id"] for e in before["i"]] == [ID1, ID2]
    cells = [[5, "dinner"], [1, "lunch"], [1, "breakfast"], [3, "snack"]]
    _, after_tw = codec.diff("typical_week", {"a": []}, {"a": cells})
    assert after_tw["a"] == [[1, "breakfast"], [1, "lunch"], [3, "snack"], [5, "dinner"]]
    before_tw, _ = codec.diff("typical_week", {"a": cells}, {"a": []})
    assert before_tw["a"] == after_tw["a"]


def test_the_presence_code_and_the_special_state_are_scalars_written_in_both_sides(
    codec: ModuleType,
) -> None:
    old: dict[str, Any] = {"i": {}, "s": None, "pr": "inherit", "nm": None}
    new: dict[str, Any] = {"i": {}, "s": "away", "pr": "added", "nm": None}
    before, after = codec.diff("meal_content", old, new)
    assert before == {"s": None, "pr": "inherit"}
    assert after == {"v": 1, "s": "away", "pr": "added"}


@pytest.mark.parametrize("unit", ["dish", "meal_guests", "attendance", "membership"])
def test_single_value_units_always_have_before_with_the_keys_of_after(
    codec: ModuleType, unit: str
) -> None:
    samples: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
        "dish": ({"st": "to_try", "ar": False}, {"st": "tested", "ar": True}),
        "meal_guests": ({"g": 0, "gn": None}, {"g": 2, "gn": None}),
        "attendance": ({"p": None}, {"p": True}),
        "membership": ({"r": "member"}, {"r": "admin"}),
    }
    old, new = samples[unit]
    before, after = codec.diff(unit, old, new)
    assert before is not None
    assert set(before) == set(after) - {"v"}


def test_functions_are_pure(codec: ModuleType) -> None:
    old, new = {"st": "to_try", "ar": False}, {"st": "tested", "ar": False}
    snapshot = deepcopy((old, new))
    before, after = codec.diff("dish", old, new)
    snap2 = deepcopy((before, after))
    codec.apply("dish", old, before, after)
    codec.revert("dish", new, before, after)
    assert (old, new) == snapshot
    assert (before, after) == snap2


# --- fixture dorate (08 §5.4, AC-028.5) -----------------------------------------------------------


def test_the_golden_fixtures_exist_for_every_unit_type() -> None:
    assert len(FIXTURES) >= 6
    covered = {json.loads(p.read_text(encoding="utf-8"))["unit_type"] for p in FIXTURES}
    assert covered == {
        "dish",
        "attendance",
        "meal_guests",
        "membership",
        "typical_week",
        "meal_content",
    }


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_golden_fixtures_still_decode_to_the_expected_states(codec: ModuleType, path: Any) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    unit, op = case["unit_type"], case["op"]
    codec.validate(unit, op, case["before"], case["after"])
    assert (
        codec.apply(unit, case["state_before"], case["before"], case["after"])
        == case["state_after"]
    )
    assert (
        codec.revert(unit, case["state_after"], case["before"], case["after"])
        == case["state_before"]
    )
    # e il formato scritto oggi dal codec coincide con quello committato (permanenza di v1)
    assert codec.diff(unit, case["state_before"], case["state_after"]) == (
        case["before"],
        case["after"],
    )


def test_the_golden_fixtures_contain_only_ids_and_values_never_names_or_emails() -> None:
    for path in FIXTURES:
        text = path.read_text(encoding="utf-8").lower()
        assert "@" not in text, path.name
        assert "email" not in text, path.name
