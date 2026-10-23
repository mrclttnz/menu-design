"""Cercare e filtrare l'archivio: `GET /api/v1/dishes` e `GET /api/v1/courses` (SL-04; US-006).

AC-006.1-.5; FR-030 (ricerca parziale che ignora maiuscole e accenti, ASM-047); SR-060
(paginazione a cursore, `limit` <= 100); THR-025 (`%`, `_`, `'`, `\\` e payload di iniezione non
sono mai interpretati: la ricerca è letterale e non esce dalla famiglia). I piatti archiviati
degli AC-006.4 vengono da fixture (l'archiviazione end-to-end è di SL-08).
"""

from collections.abc import Callable
from typing import Any

import pytest
from httpx import Response

from support.dishes import (
    BASE_CODES,
    Actor,
    Who,
    World,
    bulk_dishes,
    dish_count,
    error_fields,
    make_dish,
    names,
)
from support.owner import Owner

pytestmark = pytest.mark.integration
Login = Callable[[Who], Actor]


@pytest.fixture
def planner(world: World, login: Login) -> Actor:
    return login(world.alfa.who("planner"))


def search(actor: Actor, q: str, **extra: str) -> Response:
    from urllib.parse import urlencode

    return actor.get("/api/v1/dishes?" + urlencode({"q": q, **extra}))


# --- AC-006.1: nome parziale, senza distinzione tra maiuscole e minuscole -------------------------


@pytest.mark.parametrize("query", ["ceci", "PASTA", "Pasta", "asta e c", "CeCi", "pasta e ceci"])
def test_ac_006_1_partial_case_insensitive_search_finds_the_dish(
    world: World, planner: Actor, owner: Owner, query: str
) -> None:
    make_dish(owner, world.alfa, "Pasta e ceci")
    make_dish(owner, world.alfa, "Risotto ai funghi")
    assert names(search(planner, query)) == ["Pasta e ceci"]


def test_ac_006_1_a_query_that_matches_nothing_returns_an_empty_page(
    world: World, planner: Actor, owner: Owner
) -> None:
    make_dish(owner, world.alfa, "Pasta e ceci")
    found = search(planner, "pizza")
    assert found.status_code == 200
    assert found.json() == {"items": [], "nextCursor": None}


def test_an_empty_query_lists_everything(world: World, planner: Actor, owner: Owner) -> None:
    make_dish(owner, world.alfa, "Pasta e ceci")
    make_dish(owner, world.alfa, "Risotto")
    assert names(search(planner, "")) == ["Pasta e ceci", "Risotto"]


# --- AC-006.2: accenti ----------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["pure", "purè", "PURÈ", "Pure", "pUrÈ di", "ure di pat"])
def test_ac_006_2_search_ignores_accents_in_both_directions(
    world: World, planner: Actor, owner: Owner, query: str
) -> None:
    make_dish(owner, world.alfa, "Purè di patate")
    assert names(search(planner, query)) == ["Purè di patate"]


def test_ac_006_2_an_unaccented_name_is_found_with_an_accented_query(
    world: World, planner: Actor, owner: Owner
) -> None:
    make_dish(owner, world.alfa, "Pure di zucca")
    make_dish(owner, world.alfa, "Crème caramel")
    assert names(search(planner, "purè")) == ["Pure di zucca"]
    assert names(search(planner, "CREME")) == ["Crème caramel"]
    assert names(search(planner, "crème")) == ["Crème caramel"]


# --- AC-006.3: filtri per portata e stato ---------------------------------------------------------


def test_ac_006_3_course_and_status_filters_combine_and_exclude_archived(
    world: World, planner: Actor, owner: Owner
) -> None:
    fam = world.alfa
    make_dish(owner, fam, "Insalata", courses=("side",), status="to_try")
    make_dish(owner, fam, "Patate al forno", courses=("side",), status="tested")
    make_dish(owner, fam, "Pasta al pomodoro", courses=("first",), status="to_try")
    make_dish(owner, fam, "Zucchine", courses=("side",), status="to_try", archived=True)
    make_dish(owner, fam, "Fagiolini", courses=("side", "first"), status="to_try")
    side = str(fam.courses["side"])
    assert names(planner.get(f"/api/v1/dishes?courseId={side}&status=to_try")) == [
        "Fagiolini",
        "Insalata",
    ]
    assert names(planner.get(f"/api/v1/dishes?courseId={side}&status=tested")) == [
        "Patate al forno"
    ]
    assert names(planner.get(f"/api/v1/dishes?courseId={side}")) == [
        "Fagiolini",
        "Insalata",
        "Patate al forno",
    ]
    assert names(planner.get("/api/v1/dishes?status=tested")) == ["Patate al forno"]
    assert names(planner.get("/api/v1/dishes?status=to_try")) == [
        "Fagiolini",
        "Insalata",
        "Pasta al pomodoro",
    ]


def test_filters_combine_with_the_search_text(world: World, planner: Actor, owner: Owner) -> None:
    make_dish(owner, world.alfa, "Pasta e ceci", courses=("first",))
    make_dish(owner, world.alfa, "Insalata di ceci", courses=("side",))
    side = str(world.alfa.courses["side"])
    assert names(search(planner, "ceci", courseId=side)) == ["Insalata di ceci"]


@pytest.mark.parametrize(
    ("param", "value"),
    [("status", "done"), ("status", "TESTED"), ("archived", "maybe"), ("courseId", "abc")],
)
def test_invalid_filter_values_are_a_422_not_a_500(planner: Actor, param: str, value: str) -> None:
    refused = planner.get(f"/api/v1/dishes?{param}={value}")
    assert refused.status_code == 422, (param, value, refused.status_code, refused.text)
    assert refused.json()["code"] == "validation"


# --- AC-006.4: archiviati nascosti salvo filtro ---------------------------------------------------


def test_ac_006_4_an_archived_dish_is_hidden_unless_the_filter_is_on(
    world: World, planner: Actor, owner: Owner
) -> None:
    make_dish(owner, world.alfa, "Lasagne", archived=True)
    make_dish(owner, world.alfa, "Lasagnette", status="tested")
    assert names(search(planner, "lasagne")) == ["Lasagnette"], "nascosto di default"
    assert "Lasagne" not in names(search(planner, "lasagne", archived="false"))
    assert "Lasagne" not in names(planner.get("/api/v1/dishes"))
    shown = search(planner, "lasagne", archived="true")
    assert shown.status_code == 200
    labelled = {d["name"]: d for d in shown.json()["items"]}
    assert labelled["Lasagne"]["archived"] is True, "etichetta «archiviato»"


def test_archived_flag_is_false_for_active_dishes(
    world: World, planner: Actor, owner: Owner
) -> None:
    make_dish(owner, world.alfa, "Lasagne", archived=True)
    make_dish(owner, world.alfa, "Minestrone")
    items = {d["name"]: d for d in planner.get("/api/v1/dishes?archived=true").json()["items"]}
    assert items["Minestrone"]["archived"] is False
    assert items["Lasagne"]["archived"] is True
    assert items["Lasagne"]["everPlanned"] is True


# --- AC-006.5: nessun risultato -------------------------------------------------------------------


def test_ac_006_5_no_result_is_an_empty_page_the_client_can_turn_into_create(
    world: World, planner: Actor, owner: Owner
) -> None:
    """La frase «nessun piatto trovato» e «crea piatto con questo nome» sono della SPA."""
    make_dish(owner, world.alfa, "Pasta e ceci")
    found = search(planner, "Shakshuka")
    assert found.status_code == 200
    assert found.json()["items"] == []
    assert found.json()["nextCursor"] is None


# --- caratteri speciali: ricerca letterale (THR-025) ----------------------------------------------


@pytest.fixture
def special(world: World, owner: Owner) -> None:
    for name in (
        "50% sugo",
        "50 sugo",
        "a_b",
        "axb",
        "L'insalata di Nonna",
        "back\\slash",
        "Zuppa",
    ):
        make_dish(owner, world.alfa, name)
    make_dish(owner, world.beta, "CANARY-BETA-DISH 50% a_b L'insalata")


@pytest.mark.usefixtures("special")
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("%", ["50% sugo"]),
        ("50%", ["50% sugo"]),
        ("% sugo", ["50% sugo"]),
        ("_", ["a_b"]),
        ("a_b", ["a_b"]),
        ("'", ["L'insalata di Nonna"]),
        ("l'ins", ["L'insalata di Nonna"]),
        ("\\", ["back\\slash"]),
        ("k\\s", ["back\\slash"]),
        ("%%", []),
        ("\\%", []),
        ("a%b", []),
        ("a\\_b", []),
    ],
)
def test_wildcards_and_quotes_are_matched_literally(
    planner: Actor, query: str, expected: list[str]
) -> None:
    assert names(search(planner, query)) == expected


@pytest.mark.usefixtures("special")
@pytest.mark.parametrize(
    "payload",
    [
        "' OR 1=1 --",
        "'; DROP TABLE app.dish; --",
        '" OR ""="',
        "'; SELECT set_config('app.family_id', '00000000-0000-0000-0000-000000000000', false); --",
        "') UNION SELECT name FROM app.dish --",
        "%' OR family_id IS NOT NULL OR name_search LIKE '%",
    ],
)
def test_injection_payloads_are_plain_text_and_never_leave_the_family(
    world: World, planner: Actor, owner: Owner, payload: str
) -> None:
    before = dish_count(owner, world.alfa)
    found = search(planner, payload)
    assert found.status_code in {200, 422}, found.status_code
    if found.status_code == 200:
        assert names(found) == [], "nessun nome contiene il payload alla lettera"
    assert "CANARY-BETA" not in found.text
    assert dish_count(owner, world.alfa) == before
    # la tabella c'è ancora e la ricerca normale funziona (nessun `;` eseguito)
    assert "Zuppa" in names(search(planner, "zuppa"))


@pytest.mark.usefixtures("special")
def test_wildcard_query_never_returns_another_familys_dishes(planner: Actor) -> None:
    for query in ("%", "_", "50%", "a_b", "CANARY", "L'insalata"):
        assert "CANARY-BETA" not in search(planner, query).text, query


@pytest.mark.parametrize("query", ["a" * 1000, "a\u0000b", "%00", "🍝"])
def test_odd_queries_are_never_a_server_error(planner: Actor, query: str) -> None:
    found = search(planner, query)
    assert found.status_code in {200, 422}, (query[:20], found.status_code)


# --- ordine ---------------------------------------------------------------------------------------


def test_the_list_is_ordered_by_name_without_accents_or_case(
    world: World, planner: Actor, owner: Owner
) -> None:
    """M0-M1: «ordinato per nome senza accenti» (piano §4.3)."""
    for name in ("Zucchine", "àgnello", "Banana", "agnello al forno", "Èdamame", "carote"):
        make_dish(owner, world.alfa, name)
    assert names(planner.get("/api/v1/dishes")) == [
        "àgnello",
        "agnello al forno",
        "Banana",
        "carote",
        "Èdamame",
        "Zucchine",
    ]


# --- forma della voce di elenco -------------------------------------------------------------------


def test_list_items_are_summaries_without_notes_or_sources(
    world: World, planner: Actor, owner: Owner
) -> None:
    make_dish(
        owner,
        world.alfa,
        "Frittata",
        courses=("second", "one_dish"),
        status="tested",
        notes="CANARY-ALFA-NOTE",
        prep_time="under_30",
        sources=({"kind": "other", "reference": "dal nonno"},),
    )
    (item,) = planner.get("/api/v1/dishes").json()["items"]
    assert {"id", "name", "status", "courseIds", "archived", "everPlanned"} <= set(item)
    assert item["prepTime"] == "under_30"
    assert item["status"] == "tested"
    assert len(item["courseIds"]) == 2
    assert "notes" not in item
    assert "sources" not in item
    assert "CANARY-ALFA-NOTE" not in str(item)
    assert not [k for k in item if "_" in k]


def test_every_role_gets_the_same_archive(world: World, login: Login, owner: Owner) -> None:
    make_dish(owner, world.alfa, "Pasta e ceci")
    for role in ("admin", "planner", "member"):
        assert names(login(world.alfa.who(role)).get("/api/v1/dishes")) == ["Pasta e ceci"], role


# --- paginazione a cursore (SR-060) ---------------------------------------------------------------


def _walk(actor: Actor, query: str = "", limit: int | None = None) -> list[list[dict[str, Any]]]:
    pages: list[list[dict[str, Any]]] = []
    cursor: str | None = None
    for _ in range(100):
        params = [query] if query else []
        if limit is not None:
            params.append(f"limit={limit}")
        if cursor:
            params.append(f"cursor={cursor}")
        response = actor.get("/api/v1/dishes" + ("?" + "&".join(params) if params else ""))
        assert response.status_code == 200, response.text
        body = response.json()
        pages.append(body["items"])
        cursor = body["nextCursor"]
        if cursor is None:
            return pages
    raise AssertionError("troppe pagine: il cursore non avanza")


def test_pages_cover_every_dish_once_in_order(world: World, planner: Actor, owner: Owner) -> None:
    bulk_dishes(owner, world.alfa, 130)
    pages = _walk(planner)
    assert [len(p) for p in pages] == [50, 50, 30], "pagine da 50 (03-ux S-05) per default"
    flat = [d["name"] for page in pages for d in page]
    assert flat == sorted(flat)
    assert len(set(flat)) == 130


def test_limit_changes_the_page_size_up_to_100(world: World, planner: Actor, owner: Owner) -> None:
    bulk_dishes(owner, world.alfa, 130)
    assert [len(p) for p in _walk(planner, limit=100)] == [100, 30]
    assert [len(p) for p in _walk(planner, limit=60)] == [60, 60, 10]
    one = planner.get("/api/v1/dishes?limit=1").json()
    assert len(one["items"]) == 1
    assert one["nextCursor"]


def test_the_last_page_has_a_null_cursor_and_an_exact_page_has_none_too(
    world: World, planner: Actor, owner: Owner
) -> None:
    bulk_dishes(owner, world.alfa, 50)
    page = planner.get("/api/v1/dishes?limit=50").json()
    assert len(page["items"]) == 50
    assert page["nextCursor"] is None


@pytest.mark.parametrize("limit", ["0", "101", "-1", "abc", "1.5", "", "1000000000000000000000"])
def test_an_invalid_limit_is_a_422(planner: Actor, limit: str) -> None:
    refused = planner.get(f"/api/v1/dishes?limit={limit}")
    assert refused.status_code == 422, (limit, refused.status_code)
    assert refused.json()["code"] == "validation"


def test_identical_names_do_not_lose_or_repeat_rows_across_pages(
    world: World, planner: Actor, owner: Owner
) -> None:
    """Il cursore ordina per (nome normalizzato, id): a parità di nome nessun salto né doppione."""
    owner.execute(
        "insert into app.dish (family_id, name, created_by) "
        "select %s, 'Minestra', %s from generate_series(1, 120)",
        (world.alfa.id, world.alfa.who("planner").person),
    )
    pages = _walk(planner, limit=25)
    ids = [d["id"] for page in pages for d in page]
    assert len(ids) == 120
    assert len(set(ids)) == 120


def test_paging_with_a_search_text_keeps_the_filter(
    world: World, planner: Actor, owner: Owner
) -> None:
    bulk_dishes(owner, world.alfa, 70, prefix="Zuppa")
    bulk_dishes(owner, world.alfa, 10, prefix="Torta")
    pages = _walk(planner, "q=zuppa", limit=30)
    assert [len(p) for p in pages] == [30, 30, 10]
    assert all(d["name"].startswith("Zuppa") for page in pages for d in page)


@pytest.mark.parametrize(
    "cursor", ["garbage", "!!!", "e30", "AAAA", "%00", "a" * 5000, "' OR 1=1 --"]
)
def test_a_tampered_cursor_is_a_422_and_leaks_nothing(
    world: World, planner: Actor, owner: Owner, cursor: str
) -> None:
    bulk_dishes(owner, world.alfa, 60)
    from urllib.parse import quote

    refused = planner.get(f"/api/v1/dishes?cursor={quote(cursor)}")
    assert refused.status_code == 422, (cursor[:20], refused.status_code, refused.text)
    assert error_fields(refused).get("cursor") == "invalid_value"
    assert "Piatto" not in refused.text


def test_a_cursor_from_another_family_never_shows_that_familys_rows(
    world: World, login: Login, owner: Owner
) -> None:
    bulk_dishes(owner, world.alfa, 120, prefix="CANARY-ALFA")
    bulk_dishes(owner, world.beta, 5, prefix="Beta piatto")
    alfa = login(world.alfa.who("planner"))
    beta = login(world.beta.who("planner"))
    cursor = alfa.get("/api/v1/dishes?limit=10").json()["nextCursor"]
    assert cursor
    reply = beta.get(f"/api/v1/dishes?cursor={cursor}")
    assert reply.status_code in {200, 422}
    assert "CANARY-ALFA" not in reply.text
    if reply.status_code == 200:
        assert all(n.startswith("Beta") for n in names(reply))


# --- portate --------------------------------------------------------------------------------------


def test_courses_lists_the_eight_base_courses_of_the_family_only(
    world: World, login: Login
) -> None:
    for role in ("admin", "planner", "member"):
        actor = login(world.alfa.who(role))
        response = actor.get("/api/v1/courses")
        assert response.status_code == 200, (role, response.text)
        items = response.json()["items"]
        assert {c["baseCode"] for c in items} == set(BASE_CODES)
        assert {c["id"] for c in items} == {str(i) for i in world.alfa.courses.values()}
        assert all(c.get("name") is None for c in items), "le portate base non hanno nome salvato"
        assert not {str(i) for i in world.beta.courses.values()} & {c["id"] for c in items}
        assert response.headers["cache-control"] == "no-store"
