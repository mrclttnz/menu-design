"""`GET /plan`: la vista del piano, giorni e pasti con le voci (SL-06a; US-008, SR-060).

Una sola transazione di famiglia per una lettura coerente: i pasti dell'intervallo (`planning`)
e i riferimenti ai piatti e alle portate citati (`catalog`). Senza `from` e `to` si mostra la
settimana corrente della famiglia (lunedì-domenica nel suo fuso); un estremo mancante vale quello
della settimana corrente. L'intervallo è al massimo di 62 giorni. Le date si leggono solo come
`AAAA-MM-GG` (cifre ASCII): ogni altra forma è `validation` con `date_invalid`.
"""

import datetime as dt
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from menu import access, catalog, planning, tenancy
from menu.common import AppError, ErrorCode, RequestContext, ValidationCode
from menu.family import family_access
from menu.platform import AuthzRoute
from menu.platform.http.problem import field_error
from menu.views.schemas import DayView, PlanRefs, PlanView

router = APIRouter(prefix="/api/v1", route_class=AuthzRoute)

READ_PLAN = "plan.view.read"
_READ = Depends(family_access(READ_PLAN, writes=False))
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)

_DATE_QUERY = {"json_schema_extra": {"format": "date"}}
_PROBLEM = {
    "content": {
        "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
    }
}


def _parse(value: str | None) -> dt.date | None:
    """`None` se il parametro manca; `ValueError` se non è una data `AAAA-MM-GG` valida."""
    if value is None:
        return None
    if _ISO_DATE.fullmatch(value) is None:
        raise ValueError("data non valida")
    return dt.date.fromisoformat(value)


def _dates(start: str | None, end: str | None) -> tuple[dt.date | None, dt.date | None]:
    errors = []
    parsed: list[dt.date | None] = []
    for name, value in (("from", start), ("to", end)):
        try:
            parsed.append(_parse(value))
        except ValueError:
            parsed.append(None)
            errors.append(field_error(name, ValidationCode.DATE_INVALID))
    if errors:
        raise AppError(ErrorCode.VALIDATION, {"errors": errors})
    return parsed[0], parsed[1]


@router.get(
    "/plan",
    operation_id=READ_PLAN,
    response_model=PlanView,
    response_model_by_alias=True,
    response_model_exclude_unset=True,
    responses={
        200: {"description": "Giorni dell'intervallo, ciascuno con i suoi pasti"},
        401: {"description": "Sessione assente o scaduta", **_PROBLEM},
        422: {
            "description": (
                "`range_too_large` (`params.maxDays`: 62) oppure `validation` "
                "(`range_order`, `date_invalid`)"
            ),
            **_PROBLEM,
        },
    },
    openapi_extra={"x-authz": access.family_authz(READ_PLAN)},
)
def read_plan(
    ctx: Annotated[RequestContext, _READ],
    from_: Annotated[
        str | None,
        Query(
            alias="from",
            description="Primo giorno, `AAAA-MM-GG` (default: lunedì della settimana corrente)",
            **_DATE_QUERY,
        ),
    ] = None,
    to: Annotated[
        str | None,
        Query(
            description="Ultimo giorno incluso, `AAAA-MM-GG` (default: domenica corrente)",
            **_DATE_QUERY,
        ),
    ] = None,
) -> PlanView:
    start, end = _dates(from_, to)
    with tenancy.family_tx(ctx) as tx:
        plan = planning.read_plan(tx, ctx, start, end)
        items = [item for _, meals in plan.days for meal in meals for item in meal.items]
        dishes, courses = catalog.read_refs(
            tx,
            ctx,
            {i.dish_id for i in items if i.dish_id is not None},
            {i.course_id for i in items if i.course_id is not None},
        )
    return PlanView(
        from_=plan.start,
        to=plan.end,
        today=plan.today,
        timezone=plan.timezone,
        days=[DayView(date=day, meals=meals) for day, meals in plan.days],
        refs=PlanRefs(dishes=dishes, courses=courses),
    )
