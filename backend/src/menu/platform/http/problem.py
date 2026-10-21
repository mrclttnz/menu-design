"""problem+json (RFC 9457): stati di ADR-0010 e traduzione degli errori di validazione.

`title` è generico e `detail` non c'è: nessun testo per l'utente e nessun dato (SR-021).
Il valore ricevuto non viene mai riflesso nella risposta (THR-107).
"""

import json
from http import HTTPStatus
from typing import Any, cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from menu.common import AppError, ErrorCode, ValidationCode

PROBLEM_MEDIA_TYPE = "application/problem+json"
MAX_REPORTED_ERRORS = 50

STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.REAUTH_REQUIRED: 403,
    ErrorCode.REAUTH_WRONG_ACCOUNT: 403,
    ErrorCode.CSRF_FAILED: 403,
    ErrorCode.CONFLICT: 412,
    ErrorCode.PRECONDITION_REQUIRED: 428,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.FAMILY_PENDING_DELETION: 409,
    ErrorCode.INVITE_INVALID: 404,
    ErrorCode.CODE_INVALID: 404,
    ErrorCode.AGE_DECLARATION_BLOCKED: 422,
    ErrorCode.ALREADY_IN_FAMILY: 409,
    ErrorCode.LAST_ADMIN: 409,
    ErrorCode.DISH_ALREADY_PLANNED: 409,
    ErrorCode.DISH_NOT_PLANNED: 409,
    ErrorCode.COURSE_IN_USE: 409,
    ErrorCode.QUOTA_EXCEEDED: 409,
    ErrorCode.RANGE_TOO_LARGE: 422,
    ErrorCode.COURSE_NOT_ALLOWED: 422,
    ErrorCode.PERSON_BEFORE_JOIN: 422,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.INTERNAL: 500,
}

_URL_TYPES = {"url_parsing", "url_scheme", "url_syntax_error", "url_type", "url_too_long"}
_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


class FieldError(BaseModel):
    field: str
    code: ValidationCode
    params: dict[str, Any] | None = None


class ProblemDetails(BaseModel):
    """Schema pubblicato in OpenAPI per ogni risposta d'errore."""

    type: str
    title: str
    status: int
    code: ErrorCode
    params: dict[str, Any] | None = None
    errors: list[FieldError] | None = None


def problem_response(
    code: ErrorCode,
    params: dict[str, Any] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> Response:
    status = STATUS_BY_CODE[code]
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "code": code.value,
    }
    if params:
        body["params"] = params
    if errors:
        body["errors"] = errors[:MAX_REPORTED_ERRORS]
    return Response(
        content=json.dumps(body, separators=(",", ":")),
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def field_error(field: str, code: ValidationCode, **params: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"field": field, "code": code.value}
    if params:
        item["params"] = params
    return item


def _field_path(loc: tuple[Any, ...]) -> str:
    parts = list(loc)
    if parts and parts[0] in _LOC_PREFIXES:
        parts = parts[1:]
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path


def _translate(error: dict[str, Any]) -> dict[str, Any]:
    kind = str(error.get("type", ""))
    loc = tuple(error.get("loc", ()))
    ctx = error.get("ctx") or {}
    if kind == "json_invalid":
        return field_error("", ValidationCode.INVALID_VALUE)
    field = _field_path(loc)
    if kind == "missing":
        return field_error(field, ValidationCode.REQUIRED)
    if kind == "string_too_long":
        return field_error(field, ValidationCode.STRING_TOO_LONG, max=ctx.get("max_length"))
    if kind == "too_long":
        return field_error(field, ValidationCode.LIMIT_REACHED, max=ctx.get("max_length"))
    if kind == "extra_forbidden":
        return field_error(field, ValidationCode.UNKNOWN_FIELD)
    if kind in _URL_TYPES:
        return field_error(field, ValidationCode.URL_INVALID)
    if kind.startswith(("date_", "datetime_")):
        return field_error(field, ValidationCode.DATE_INVALID)
    return field_error(field, ValidationCode.INVALID_VALUE)


async def app_error_handler(_: Request, exc: Exception) -> Response:
    exc = cast(AppError, exc)
    params = dict(exc.params)
    errors = params.pop("errors", None) if exc.code is ErrorCode.VALIDATION else None
    return problem_response(exc.code, params, errors)


async def validation_error_handler(_: Request, exc: Exception) -> Response:
    errors = [_translate(dict(e)) for e in cast(RequestValidationError, exc).errors()]
    return problem_response(ErrorCode.VALIDATION, errors=errors)


async def http_exception_handler(_: Request, exc: Exception) -> Response:
    """Errori del framework: 400 (corpo illeggibile) è una validazione; 404/405 `not_found`."""
    status = cast(StarletteHTTPException, exc).status_code
    if status == 400:
        return problem_response(
            ErrorCode.VALIDATION, errors=[field_error("", ValidationCode.INVALID_VALUE)]
        )
    if status in (404, 405):
        return problem_response(ErrorCode.NOT_FOUND)
    return problem_response(ErrorCode.INTERNAL)
