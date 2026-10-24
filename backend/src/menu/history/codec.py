"""Codec v1 degli eventi di modifica: formato compatto, permanente e invertibile (ADR-0012).

Un evento porta `before` e `after` con chiavi brevi e solo ciò che è cambiato (05-data §4.2);
`after` porta anche la versione del formato (`"v": 1`). Il formato v1 non cambia mai: una
versione nuova si aggiunge accanto, e il decodificatore le gestisce tutte (AC-028.5).

Gli stati sono dizionari nelle chiavi brevi e le funzioni sono pure: non modificano gli argomenti
e non ne condividono la struttura con il risultato.

    dish {st, ar} · meal_guests {g, gn} · attendance {p} · membership {r}
    typical_week {a: [[iso_dow, tipo_pasto], ...] ordinate}
    meal_content {i: {id_voce: {p, d, c, t, n}}, s, pr, nm}

Regole del formato v1:
- unità a valore singolo (`dish`, `meal_guests`, `attendance`, `membership`): `before` esiste
  sempre e ha le stesse chiavi di `after` meno `v`, così l'evento si annulla;
- `typical_week`: `a` elenca le celle assenti aggiunte (in `after`) o tolte (in `before`);
- `meal_content`: `i` elenca le voci. Una voce solo in `after` è aggiunta, solo in `before` è
  tolta (campi nulli omessi), in entrambi è modificata (solo i campi cambiati più `id`: un campo
  assente significa «invariato», il passaggio a nullo si scrive `null`). `s`, `pr` e `nm` sono
  scalari scritti da entrambe le parti; `pr` è il codice di presenza, mai un booleano;
- `i` è ordinato per id della voce, `a` per [giorno, pasto come stringa]; senza duplicati;
- nessun nome né email: solo identificativi, codici e i testi liberi del pasto (SR-047).

Un payload non conforme solleva `CodecError`: la transazione che lo scrive fallisce.
"""

import itertools
from collections.abc import Mapping
from copy import deepcopy
from typing import Any
from uuid import UUID

CODEC_VERSION = 1

KEYS: Mapping[str, frozenset[str]] = {
    "meal_content": frozenset({"i", "s", "pr", "nm"}),
    "meal_guests": frozenset({"g", "gn"}),
    "attendance": frozenset({"p"}),
    "typical_week": frozenset({"a"}),
    "dish": frozenset({"st", "ar"}),
    "membership": frozenset({"r"}),
}

OPERATIONS: Mapping[str, frozenset[str]] = {
    "meal_content": frozenset({"set", "clear", "move", "swap", "copy"}),
    "meal_guests": frozenset({"set", "clear"}),
    "attendance": frozenset({"set", "clear"}),
    "typical_week": frozenset({"set", "clear"}),
    "dish": frozenset({"status_change", "archive", "restore"}),
    "membership": frozenset({"role_change"}),
}

_SINGLE_VALUE = frozenset({"dish", "meal_guests", "attendance", "membership"})
_ITEM_FIELDS = ("p", "d", "c", "t", "n")
_MEAL_SCALARS = ("s", "pr", "nm")
_DEFAULT_ITEM: Mapping[str, Any] = {"p": 0, "d": None, "c": None, "t": None, "n": False}

_DISH_STATUS = frozenset({"to_try", "tested"})
_ROLES = frozenset({"admin", "planner", "member"})
_SPECIAL_STATES = frozenset({"away", "restaurant", "skipped"})
_PRESENCE = frozenset({"inherit", "added", "removed"})
_TYPICAL_MEALS = frozenset({"breakfast", "lunch", "snack", "dinner"})  # niente `other` (ASM-032)
_TEXT_MAX = 200
_NAME_MAX = 40


class CodecError(ValueError):
    """Payload non conforme al formato v1, o stato incoerente con l'evento."""


def _fail(message: str) -> CodecError:
    return CodecError(message)


# --- valori --------------------------------------------------------------------------------------


def _is_int(value: object) -> bool:
    return type(value) is int


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _is_text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= maximum and "\x00" not in value


def _is_optional_text(value: object, maximum: int) -> bool:
    return value is None or _is_text(value, maximum)


def _scalar_ok(key: str, value: object) -> bool:
    """Il valore ammesso per una chiave scalare (non lista)."""
    if key == "st":
        return isinstance(value, str) and value in _DISH_STATUS
    if key == "ar":
        return isinstance(value, bool)
    if key == "p":
        return value is None or isinstance(value, bool)
    if key == "r":
        return isinstance(value, str) and value in _ROLES
    if key == "g":
        return _is_int(value) and isinstance(value, int) and value >= 0
    if key == "gn":
        return _is_optional_text(value, _TEXT_MAX)
    if key == "s":
        return value is None or (isinstance(value, str) and value in _SPECIAL_STATES)
    if key == "pr":
        return isinstance(value, str) and value in _PRESENCE
    if key == "nm":
        return _is_optional_text(value, _NAME_MAX)
    return False


def _item_field_ok(field: str, value: object) -> bool:
    if field == "p":
        return _is_int(value) and isinstance(value, int) and value >= 0
    if field in {"d", "c"}:
        return value is None or _is_uuid(value)
    if field == "t":
        return _is_optional_text(value, _TEXT_MAX)
    return isinstance(value, bool)  # n


# --- validazione ---------------------------------------------------------------------------------


def _payload_keys(payload: Mapping[str, Any] | None) -> set[str]:
    return set() if payload is None else set(payload)


def validate(unit_type: str, op: str, before: Any, after: Any) -> None:
    """Solleva `CodecError` se (`before`, `after`) non è un payload v1 valido per unità e op."""
    if unit_type not in KEYS:
        raise _fail("tipo di unità sconosciuto")
    if op not in OPERATIONS[unit_type]:
        raise _fail("operazione non ammessa per l'unità")
    if not isinstance(after, dict):
        raise _fail("after deve essere un oggetto")
    version = after.get("v")
    if not _is_int(version) or version != CODEC_VERSION:
        raise _fail("versione del formato assente o sconosciuta")
    if before is not None and (not isinstance(before, dict) or not before):
        raise _fail("before deve essere assente o un oggetto non vuoto")
    allowed = KEYS[unit_type]
    after_keys = set(after) - {"v"}
    before_keys = _payload_keys(before)
    if not (after_keys | before_keys) <= allowed:
        raise _fail("chiave non ammessa")
    if unit_type in _SINGLE_VALUE:
        _validate_single(before, after, after_keys, before_keys)
    elif unit_type == "typical_week":
        _validate_typical_week(before, after)
    else:
        _validate_meal_content(before, after, after_keys, before_keys)


def _validate_single(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    after_keys: set[str],
    before_keys: set[str],
) -> None:
    if before is None or not after_keys or before_keys != after_keys:
        raise _fail("before ha esattamente le chiavi di after meno v")
    for key in after_keys:
        if not _scalar_ok(key, before[key]) or not _scalar_ok(key, after[key]):
            raise _fail("valore non ammesso")


def _cells(payload: Mapping[str, Any] | None) -> list[tuple[int, str]]:
    if payload is None or "a" not in payload:
        return []
    raw = payload["a"]
    if not isinstance(raw, list) or not raw:
        raise _fail("a deve essere una lista non vuota")
    cells: list[tuple[int, str]] = []
    for cell in raw:
        if (
            not isinstance(cell, list)
            or len(cell) != 2
            or not _is_int(cell[0])
            or not 1 <= cell[0] <= 7
            or not isinstance(cell[1], str)
            or cell[1] not in _TYPICAL_MEALS
        ):
            raise _fail("cella della settimana tipo non valida")
        cells.append((cell[0], cell[1]))
    if any(a >= b for a, b in itertools.pairwise(cells)):
        raise _fail("celle non ordinate o duplicate")
    return cells


def _validate_typical_week(before: dict[str, Any] | None, after: dict[str, Any]) -> None:
    removed, added = _cells(before), _cells(after)
    if not removed and not added:
        raise _fail("nessuna cella cambiata")
    if set(removed) & set(added):
        raise _fail("una cella non può essere tolta e aggiunta insieme")


def _entries(payload: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Le voci di `i` per id; liste vuote, non ordinate o con duplicati sono rifiutate."""
    if payload is None or "i" not in payload:
        return {}
    raw = payload["i"]
    if not isinstance(raw, list) or not raw:
        raise _fail("i deve essere una lista non vuota")
    entries: dict[str, dict[str, Any]] = {}
    previous = ""
    for entry in raw:
        if not isinstance(entry, dict) or not _is_uuid(entry.get("id")):
            raise _fail("voce senza identificativo valido")
        item_id: str = entry["id"]
        if item_id <= previous:
            raise _fail("voci non ordinate per id o duplicate")
        previous = item_id
        if not set(entry) <= {"id", *_ITEM_FIELDS}:
            raise _fail("campo della voce non ammesso")
        for field in entry.keys() - {"id"}:
            if not _item_field_ok(field, entry[field]):
                raise _fail("valore della voce non ammesso")
        entries[item_id] = entry
    return entries


def _validate_whole_item(entry: Mapping[str, Any]) -> None:
    """Voce aggiunta o tolta: completa, senza campi nulli, piatto con portata o testo libero."""
    fields = set(entry) - {"id"}
    if "p" not in fields or any(entry[f] is None for f in fields):
        raise _fail("voce aggiunta o tolta incompleta o con campi nulli")
    if ("t" in fields) == ("d" in fields) or ("d" in fields) != ("c" in fields):
        raise _fail("la voce è un piatto con portata oppure un testo libero")


def _validate_meal_content(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    after_keys: set[str],
    before_keys: set[str],
) -> None:
    scalars_after, scalars_before = after_keys - {"i"}, before_keys - {"i"}
    if scalars_after != scalars_before:
        raise _fail("s, pr e nm vanno scritti da entrambe le parti")
    for key in scalars_after:
        if before is None or not _scalar_ok(key, before[key]) or not _scalar_ok(key, after[key]):
            raise _fail("valore non ammesso")
    old, new = _entries(before), _entries(after)
    if not old and not new and not scalars_after:
        raise _fail("nessun cambiamento")
    for item_id, entry in old.items():
        if item_id not in new:
            _validate_whole_item(entry)
    for item_id, entry in new.items():
        if item_id not in old:
            _validate_whole_item(entry)
            continue
        other = old[item_id]
        fields = set(entry) - {"id"}
        if not fields or fields != set(other) - {"id"}:
            raise _fail("voce modificata: stessi campi cambiati in before e after")
        if any(entry[f] == other[f] for f in fields):
            raise _fail("voce modificata: un campo indicato non è cambiato")


# --- differenze ----------------------------------------------------------------------------------


def _require_unit(unit_type: str) -> None:
    if unit_type not in KEYS:
        raise _fail("tipo di unità sconosciuto")


def diff(
    unit_type: str, old_state: Mapping[str, Any], new_state: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(`before`, `after`) con i soli campi cambiati. `CodecError` se non è cambiato nulla."""
    _require_unit(unit_type)
    if unit_type in _SINGLE_VALUE:
        before, after = _diff_single(unit_type, old_state, new_state)
    elif unit_type == "typical_week":
        before, after = _diff_typical_week(old_state, new_state)
    else:
        before, after = _diff_meal_content(old_state, new_state)
    if not before and not after:
        raise _fail("nessun cambiamento da registrare")
    return before or None, {"v": CODEC_VERSION, **after}


def _diff_single(
    unit_type: str, old: Mapping[str, Any], new: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    keys = sorted(k for k in KEYS[unit_type] if (k in old or k in new) and old.get(k) != new.get(k))
    return {k: old.get(k) for k in keys}, {k: new.get(k) for k in keys}


def _diff_typical_week(
    old: Mapping[str, Any], new: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    before_cells = {(c[0], c[1]) for c in old.get("a", [])}
    after_cells = {(c[0], c[1]) for c in new.get("a", [])}
    removed, added = sorted(before_cells - after_cells), sorted(after_cells - before_cells)
    return (
        {"a": [list(c) for c in removed]} if removed else {},
        {"a": [list(c) for c in added]} if added else {},
    )


def _whole_item(item_id: str, item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": item_id,
        **{f: item[f] for f in _ITEM_FIELDS if item.get(f) is not None},
    }


def _diff_meal_content(
    old: Mapping[str, Any], new: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    old_items: Mapping[str, Mapping[str, Any]] = old.get("i", {})
    new_items: Mapping[str, Mapping[str, Any]] = new.get("i", {})
    before_items: list[dict[str, Any]] = []
    after_items: list[dict[str, Any]] = []
    for item_id in sorted(old_items.keys() | new_items.keys()):
        was, now = old_items.get(item_id), new_items.get(item_id)
        if was is None and now is not None:
            after_items.append(_whole_item(item_id, now))
        elif now is None and was is not None:
            before_items.append(_whole_item(item_id, was))
        elif was is not None and now is not None and was != now:
            changed = [f for f in _ITEM_FIELDS if was.get(f) != now.get(f)]
            before_items.append({"id": item_id, **{f: was.get(f) for f in changed}})
            after_items.append({"id": item_id, **{f: now.get(f) for f in changed}})
    before: dict[str, Any] = {"i": before_items} if before_items else {}
    after: dict[str, Any] = {"i": after_items} if after_items else {}
    for key in _MEAL_SCALARS:
        if (key in old or key in new) and old.get(key) != new.get(key):
            before[key], after[key] = old.get(key), new.get(key)
    return before, after


# --- applicazione e annullamento -----------------------------------------------------------------


def apply(unit_type: str, state: Mapping[str, Any], before: Any, after: Any) -> dict[str, Any]:
    """Lo stato dopo l'evento, partendo dallo stato prima di esso."""
    return _move(unit_type, state, before, after)


def revert(unit_type: str, state: Mapping[str, Any], before: Any, after: Any) -> dict[str, Any]:
    """Lo stato prima dell'evento, partendo dallo stato dopo di esso (usa `before`)."""
    return _move(unit_type, state, after, before)


def _move(
    unit_type: str, state: Mapping[str, Any], source: Mapping[str, Any] | None, target: Any
) -> dict[str, Any]:
    """Porta `state` da quello descritto da `source` a quello descritto da `target`."""
    _require_unit(unit_type)
    out = deepcopy(dict(state))
    if unit_type in _SINGLE_VALUE:
        if target is None:
            raise _fail("le unità a valore singolo hanno sempre before")
        for key in target.keys() - {"v"}:
            out[key] = deepcopy(target[key])
    elif unit_type == "typical_week":
        cells = {(c[0], c[1]) for c in out.get("a", [])}
        cells -= set(_cells(source))
        cells |= set(_cells(target))
        out["a"] = [list(c) for c in sorted(cells)]
    else:
        _move_meal_content(out, source, target)
    return out


def _move_meal_content(
    out: dict[str, Any], source: Mapping[str, Any] | None, target: Mapping[str, Any] | None
) -> None:
    target = target or {}
    items: dict[str, dict[str, Any]] = out.setdefault("i", {})
    leaving = _entries(source)
    arriving = _entries(target)
    for item_id in leaving.keys() - arriving.keys():
        if items.pop(item_id, None) is None:
            raise _fail("voce da togliere assente dallo stato")
    for item_id, entry in arriving.items():
        fields = {f: entry[f] for f in _ITEM_FIELDS if f in entry}
        if item_id in leaving:
            if item_id not in items:
                raise _fail("voce da modificare assente dallo stato")
            items[item_id] = {**items[item_id], **fields}
        else:
            if item_id in items:
                raise _fail("voce da aggiungere già presente nello stato")
            items[item_id] = {**_DEFAULT_ITEM, **fields}
    for key in _MEAL_SCALARS:
        if key in target:
            out[key] = deepcopy(target[key])
