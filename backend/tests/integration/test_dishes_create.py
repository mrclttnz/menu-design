"""Creare un piatto: `POST /api/v1/dishes` (SL-04; US-004; AC-004.1-.7; SR-024, SR-032, SR-060).

Le prove usano utenti con sessione vera (accesso tramite il provider OIDC finto), database reale,
ruolo `menu_app` con RLS attiva. Gli errori sono `problem+json` con `code=validation` ed
`errors[{field, code, params}]` (piano §4.1). Nessun evento di modifica prima di SL-05.
"""

from collections.abc import Callable
from typing import Any

import pytest

from support.dishes import (
    Actor,
    Who,
    World,
    book,
    change_events,
    dish_count,
    dish_row,
    error_fields,
    etag,
    link,
    make_dish,
    names,
    payload,
)
from support.owner import Owner

pytestmark = pytest.mark.integration
Login = Callable[[Who], Actor]
# URL con credenziali incorporate, costruito a pezzi (dato di prova, non un segreto).
URL_WITH_CREDENTIALS = "https://" + "utente:prova" + "@ricette.example.test/a"


@pytest.fixture
def planner(world: World, login: Login) -> Actor:
    return login(world.alfa.who("planner"))


# --- AC-004.1: nome, portate, stato, fascia -------------------------------------------------------


def test_ac_004_1_the_planner_saves_a_dish_with_all_its_data(
    world: World, planner: Actor, owner: Owner
) -> None:
    """AC-004.1: «Frittata di zucchine», secondo + piatto unico, collaudato, meno di 30 minuti."""
    fam = world.alfa
    body = payload(
        fam,
        "Frittata di zucchine",
        courseIds=[str(fam.courses["second"]), str(fam.courses["one_dish"])],
        status="tested",
        prepTime="under_30",
    )
    created = planner.post("/api/v1/dishes", body)
    assert created.status_code == 201, created.text
    assert etag(created) == '"1"'
    dish = created.json()
    assert dish["name"] == "Frittata di zucchine"
    assert dish["status"] == "tested"
    assert dish["prepTime"] == "under_30"
    assert sorted(dish["courseIds"]) == sorted(body["courseIds"])
    assert dish["version"] == 1
    assert dish["archived"] is False
    assert dish["everPlanned"] is False
    assert dish["createdBy"] == str(fam.who("planner").person)
    assert dish["sources"] == []

    # compare nell'archivio (elenco) e nella scheda con gli stessi dati
    listed = planner.get("/api/v1/dishes").json()["items"]
    assert [d["id"] for d in listed] == [dish["id"]]
    assert listed[0]["status"] == "tested"
    assert listed[0]["prepTime"] == "under_30"
    assert sorted(listed[0]["courseIds"]) == sorted(body["courseIds"])
    detail = planner.get(f"/api/v1/dishes/{dish['id']}")
    assert detail.status_code == 200
    assert detail.json() == dish
    assert etag(detail) == '"1"'

    row = dish_row(owner, dish["id"])
    assert row is not None
    assert row[0] == "Frittata di zucchine"
    assert row[1] == "tested"


def test_the_administrator_can_create_too_and_the_status_defaults_to_to_try(
    world: World, login: Login
) -> None:
    admin = login(world.alfa.who("admin"))
    created = admin.post("/api/v1/dishes", payload(world.alfa, "Pasta e ceci"))
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "to_try"
    assert created.json().get("prepTime") is None
    assert created.json().get("notes") is None
    assert created.json()["createdBy"] == str(world.alfa.who("admin").person)


def test_duplicate_names_are_allowed(world: World, planner: Actor) -> None:
    """05-data: «Nomi duplicati ammessi» (FR-032 avvisa solo da M2)."""
    first = planner.post("/api/v1/dishes", payload(world.alfa, "Minestrone"))
    second = planner.post("/api/v1/dishes", payload(world.alfa, "Minestrone"))
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_notes_and_every_prep_time_band_are_saved(world: World, planner: Actor) -> None:
    for band in ("under_30", "30_60", "over_60"):
        created = planner.post(
            "/api/v1/dishes",
            payload(world.alfa, f"Piatto {band}", prepTime=band, notes="Con rosmarino."),
        )
        assert created.status_code == 201, created.text
        assert created.json()["prepTime"] == band
        assert created.json()["notes"] == "Con rosmarino."


def test_the_response_is_not_cacheable_and_uses_camel_case_only(
    world: World, planner: Actor
) -> None:
    created = planner.post("/api/v1/dishes", payload(world.alfa))
    assert created.headers["cache-control"] == "no-store"
    assert created.headers["content-type"].startswith("application/json")
    assert not [k for k in created.json() if "_" in k], "chiavi JSON in camelCase (piano §4.1)"
    assert "familyId" not in created.json()
    assert "family_id" not in created.json()


def test_no_change_event_is_written_in_sl04(world: World, planner: Actor, owner: Owner) -> None:
    """`change_event` arriva con SL-05: finché non esiste non ce n'è nessuno."""
    assert planner.post("/api/v1/dishes", payload(world.alfa)).status_code == 201
    assert change_events(owner) == 0


# --- AC-004.2: fonti ------------------------------------------------------------------------------


def test_ac_004_2_link_and_book_sources_are_saved_in_order(world: World, planner: Actor) -> None:
    sources = [
        link("https://ricette.example.test/frittata", note="la migliore"),
        book("Il cucchiaio", "142"),
    ]
    created = planner.post("/api/v1/dishes", payload(world.alfa, sources=sources))
    assert created.status_code == 201, created.text
    assert created.json()["sources"] == [
        {
            "kind": "link",
            "reference": "https://ricette.example.test/frittata",
            "note": "la migliore",
        },
        {"kind": "book", "reference": "Il cucchiaio", "page": "142"},
    ]
    detail = planner.get(f"/api/v1/dishes/{created.json()['id']}").json()
    assert detail["sources"] == created.json()["sources"]


def test_ac_004_2_http_and_other_kinds_of_source_are_accepted(world: World, planner: Actor) -> None:
    sources = [
        link("http://ricette.example.test/vecchia"),
        {"kind": "magazine", "reference": "Cucina Facile", "page": "9"},
        {"kind": "other", "reference": "Il quaderno della nonna"},
    ]
    created = planner.post("/api/v1/dishes", payload(world.alfa, sources=sources))
    assert created.status_code == 201, created.text
    assert [s["kind"] for s in created.json()["sources"]] == ["link", "magazine", "other"]


# --- AC-004.3: nome e portate obbligatori ---------------------------------------------------------


@pytest.mark.parametrize("missing", ["name", "courseIds"])
def test_ac_004_3_missing_required_field_is_refused_and_named(
    world: World, planner: Actor, owner: Owner, missing: str
) -> None:
    body = payload(world.alfa)
    del body[missing]
    refused = planner.post("/api/v1/dishes", body)
    assert refused.status_code == 422, refused.text
    fields = error_fields(refused)
    assert missing in fields, fields
    assert fields[missing] in {"required", "course_required"}
    assert dish_count(owner, world.alfa) == 0


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_ac_004_3_blank_name_is_refused_as_required(
    world: World, planner: Actor, owner: Owner, name: str
) -> None:
    refused = planner.post("/api/v1/dishes", payload(world.alfa, name))
    assert refused.status_code == 422, refused.text
    assert error_fields(refused).get("name") == "required"
    assert dish_count(owner, world.alfa) == 0


def test_ac_004_3_no_course_is_refused_with_course_required(
    world: World, planner: Actor, owner: Owner
) -> None:
    refused = planner.post("/api/v1/dishes", payload(world.alfa, courseIds=[]))
    assert refused.status_code == 422, refused.text
    assert error_fields(refused).get("courseIds") == "course_required"
    assert dish_count(owner, world.alfa) == 0


# --- AC-004.4: fonti link con schema diverso da http/https ----------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        " javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "ftp://ricette.example.test/a",
        "ricette.example.test/frittata",
        "//ricette.example.test/frittata",
        "https://",
        URL_WITH_CREDENTIALS,
        "https://ricette.example.test/a b",
        "not a url",
        "",
    ],
)
def test_ac_004_4_a_link_that_is_not_http_or_https_is_refused(
    world: World, planner: Actor, owner: Owner, url: str
) -> None:
    refused = planner.post("/api/v1/dishes", payload(world.alfa, sources=[link(url)]))
    assert refused.status_code == 422, refused.text
    fields = error_fields(refused)
    assert "sources[0].reference" in fields, fields
    assert fields["sources[0].reference"] in {"url_invalid", "required"}
    if url.strip():
        assert url.strip() not in refused.text, "il valore ricevuto non si riflette (THR-107)"
    assert dish_count(owner, world.alfa) == 0


def test_ac_004_4_the_url_error_is_attached_to_the_right_source(
    world: World, planner: Actor
) -> None:
    sources = [link("https://ricette.example.test/ok"), link("javascript:alert(1)")]
    refused = planner.post("/api/v1/dishes", payload(world.alfa, sources=sources))
    assert refused.status_code == 422
    assert error_fields(refused) == {"sources[1].reference": "url_invalid"}


@pytest.mark.parametrize(
    ("source", "field"),
    [
        ({"kind": "book", "reference": ""}, "sources[0].reference"),
        ({"kind": "other", "reference": ""}, "sources[0].reference"),
        ({"kind": "video", "reference": "x"}, "sources[0].kind"),
        ({"reference": "x"}, "sources[0].kind"),
        ({"kind": "book"}, "sources[0].reference"),
        ({"kind": "link", "reference": "https://a.example.test", "page": "3"}, "sources[0].page"),
        ({"kind": "other", "reference": "x", "page": "3"}, "sources[0].page"),
        ({"kind": "book", "reference": "x", "extra": 1}, "sources[0].extra"),
    ],
)
def test_malformed_sources_are_refused_on_the_right_field(
    world: World, planner: Actor, source: dict[str, Any], field: str
) -> None:
    refused = planner.post("/api/v1/dishes", payload(world.alfa, sources=[source]))
    assert refused.status_code == 422, refused.text
    assert field in error_fields(refused), error_fields(refused)


# --- AC-004.5: limiti -----------------------------------------------------------------------------


def test_ac_004_5_a_name_of_120_characters_is_accepted_and_121_is_refused(
    world: World, planner: Actor, owner: Owner
) -> None:
    ok = planner.post("/api/v1/dishes", payload(world.alfa, "è" * 120))
    assert ok.status_code == 201
    assert ok.json()["name"] == "è" * 120
    refused = planner.post("/api/v1/dishes", payload(world.alfa, "è" * 121))
    assert refused.status_code == 422
    assert error_fields(refused) == {"name": "string_too_long"}
    assert refused.json()["errors"][0]["params"] == {"max": 120}
    assert dish_count(owner, world.alfa) == 1


def test_ac_004_5_notes_of_2000_characters_are_accepted_and_2001_are_refused(
    world: World, planner: Actor
) -> None:
    assert planner.post("/api/v1/dishes", payload(world.alfa, notes="n" * 2000)).status_code == 201
    refused = planner.post("/api/v1/dishes", payload(world.alfa, notes="n" * 2001))
    assert refused.status_code == 422
    assert error_fields(refused) == {"notes": "string_too_long"}
    assert refused.json()["errors"][0]["params"] == {"max": 2000}


def test_ac_004_5_ten_sources_are_accepted_and_the_eleventh_is_refused(
    world: World, planner: Actor, owner: Owner
) -> None:
    ten = [link(f"https://ricette.example.test/{n}") for n in range(10)]
    ok = planner.post("/api/v1/dishes", payload(world.alfa, "Dieci fonti", sources=ten))
    assert ok.status_code == 201
    assert len(ok.json()["sources"]) == 10
    refused = planner.post(
        "/api/v1/dishes",
        payload(
            world.alfa, "Undici fonti", sources=[*ten, link("https://ricette.example.test/10")]
        ),
    )
    assert refused.status_code == 422
    assert error_fields(refused) == {"sources": "limit_reached"}
    assert refused.json()["errors"][0]["params"] == {"max": 10}
    assert dish_count(owner, world.alfa) == 1


@pytest.mark.parametrize(
    ("source", "field"),
    [
        (link("https://a.example.test/" + "x" * 500), "sources[0].reference"),
        (book("t", "p" * 21), "sources[0].page"),
        ({"kind": "other", "reference": "r", "note": "n" * 501}, "sources[0].note"),
    ],
)
def test_source_field_limits(
    world: World, planner: Actor, source: dict[str, Any], field: str
) -> None:
    refused = planner.post("/api/v1/dishes", payload(world.alfa, sources=[source]))
    assert refused.status_code == 422, refused.text
    assert error_fields(refused).get(field) == "string_too_long"


# --- AC-004.6: testo letterale, mai markup --------------------------------------------------------


XSS = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "<svg onload=alert(1)>",
    "&lt;b&gt;grassetto&lt;/b&gt; &amp; più",
    "javascript:alert(1)",
]


@pytest.mark.parametrize("text", XSS)
def test_ac_004_6_markup_in_name_and_notes_is_stored_and_returned_literally(
    world: World, planner: Actor, text: str
) -> None:
    """Lato server: nessuna trasformazione né codifica; è la SPA a mostrarlo come testo (e2e)."""
    created = planner.post("/api/v1/dishes", payload(world.alfa, text, notes=text))
    assert created.status_code == 201, created.text
    assert created.json()["name"] == text
    assert created.json()["notes"] == text
    detail = planner.get(f"/api/v1/dishes/{created.json()['id']}")
    assert detail.json()["name"] == text
    assert detail.json()["notes"] == text
    assert detail.headers["content-type"].startswith("application/json"), "mai text/html"
    assert detail.headers["x-content-type-options"] == "nosniff"
    listed = planner.get("/api/v1/dishes").json()["items"]
    assert [d["name"] for d in listed] == [text]


def test_unicode_and_emoji_round_trip(world: World, planner: Actor) -> None:
    name = "Crème brûlée 🍮 ñoquis 日本"
    created = planner.post("/api/v1/dishes", payload(world.alfa, name, notes="à è ì ò ù 🥕"))
    assert created.status_code == 201
    assert planner.get(f"/api/v1/dishes/{created.json()['id']}").json()["name"] == name


def test_a_nul_character_is_a_validation_error_not_a_server_error(
    world: World, planner: Actor, owner: Owner
) -> None:
    """PostgreSQL non accetta NUL nel testo: deve essere un 422, mai un 500 (CWE-158)."""
    for field in ("name", "notes"):
        body = payload(world.alfa, "Nome") | {field: "a\u0000b"}
        refused = planner.post("/api/v1/dishes", body)
        assert refused.status_code == 422, (field, refused.status_code, refused.text)
        assert field in error_fields(refused)
    nul_url = link("https://a.example.test/\u0000")
    refused = planner.post("/api/v1/dishes", payload(world.alfa, sources=[nul_url]))
    assert refused.status_code == 422
    assert dish_count(owner, world.alfa) == 0


# --- AC-004.7: archivio vuoto ---------------------------------------------------------------------


def test_ac_004_7_an_empty_archive_lists_no_dishes(
    world: World, planner: Actor, owner: Owner
) -> None:
    """Il messaggio di stato vuoto e il pulsante sono della SPA; il server dà una pagina vuota."""
    make_dish(owner, world.beta, "CANARY-BETA-DISH-1")
    listed = planner.get("/api/v1/dishes")
    assert listed.status_code == 200
    assert listed.json() == {"items": [], "nextCursor": None}


# --- forma della richiesta ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"name": 123},
        {"name": None},
        {"name": ["a"]},
        {"courseIds": "uno"},
        {"courseIds": [1]},
        {"courseIds": ["non-un-uuid"]},
        {"courseIds": [None]},
        {"status": "done"},
        {"status": "TESTED"},
        {"status": None},
        {"prepTime": "forever"},
        {"prepTime": 30},
        {"notes": 5},
        {"sources": "x"},
        {"sources": {"kind": "link"}},
        {"sources": [None]},
    ],
)
def test_wrongly_typed_or_out_of_vocabulary_values_are_a_422_never_a_500(
    world: World, planner: Actor, owner: Owner, bad: dict[str, Any]
) -> None:
    refused = planner.post("/api/v1/dishes", payload(world.alfa) | bad)
    assert refused.status_code == 422, (bad, refused.status_code, refused.text)
    assert refused.json()["code"] == "validation"
    assert dish_count(owner, world.alfa) == 0


def test_a_body_that_is_not_a_json_object_is_a_422(world: World, planner: Actor) -> None:
    for raw in (b"", b"{", b"[]", b'"x"', b"null", b"\xff\xfe"):
        refused = planner.browser.request("POST", "/api/v1/dishes", content=raw, csrf=planner.csrf)
        assert refused.status_code in {400, 422}, (raw, refused.status_code, refused.text)
        assert refused.json()["code"] == "validation"


def test_a_json_nested_deeper_than_ten_levels_is_refused(world: World, planner: Actor) -> None:
    """SR-060: profondità JSON <= 10."""
    deep: Any = "x"
    for _ in range(12):
        deep = {"a": deep}
    refused = planner.post("/api/v1/dishes", payload(world.alfa) | {"notes": deep})
    assert refused.status_code in {413, 422}, refused.status_code
    ok = planner.post("/api/v1/dishes", payload(world.alfa, "Dopo il rifiuto"))
    assert ok.status_code == 201, "la rotta esiste e accetta un corpo normale"


def test_a_body_over_64_kib_is_refused_with_413(world: World, planner: Actor) -> None:
    big = planner.post("/api/v1/dishes", payload(world.alfa, notes="n" * 70_000))
    assert big.status_code == 413
    assert big.json()["code"] == "payload_too_large"
    ok = planner.post("/api/v1/dishes", payload(world.alfa, "Dopo il rifiuto"))
    assert ok.status_code == 201, "la rotta esiste e accetta un corpo normale"


def test_created_by_cannot_be_set_through_the_body(world: World, planner: Actor) -> None:
    """`createdBy` è sempre la persona della sessione (SR-010); il campo nel corpo è respinto."""
    other = str(world.alfa.who("admin").person)
    refused = planner.post("/api/v1/dishes", payload(world.alfa) | {"createdBy": other})
    assert refused.status_code == 422
    assert error_fields(refused) == {"createdBy": "unknown_field"}
    assert names(planner.get("/api/v1/dishes")) == []
