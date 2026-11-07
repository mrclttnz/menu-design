"""Rotte del pasto (piano §4.3; SL-06a): lettura e presenza.

Il pasto si indirizza per (data, tipo, slot) e la famiglia viene dalla sessione: nessun
identificativo di risorsa altrui nel percorso, quindi nessun `404` per «pasto di un'altra
famiglia». Uno slot non valido per il tipo è `404 not_found` (ADR-0009). Il permesso si controlla
prima della validazione del corpo e di `If-Match`; la versione del contenuto è l'`ETag`.
"""

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response

from menu import access
from menu.common import AppError, ErrorCode, RequestContext
from menu.family import family_access
from menu.planning import meals
from menu.planning.schemas import MealType, MealView, PresenceChange
from menu.platform import AuthzRoute, expected_version

router = APIRouter(prefix="/api/v1", route_class=AuthzRoute)

READ_MEAL = "meal.view.read"
SET_PRESENCE = "meal.presence.write"

_READ = Depends(family_access(READ_MEAL, writes=False))
_WRITE = Depends(family_access(SET_PRESENCE, writes=True))

Day = Annotated[dt.date, Path(alias="date")]
Kind = Annotated[MealType, Path(alias="mealType")]
Slot = Annotated[int, Path()]


def _problem(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        },
    }


def _etag_header(description: str) -> dict[str, Any]:
    return {"ETag": {"description": description, "schema": {"type": "string"}}}


def _key(day: dt.date, meal_type: MealType, slot: int) -> meals.MealKey:
    key = meals.MealKey(day, meal_type, slot)
    if not key.is_valid:
        raise AppError(ErrorCode.NOT_FOUND)
    return key


def _etag(response: Response, meal: MealView) -> None:
    response.headers["ETag"] = f'"{meal.content_version}"'


@router.get(
    "/meals/{date}/{mealType}/{slot}",
    operation_id=READ_MEAL,
    response_model=MealView,
    response_model_exclude_unset=True,
    responses={
        200: {
            "description": "Il pasto",
            "headers": _etag_header('Versione del contenuto, `"<n>"` (`0` se mai scritto)'),
        },
        401: _problem("Sessione assente o scaduta"),
        404: _problem("Slot non valido per il tipo di pasto"),
        422: _problem("Data o tipo di pasto non validi"),
    },
    openapi_extra={"x-authz": access.family_authz(READ_MEAL)},
)
def read_meal(
    ctx: Annotated[RequestContext, _READ],
    day: Day,
    meal_type: Kind,
    slot: Slot,
    response: Response,
) -> MealView:
    meal = meals.read_meal(ctx, _key(day, meal_type, slot))
    _etag(response, meal)
    return meal


@router.put(
    "/meals/{date}/{mealType}/{slot}/presence",
    operation_id=SET_PRESENCE,
    response_model=MealView,
    response_model_exclude_unset=True,
    responses={
        200: {
            "description": "Il pasto aggiornato",
            "headers": _etag_header('Nuova versione del contenuto, `"<n>"`'),
        },
        401: _problem("Sessione assente o scaduta"),
        403: _problem("Ruolo senza permesso (Membro) o token CSRF non valido"),
        404: _problem("Slot non valido per il tipo di pasto"),
        412: _problem("Versione superata: `params.current` è il pasto attuale"),
        422: _problem("Corpo, data, tipo di pasto o `If-Match` non validi"),
        428: _problem("`If-Match` assente"),
        429: _problem(
            "Limite di frequenza (sessione, account) o tetto giornaliero di scritture tracciate "
            "della famiglia; `Retry-After` in secondi"
        ),
    },
    openapi_extra={"x-authz": access.family_authz(SET_PRESENCE)},
)
def set_presence(
    ctx: Annotated[RequestContext, _WRITE],
    version: Annotated[int, Depends(expected_version)],
    day: Day,
    meal_type: Kind,
    slot: Slot,
    body: PresenceChange,
    response: Response,
) -> MealView:
    meal = meals.set_presence(ctx, _key(day, meal_type, slot), body.present, version)
    _etag(response, meal)
    return meal
