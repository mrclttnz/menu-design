"""Dati e client di prova dell'archivio piatti (SL-04): famiglie, portate, piatti, attori.

Le righe si scrivono con l'helper `owner` (08 §5.1), mai dall'API, così i test non dipendono dalle
rotte sotto prova. Dati sintetici: email `@example.test`, nomi inventati, valori CANARINO distinti
per famiglia (08 §5.2) per vedere se un dato attraversa il confine tra famiglie.

`Actor` è un utente collegato: un `Browser` con sessione vera (accesso tramite il provider OIDC
finto) che aggiunge da solo il token CSRF della sessione alle richieste non sicure.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from httpx import Response

from support.accounts import make_family, make_member
from support.browser_sim import Browser
from support.fake_oidc import FakeOidc, Identity
from support.owner import Owner

BASE_CODES = ("starter", "first", "second", "side", "one_dish", "dessert", "drink", "other")
ROLES = ("admin", "planner", "member")
DISH_QUOTA = 2000


@dataclass(frozen=True)
class Who:
    role: str
    identity: Identity
    account: UUID
    person: UUID


@dataclass(frozen=True)
class Fam:
    key: str
    id: UUID
    courses: dict[str, UUID]
    people: dict[str, Who]
    canary: str

    def who(self, role: str) -> Who:
        return self.people[role]


@dataclass(frozen=True)
class World:
    alfa: Fam
    beta: Fam

    def fam(self, key: str) -> Fam:
        return {"alfa": self.alfa, "beta": self.beta}[key]


def make_courses(owner: Owner, family: UUID) -> dict[str, UUID]:
    """Le 8 portate base della famiglia (come `console_bootstrap_family`)."""
    ids = {code: uuid4() for code in BASE_CODES}
    for code, course_id in ids.items():
        owner.execute(
            "insert into app.course (id, family_id, base_code) values (%s, %s, %s)",
            (course_id, family, code),
        )
    return ids


def make_fam(owner: Owner, key: str) -> Fam:
    name = key.capitalize()
    family = make_family(owner, f"Famiglia {name}")
    people: dict[str, Who] = {}
    for role in ROLES:
        identity = Identity(
            sub=f"sub-{key}-{role}",
            email=f"{key}.{role}@example.test",
            name=f"{role.capitalize()} {name}",
        )
        account, person = make_member(
            owner,
            family,
            sub=identity.sub,
            email=identity.email,
            role=role,
            display_name=identity.name or role,
        )
        people[role] = Who(role, identity, account, person)
    return Fam(key, family, make_courses(owner, family), people, f"CANARY-{key.upper()}")


def make_world(owner: Owner) -> World:
    return World(make_fam(owner, "alfa"), make_fam(owner, "beta"))


# --- piatti scritti con l'helper owner ---------------------------------------------------------


def make_dish(
    owner: Owner,
    fam: Fam,
    name: str,
    *,
    courses: tuple[str, ...] = ("first",),
    status: str = "to_try",
    notes: str | None = None,
    prep_time: str | None = None,
    archived: bool = False,
    ever_planned: bool = False,
    sources: tuple[dict[str, Any], ...] = (),
    version: int = 1,
    created_by: str = "planner",
) -> UUID:
    dish = uuid4()
    planned = ever_planned or archived
    owner.execute(
        "insert into app.dish (id, family_id, name, status, notes, prep_time, archived_at, "
        "ever_planned, created_by, version) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            dish,
            fam.id,
            name,
            status,
            notes,
            prep_time,
            datetime.now(UTC) if archived else None,
            planned,
            fam.who(created_by).person,
            version,
        ),
    )
    for code in courses:
        owner.execute(
            "insert into app.dish_course (family_id, dish_id, course_id) values (%s, %s, %s)",
            (fam.id, dish, fam.courses[code]),
        )
    for position, source in enumerate(sources):
        owner.execute(
            "insert into app.dish_source (id, family_id, dish_id, position, kind, reference, "
            "page, note) values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                uuid4(),
                fam.id,
                dish,
                position,
                source["kind"],
                source["reference"],
                source.get("page"),
                source.get("note"),
            ),
        )
    return dish


def seed_dishes(
    owner: Owner,
    family: UUID,
    person: UUID,
    courses: dict[str, UUID],
    dishes: list[dict[str, Any]],
) -> None:
    """Piatti di prova per gli e2e (`POST /__seed`): portate per codice base, id facoltativo."""
    for item in dishes:
        dish = UUID(item["id"]) if item.get("id") else uuid4()
        archived = bool(item.get("archived"))
        owner.execute(
            "insert into app.dish (id, family_id, name, status, notes, prep_time, archived_at, "
            "ever_planned, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                dish,
                family,
                item["name"],
                item.get("status", "to_try"),
                item.get("notes"),
                item.get("prepTime"),
                datetime.now(UTC) if archived else None,
                archived,
                person,
            ),
        )
        for code in item.get("courses", ["first"]):
            owner.execute(
                "insert into app.dish_course (family_id, dish_id, course_id) values (%s, %s, %s)",
                (family, dish, courses[code]),
            )
        for position, source in enumerate(item.get("sources", [])):
            owner.execute(
                "insert into app.dish_source (family_id, dish_id, position, kind, reference, page) "
                "values (%s, %s, %s, %s, %s, %s)",
                (family, dish, position, source["kind"], source["reference"], source.get("page")),
            )


def bulk_dishes(owner: Owner, fam: Fam, count: int, prefix: str = "Piatto") -> None:
    """`count` piatti validi (con una portata) in un solo statement: per quote e paginazione."""
    owner.execute(
        "insert into app.dish (family_id, name, created_by) "
        "select %s, %s || ' ' || lpad(g::text, 5, '0'), %s from generate_series(1, %s) g",
        (fam.id, prefix, fam.who("planner").person, count),
    )
    owner.execute(
        "insert into app.dish_course (family_id, dish_id, course_id) "
        "select family_id, id, %s from app.dish where family_id = %s and name like %s",
        (fam.courses["first"], fam.id, prefix + " %"),
    )


def dish_count(owner: Owner, fam: Fam) -> int:
    return int(owner.scalar("select count(*) from app.dish where family_id = %s", (fam.id,)))


def dish_row(owner: Owner, dish: UUID | str) -> tuple[Any, ...] | None:
    rows = owner.rows(
        "select name, status, notes, prep_time, version, archived_at is not null, ever_planned, "
        "modified_by from app.dish where id = %s",
        (dish,),
    )
    return rows[0] if rows else None


def family_state_hash(owner: Owner, fam: Fam) -> str:
    """Impronta di tutte le righe di piatti, portate-piatto e fonti di una famiglia (08 §6.2)."""
    parts = []
    for table in ("dish", "dish_course", "dish_source"):
        rows = owner.rows(
            f"select t::text from app.{table} t where family_id = %s order by 1",  # noqa: S608
            (fam.id,),
        )
        parts.append(json.dumps([r[0] for r in rows]))
    return "|".join(parts)


def security_event_types(owner: Owner) -> list[str]:
    return [r[0] for r in owner.rows("select event_type from app.security_event order by id")]


def change_events(owner: Owner) -> int:
    """Eventi di modifica scritti (la tabella arriva con SL-05: prima non c'è nulla da contare)."""
    exists = owner.scalar("select to_regclass('app.change_event') is not null")
    return int(owner.scalar("select count(*) from app.change_event")) if exists else 0


# --- payload e risposte ---------------------------------------------------------------------------


def payload(fam: Fam, name: str = "Frittata di zucchine", **over: Any) -> dict[str, Any]:
    """Un `DishWrite` valido (piano §4.2): portata «secondo» della famiglia, nessuna fonte."""
    body: dict[str, Any] = {
        "name": name,
        "courseIds": [str(fam.courses["second"])],
        "sources": [],
    }
    body.update(over)
    return body


def link(url: str, **extra: Any) -> dict[str, Any]:
    return {"kind": "link", "reference": url, **extra}


def book(title: str, page: str | None = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "book", "reference": title, **extra}
    if page is not None:
        out["page"] = page
    return out


def etag(response: Response) -> str:
    value = response.headers.get("etag")
    assert value is not None, "manca l'intestazione ETag"
    return str(value)


def error_fields(response: Response) -> dict[str, str]:
    """`errors[]` di un 422 come mappa campo -> codice."""
    body = response.json()
    assert body["code"] == "validation", body
    return {e["field"]: e["code"] for e in body.get("errors", [])}


def names(response: Response) -> list[str]:
    assert response.status_code == 200, (response.status_code, response.text)
    return [item["name"] for item in response.json()["items"]]


@dataclass
class Actor:
    """Un utente con sessione vera: ogni richiesta non sicura porta il suo token CSRF."""

    browser: Browser
    who: Who
    csrf: str
    log: list[Response] = field(default_factory=list)

    def get(self, path: str, **kw: Any) -> Response:
        return self.browser.get(path, **kw)

    def _write(
        self, method: str, path: str, body: Any, if_match: str | int | None, **kw: Any
    ) -> Response:
        headers = dict(kw.pop("headers", {}) or {})
        if if_match is not None:
            headers["If-Match"] = if_match if isinstance(if_match, str) else f'"{if_match}"'
        kw.setdefault("csrf", self.csrf)
        return self.browser.request(method, path, json=body, headers=headers, **kw)

    def post(
        self, path: str, body: Any = None, *, if_match: str | int | None = None, **kw: Any
    ) -> Response:
        return self._write("POST", path, {} if body is None else body, if_match, **kw)

    def put(
        self, path: str, body: Any, *, if_match: str | int | None = None, **kw: Any
    ) -> Response:
        return self._write("PUT", path, body, if_match, **kw)

    def delete(self, path: str, *, if_match: str | int | None = None, **kw: Any) -> Response:
        return self._write("DELETE", path, None, if_match, **kw)


def connect(browser: Browser, oidc: FakeOidc, who: Who) -> Actor:
    response = browser.login(oidc, who.identity)
    assert response.status_code == 302, response.text
    return Actor(browser, who, browser.session_csrf())


# --- richieste valide minime per operazione (08 §7.1 `request_builders`) ------------------------


@dataclass(frozen=True)
class Req:
    method: str
    path: str
    body: Any = None
    if_match: str | None = None
    query: str = ""


def request_for(op_id: str, fam: Fam, dish: UUID | str | None = None, version: int = 1) -> Req:
    """La richiesta valida minima di ogni operazione dell'archivio, contro la famiglia `fam`.

    Chi aggiunge un'operazione di famiglia amplia questa tabella: i test della matrice, del CSRF
    e dell'inventario falliscono per ogni `operationId` senza costruttore (fail closed).
    """
    builders: dict[str, Req] = {
        "catalog.course.list": Req("GET", "/api/v1/courses"),
        "catalog.dish.list": Req("GET", "/api/v1/dishes"),
        "catalog.dish.create": Req("POST", "/api/v1/dishes", payload(fam, "Nuovo piatto")),
        "catalog.dish.read": Req("GET", f"/api/v1/dishes/{dish}"),
        "catalog.dish.update": Req(
            "PUT", f"/api/v1/dishes/{dish}", payload(fam, "Piatto modificato"), f'"{version}"'
        ),
    }
    assert op_id in builders, (
        f"manca il costruttore di richiesta per {op_id} (tests/support/dishes.py)"
    )
    return builders[op_id]


def send(actor: Actor, req: Req, **kw: Any) -> Response:
    if req.method == "GET":
        return actor.get(req.path + req.query, **kw)
    if req.method == "POST":
        return actor.post(req.path, req.body, if_match=req.if_match, **kw)
    if req.method == "PUT":
        return actor.put(req.path, req.body, if_match=req.if_match, **kw)
    if req.method == "DELETE":
        return actor.delete(req.path, if_match=req.if_match, **kw)
    raise AssertionError(req.method)
