"""Rotte dell'archivio piatti (piano §4.3; SL-04): portate, elenco con ricerca, scheda.

Ogni rotta dichiara `x-authz` ricavato dalla matrice di `access` e dipende da `family_access`:
sessione (con CSRF sulle scritture), ruolo attuale e permesso, prima della validazione dei campi
del corpo (il JSON è già stato letto: un JSON malformato dà `422` anche a chi non ha il permesso).
Le risorse non trovate per identificativo rispondono tutte `404 not_found` con l'evento
`access.cross_family`, che siano inesistenti o di un'altra famiglia (SR-008, THR-020).
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import AfterValidator, StringConstraints

from menu import access
from menu.catalog import dishes
from menu.catalog.schemas import (
    CoursePage,
    DishDetail,
    DishPage,
    DishStatus,
    DishUpdate,
    DishWrite,
    StatusChange,
)
from menu.catalog.text import check_storable
from menu.common import AppError, ErrorCode, RequestContext, ValidationCode
from menu.family import family_access
from menu.platform import AuthzRoute, expected_version
from menu.platform.http.problem import field_error

router = APIRouter(prefix="/api/v1", route_class=AuthzRoute)

LIST_COURSES = "catalog.course.list"
LIST_DISHES = "catalog.dish.list"
CREATE_DISH = "catalog.dish.create"
READ_DISH = "catalog.dish.read"
UPDATE_DISH = "catalog.dish.update"
SET_STATUS = "catalog.dish.set_status"

_READ_COURSES = Depends(family_access(LIST_COURSES, writes=False))
_READ_LIST = Depends(family_access(LIST_DISHES, writes=False))
_WRITE_CREATE = Depends(family_access(CREATE_DISH, writes=True))
_READ_ONE = Depends(family_access(READ_DISH, writes=False))
_WRITE_UPDATE = Depends(family_access(UPDATE_DISH, writes=True))
_WRITE_STATUS = Depends(family_access(SET_STATUS, writes=True))

SearchText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=120), AfterValidator(check_storable)
]
DishId = Annotated[UUID, Path(alias="dishId")]


def _etag(response: Response, dish: DishDetail) -> None:
    response.headers["ETag"] = f'"{dish.version}"'


@router.get(
    "/courses",
    operation_id=LIST_COURSES,
    response_model=CoursePage,
    response_model_exclude_unset=True,
    openapi_extra={"x-authz": access.family_authz(LIST_COURSES)},
)
def list_courses(ctx: Annotated[RequestContext, _READ_COURSES]) -> CoursePage:
    return CoursePage(items=dishes.list_courses(ctx))


@router.get(
    "/dishes",
    operation_id=LIST_DISHES,
    response_model=DishPage,
    response_model_exclude_unset=True,
    openapi_extra={"x-authz": access.family_authz(LIST_DISHES)},
)
def list_dishes(
    ctx: Annotated[RequestContext, _READ_LIST],
    q: Annotated[SearchText, Query(description="Nome, anche parziale")] = "",
    course_id: Annotated[UUID | None, Query(alias="courseId")] = None,
    status: DishStatus | None = None,
    archived: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=dishes.MAX_LIMIT)] = dishes.DEFAULT_LIMIT,
) -> DishPage:
    try:
        page = dishes.list_dishes(
            ctx,
            q=q,
            course_id=course_id,
            status=status,
            archived=archived,
            cursor=cursor,
            limit=limit,
        )
    except dishes.InvalidCursor:
        raise AppError(
            ErrorCode.VALIDATION,
            {"errors": [field_error("cursor", ValidationCode.INVALID_VALUE)]},
        ) from None
    except dishes.MissingReference:
        raise access.cross_family(ctx, LIST_DISHES) from None
    return DishPage(items=page.items, next_cursor=page.next_cursor)


@router.post(
    "/dishes",
    operation_id=CREATE_DISH,
    status_code=201,
    response_model=DishDetail,
    response_model_exclude_unset=True,
    openapi_extra={"x-authz": access.family_authz(CREATE_DISH)},
)
def create_dish(
    ctx: Annotated[RequestContext, _WRITE_CREATE], body: DishWrite, response: Response
) -> DishDetail:
    try:
        dish = dishes.create_dish(ctx, body)
    except dishes.MissingReference:
        raise access.cross_family(ctx, CREATE_DISH) from None
    _etag(response, dish)
    return dish


@router.get(
    "/dishes/{dishId}",
    operation_id=READ_DISH,
    response_model=DishDetail,
    response_model_exclude_unset=True,
    openapi_extra={"x-authz": access.family_authz(READ_DISH)},
)
def read_dish(
    ctx: Annotated[RequestContext, _READ_ONE], dish_id: DishId, response: Response
) -> DishDetail:
    try:
        dish = dishes.read_dish(ctx, dish_id)
    except dishes.MissingReference:
        raise access.cross_family(ctx, READ_DISH) from None
    _etag(response, dish)
    return dish


@router.put(
    "/dishes/{dishId}",
    operation_id=UPDATE_DISH,
    response_model=DishDetail,
    response_model_exclude_unset=True,
    openapi_extra={"x-authz": access.family_authz(UPDATE_DISH)},
)
def update_dish(
    ctx: Annotated[RequestContext, _WRITE_UPDATE],
    version: Annotated[int, Depends(expected_version)],
    dish_id: DishId,
    body: DishUpdate,
    response: Response,
) -> DishDetail:
    try:
        dish = dishes.update_dish(ctx, dish_id, body, version)
    except dishes.MissingReference:
        raise access.cross_family(ctx, UPDATE_DISH) from None
    _etag(response, dish)
    return dish


def _problem(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        },
    }


@router.post(
    "/dishes/{dishId}/status",
    operation_id=SET_STATUS,
    response_model=DishDetail,
    response_model_exclude_unset=True,
    responses={
        200: {
            "description": "Scheda aggiornata",
            "headers": {
                "ETag": {
                    "description": 'Versione della scheda, `"<n>"`',
                    "schema": {"type": "string"},
                }
            },
        },
        401: _problem("Sessione assente o scaduta"),
        403: _problem("Ruolo senza permesso (Membro) o token CSRF non valido"),
        404: _problem("Piatto non trovato nella famiglia"),
        412: _problem("Versione superata: `params.current` è la scheda attuale"),
        422: _problem("Stato o `If-Match` non validi"),
        428: _problem("`If-Match` assente"),
        429: _problem(
            "Limite di frequenza (sessione, account) o tetto giornaliero di scritture tracciate "
            "della famiglia; `Retry-After` in secondi"
        ),
    },
    openapi_extra={"x-authz": access.family_authz(SET_STATUS)},
)
def set_dish_status(
    ctx: Annotated[RequestContext, _WRITE_STATUS],
    version: Annotated[int, Depends(expected_version)],
    dish_id: DishId,
    body: StatusChange,
    response: Response,
) -> DishDetail:
    try:
        dish = dishes.set_status(ctx, dish_id, body.status, version)
    except dishes.MissingReference:
        raise access.cross_family(ctx, SET_STATUS) from None
    _etag(response, dish)
    return dish
