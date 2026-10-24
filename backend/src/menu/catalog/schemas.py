"""DTO dell'archivio piatti (piano §4.2): `DishWrite`, `DishSummary`, `DishDetail`, `Course`.

I corpi in ingresso sono chiusi (`extra='forbid'`, SR-010) e si leggono solo per nome camelCase.
Le lunghezze sono quelle di AC-004.5 e 05-data §4.2: il database le ripete come ultima difesa, ma
il rifiuto con il campo nominato lo dà l'API. Le risposte omettono i campi facoltativi assenti
(`response_model_exclude_unset`): chi costruisce un DTO imposta solo ciò che ha un valore.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError

from menu.catalog.text import check_required, check_storable, is_http_url

NAME_MAX = 120
NOTES_MAX = 2000
SOURCES_MAX = 10
REFERENCE_MAX = 500
PAGE_MAX = 20
SOURCE_NOTE_MAX = 500
COURSES_MAX = 50

DishStatus = Literal["to_try", "tested"]
PrepTime = Literal["under_30", "30_60", "over_60"]
SourceKind = Literal["link", "book", "magazine", "other"]
BaseCode = Literal["starter", "first", "second", "side", "one_dish", "dessert", "drink", "other"]

_Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=NAME_MAX),
    AfterValidator(check_storable),
    AfterValidator(check_required),
]
_Notes = Annotated[str, StringConstraints(max_length=NOTES_MAX), AfterValidator(check_storable)]
_Reference = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=REFERENCE_MAX),
    AfterValidator(check_storable),
    AfterValidator(check_required),
]
_Page = Annotated[str, StringConstraints(max_length=PAGE_MAX), AfterValidator(check_storable)]
_SourceNote = Annotated[
    str, StringConstraints(max_length=SOURCE_NOTE_MAX), AfterValidator(check_storable)
]


class Body(BaseModel):
    """Corpo in ingresso: chiuso, camelCase, nessun nome di campo Python accettato."""

    model_config = ConfigDict(alias_generator=to_camel, extra="forbid")


class View(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Source(Body):
    kind: SourceKind
    reference: _Reference
    page: _Page | None = None
    note: _SourceNote | None = None

    @field_validator("reference", mode="after")
    @classmethod
    def _link_is_http(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("kind") == "link" and not is_http_url(value):
            raise PydanticCustomError("url_parsing", "indirizzo non valido")
        return value

    @field_validator("page", mode="after")
    @classmethod
    def _page_only_for_print(cls, value: str | None, info: ValidationInfo) -> str | None:
        kind = info.data.get("kind")
        if value is not None and kind is not None and kind not in ("book", "magazine"):
            raise PydanticCustomError("invalid_value", "pagina ammessa solo per libri e riviste")
        return value


class DishUpdate(Body):
    """`PUT`: sostituzione completa della scheda; lo stato cambia con `POST /status` (SL-05)."""

    name: _Name
    course_ids: Annotated[
        list[UUID],
        Field(max_length=COURSES_MAX, json_schema_extra={"minItems": 1}),
    ]
    notes: _Notes | None = None
    prep_time: PrepTime | None = None
    sources: Annotated[list[Source], Field(max_length=SOURCES_MAX)] = []

    @field_validator("course_ids", mode="after")
    @classmethod
    def _at_least_one_course(cls, value: list[UUID]) -> list[UUID]:
        if not value:
            raise PydanticCustomError("course_required", "almeno una portata")
        return value


class DishWrite(DishUpdate):
    """`POST`: come `DishUpdate` più lo stato iniziale (default «da provare»)."""

    status: DishStatus = "to_try"


class StatusChange(Body):
    """`POST /status`: solo il nuovo stato (la scheda si modifica con `PUT`)."""

    status: DishStatus


class SourceView(View):
    kind: SourceKind
    reference: str
    page: str | None = None
    note: str | None = None


class DishSummary(View):
    id: UUID
    name: str
    status: DishStatus
    course_ids: list[UUID]
    prep_time: PrepTime | None = None
    archived: bool
    ever_planned: bool


class DishDetail(DishSummary):
    notes: str | None = None
    sources: list[SourceView]
    created_by: UUID
    version: int


class DishPage(View):
    items: list[DishSummary]
    next_cursor: str | None


class Course(View):
    id: UUID
    base_code: BaseCode | None
    name: str | None


class CoursePage(View):
    items: list[Course]


def conflict_params(
    current: DishDetail, modified_by: UUID | None, modified_at: datetime
) -> dict[str, Any]:
    return {
        "current": current.model_dump(mode="json", by_alias=True, exclude_unset=True),
        "modifiedBy": None if modified_by is None else str(modified_by),
        "modifiedAt": modified_at.isoformat().replace("+00:00", "Z"),
    }
