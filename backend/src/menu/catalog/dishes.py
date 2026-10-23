"""Piatti e portate: letture, ricerca a cursore, creazione e modifica (SL-04; US-004, US-006).

Ogni funzione apre una sola transazione di famiglia (`family_tx`): la RLS limita le righe alla
famiglia del contesto e il `family_id` esplicito nelle query è una seconda difesa (SR-008, SR-041).
Gli identificativi di portate nel corpo o nei parametri si verificano nella stessa transazione
della scrittura: se uno non è della famiglia, `MissingReference` annulla tutto e la rotta risponde
`404` con l'evento `access.cross_family` (THR-020, THR-021). Il contenuto dei piatti non esce
mai in log né in eventi.
"""

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text

from menu import tenancy
from menu.catalog.schemas import (
    Course,
    DishDetail,
    DishSummary,
    DishUpdate,
    DishWrite,
    SourceView,
    conflict_params,
)
from menu.common import AppError, ErrorCode, RequestContext
from menu.tenancy import Tx

DISH_QUOTA = 2000
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
_CURSOR_MAX_LENGTH = 1024
_NAME_SEARCH_MAX_LENGTH = 1000

_QUOTA_LOCK = text(
    "select pg_advisory_xact_lock(hashtextextended('dish_quota:' || cast(:family as text), 0))"
)
_COUNT = text("select count(*) from app.dish where family_id = :family")
_COURSES_OF_FAMILY = text("select id from app.course where family_id = :family and id = any(:ids)")
_COURSE_LIST = text(
    "select id, base_code, name from app.course where family_id = :family "
    "order by array_position(array['starter', 'first', 'second', 'side', 'one_dish', 'dessert', "
    "'drink', 'other'], base_code), created_at, id"
)
_INSERT_DISH = text(
    "insert into app.dish (family_id, name, status, notes, prep_time, created_by) "
    "values (:family, :name, :status, :notes, :prep_time, :person) returning id"
)
_LOCK_DISH = text(
    "select version, created_by, modified_by, modified_at from app.dish "
    "where id = :id and family_id = :family for update"
)
_UPDATE_DISH = text(
    "update app.dish set name = :name, notes = :notes, prep_time = :prep_time, "
    "version = version + 1, modified_by = :person, modified_at = app.now_utc() "
    "where id = :id and family_id = :family"
)
_DELETE_COURSES = text("delete from app.dish_course where family_id = :family and dish_id = :id")
_DELETE_SOURCES = text("delete from app.dish_source where family_id = :family and dish_id = :id")
_INSERT_COURSE = text(
    "insert into app.dish_course (family_id, dish_id, course_id) values (:family, :id, :course)"
)
_INSERT_SOURCE = text(
    "insert into app.dish_source (family_id, dish_id, position, kind, reference, page, note) "
    "values (:family, :id, :position, :kind, :reference, :page, :note)"
)
_DETAIL = text(
    "select d.id, d.name, d.status, d.notes, d.prep_time, d.archived_at is not null as archived, "
    "d.ever_planned, d.created_by, d.version, "
    "array(select c.course_id from app.dish_course c "
    "where c.family_id = d.family_id and c.dish_id = d.id order by c.course_id) as course_ids "
    "from app.dish d where d.id = :id and d.family_id = :family"
)
_SOURCES = text(
    "select kind, reference, page, note from app.dish_source "
    "where family_id = :family and dish_id = :id order by position"
)
_COURSE_EXISTS = text("select 1 from app.course where id = :id and family_id = :family")
_DISH_EXISTS = text("select 1 from app.dish where id = :id and family_id = :family")

# Una sola istruzione costante: i filtri assenti valgono NULL (mai SQL costruito a pezzi, THR-025).
# Ricerca letterale: `\`, `%` e `_` della richiesta sono protetti prima del LIKE.
_LIST = text(
    "select d.id, d.name, d.status, d.prep_time, d.archived_at is not null as archived, "
    "d.ever_planned, d.name_search, "
    "array(select c.course_id from app.dish_course c "
    "where c.family_id = d.family_id and c.dish_id = d.id order by c.course_id) as course_ids "
    "from app.dish d where d.family_id = :family "
    "and (cast(:q as text) = '' or d.name_search like '%' || "
    "replace(replace(replace(app.search_norm(cast(:q as text)), '\\', '\\\\'), '%', '\\%'), "
    "'_', '\\_') || '%' escape '\\') "
    "and (cast(:archived as boolean) or d.archived_at is null) "
    "and (cast(:status as text) is null or d.status = cast(:status as text)) "
    "and (cast(:course as uuid) is null or exists (select 1 from app.dish_course f "
    "where f.family_id = d.family_id and f.dish_id = d.id "
    "and f.course_id = cast(:course as uuid))) "
    "and (cast(:after_name as text) is null or "
    "(d.name_search, d.id) > (cast(:after_name as text), cast(:after_id as uuid))) "
    "order by d.name_search, d.id limit :limit"
)


class MissingReference(Exception):  # noqa: N818 - non è un errore da riportare: segnale interno
    """Identificativo non trovato nella famiglia (inesistente o di un'altra famiglia)."""


class InvalidCursor(Exception):  # noqa: N818 - segnale interno, la rotta lo traduce in 422
    """Cursore non decodificabile o non valido."""


@dataclass(frozen=True)
class Page:
    items: list[DishSummary]
    next_cursor: str | None


def _family(ctx: RequestContext) -> UUID:
    if ctx.family_id is None or ctx.person_id is None:
        raise AppError(ErrorCode.FORBIDDEN)
    return ctx.family_id


def encode_cursor(name_search: str, dish_id: UUID) -> str:
    raw = json.dumps({"n": name_search, "i": str(dish_id)}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, UUID]:
    """Chiave (nome normalizzato, id) dell'ultima voce vista; ogni difetto è `InvalidCursor`."""
    if not cursor or len(cursor) > _CURSOR_MAX_LENGTH:
        raise InvalidCursor
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        data: Any = json.loads(raw)
        name, dish_id = data["n"], data["i"]
        if (
            set(data) != {"n", "i"}
            or not isinstance(name, str)
            or not isinstance(dish_id, str)
            or len(name) > _NAME_SEARCH_MAX_LENGTH
            or "\x00" in name
        ):
            raise InvalidCursor
        name.encode("utf-8")
        return name, UUID(dish_id)
    except (binascii.Error, ValueError, KeyError, TypeError) as error:
        raise InvalidCursor from error


def _unique(ids: list[UUID]) -> list[UUID]:
    return list(dict.fromkeys(ids))


def _require_courses(tx: Tx, family: UUID, ids: list[UUID]) -> None:
    found = {r[0] for r in tx.execute(_COURSES_OF_FAMILY, {"family": family, "ids": ids})}
    if found != set(ids):
        raise MissingReference


def _write_parts(
    tx: Tx, family: UUID, dish_id: UUID, body: DishUpdate, course_ids: list[UUID]
) -> None:
    tx.execute(_INSERT_COURSE, [{"family": family, "id": dish_id, "course": c} for c in course_ids])
    if body.sources:
        tx.execute(
            _INSERT_SOURCE,
            [
                {
                    "family": family,
                    "id": dish_id,
                    "position": position,
                    "kind": s.kind,
                    "reference": s.reference,
                    "page": s.page,
                    "note": s.note,
                }
                for position, s in enumerate(body.sources)
            ],
        )


def _load(tx: Tx, family: UUID, dish_id: UUID) -> DishDetail:
    row = tx.execute(_DETAIL, {"id": dish_id, "family": family}).mappings().one()
    sources = [
        SourceView.model_validate(_present(dict(s)))
        for s in tx.execute(_SOURCES, {"id": dish_id, "family": family}).mappings()
    ]
    fields: dict[str, Any] = {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "course_ids": list(row["course_ids"]),
        "archived": row["archived"],
        "ever_planned": row["ever_planned"],
        "sources": sources,
        "created_by": row["created_by"],
        "version": row["version"],
    }
    if row["prep_time"] is not None:
        fields["prep_time"] = row["prep_time"]
    if row["notes"] is not None:
        fields["notes"] = row["notes"]
    return DishDetail(**fields)


def _present(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def list_courses(ctx: RequestContext) -> list[Course]:
    family = _family(ctx)
    with tenancy.family_tx(ctx) as tx:
        rows = tx.execute(_COURSE_LIST, {"family": family}).mappings().all()
    return [Course(id=r["id"], base_code=r["base_code"], name=r["name"]) for r in rows]


def list_dishes(
    ctx: RequestContext,
    *,
    q: str,
    course_id: UUID | None,
    status: Literal["to_try", "tested"] | None,
    archived: bool,
    cursor: str | None,
    limit: int,
) -> Page:
    """Una pagina dell'archivio ordinata per (nome normalizzato, id); `MissingReference` se la
    portata del filtro non è della famiglia, `InvalidCursor` se il cursore non è valido."""
    family = _family(ctx)
    after = decode_cursor(cursor) if cursor is not None else None
    after_name, after_id = after if after is not None else (None, None)
    params: dict[str, Any] = {
        "family": family,
        "q": q,
        "archived": archived,
        "status": status,
        "course": course_id,
        "after_name": after_name,
        "after_id": after_id,
        "limit": limit + 1,
    }
    with tenancy.family_tx(ctx) as tx:
        if (
            course_id is not None
            and tx.execute(_COURSE_EXISTS, {"id": course_id, "family": family}).first() is None
        ):
            raise MissingReference
        rows = tx.execute(_LIST, params).mappings().all()
    page = rows[:limit]
    items = [DishSummary(**_summary_fields(r)) for r in page]
    next_cursor = (
        encode_cursor(page[-1]["name_search"], page[-1]["id"]) if len(rows) > limit else None
    )
    return Page(items, next_cursor)


def _summary_fields(row: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "course_ids": list(row["course_ids"]),
        "archived": row["archived"],
        "ever_planned": row["ever_planned"],
    }
    if row["prep_time"] is not None:
        fields["prep_time"] = row["prep_time"]
    return fields


def read_dish(ctx: RequestContext, dish_id: UUID) -> DishDetail:
    family = _family(ctx)
    with tenancy.family_tx(ctx) as tx:
        if tx.execute(_DISH_EXISTS, {"id": dish_id, "family": family}).first() is None:
            raise MissingReference
        return _load(tx, family, dish_id)


def create_dish(ctx: RequestContext, body: DishWrite) -> DishDetail:
    """Crea il piatto. Quota di 2.000 piatti per famiglia, archiviati compresi (SR-060).

    Il lock consultivo della famiglia serializza le creazioni concorrenti: il conteggio e
    l'inserimento avvengono nella stessa sezione critica (nessun superamento della quota).
    """
    family = _family(ctx)
    course_ids = _unique(body.course_ids)
    with tenancy.family_tx(ctx) as tx:
        tx.execute(_QUOTA_LOCK, {"family": family})
        _require_courses(tx, family, course_ids)
        if tx.execute(_COUNT, {"family": family}).scalar_one() >= DISH_QUOTA:
            raise AppError(ErrorCode.QUOTA_EXCEEDED, {"quota": "dishes", "limit": DISH_QUOTA})
        dish_id: UUID = tx.execute(
            _INSERT_DISH,
            {
                "family": family,
                "name": body.name,
                "status": body.status,
                "notes": body.notes,
                "prep_time": body.prep_time,
                "person": ctx.person_id,
            },
        ).scalar_one()
        _write_parts(tx, family, dish_id, body, course_ids)
        return _load(tx, family, dish_id)


def update_dish(
    ctx: RequestContext, dish_id: UUID, body: DishUpdate, expected_version: int
) -> DishDetail:
    """Sostituzione completa con controllo ottimistico (ADR-0008).

    La riga si blocca con `FOR UPDATE`: di due `PUT` con lo stesso `If-Match` il secondo attende,
    rilegge la versione già cresciuta e riceve `412`. Un piatto altrui o inesistente è sempre
    `MissingReference`, anche con una versione sbagliata (un `412` ne rivelerebbe l'esistenza).
    """
    family = _family(ctx)
    course_ids = _unique(body.course_ids)
    with tenancy.family_tx(ctx) as tx:
        current = tx.execute(_LOCK_DISH, {"id": dish_id, "family": family}).mappings().first()
        if current is None:
            raise MissingReference
        if current["version"] != expected_version:
            raise AppError(
                ErrorCode.CONFLICT,
                conflict_params(
                    _load(tx, family, dish_id),
                    current["modified_by"] or current["created_by"],
                    current["modified_at"],
                ),
            )
        _require_courses(tx, family, course_ids)
        tx.execute(
            _UPDATE_DISH,
            {
                "id": dish_id,
                "family": family,
                "name": body.name,
                "notes": body.notes,
                "prep_time": body.prep_time,
                "person": ctx.person_id,
            },
        )
        tx.execute(_DELETE_COURSES, {"family": family, "id": dish_id})
        tx.execute(_DELETE_SOURCES, {"family": family, "id": dish_id})
        _write_parts(tx, family, dish_id, body, course_ids)
        return _load(tx, family, dish_id)
