"""`If-Match` per le scritture versionate (ADR-0008, THR-107, A-23)."""

import re
from typing import Annotated

from fastapi import Header, Request

from menu.common import AppError, ErrorCode, ValidationCode
from menu.platform.http.problem import field_error

# Al massimo 18 cifre, sempre nell'intervallo di bigint. Usare `fullmatch`, mai `$`.
_IF_MATCH = re.compile(r'"(0|[1-9][0-9]{0,17})"')


async def expected_version(
    request: Request,
    if_match: Annotated[str | None, Header(alias="If-Match", description='ETag "<n>"')] = None,
) -> int:
    """Versione attesa. Assente: 428. Qualsiasi altra forma: 422 `invalid_value` (mai 500).

    Il valore ricevuto non viene riflesso nell'errore.
    """
    values = request.headers.getlist("if-match")
    if not values:
        raise AppError(ErrorCode.PRECONDITION_REQUIRED)
    match = _IF_MATCH.fullmatch(values[0]) if len(values) == 1 else None
    if match is None:
        raise AppError(
            ErrorCode.VALIDATION,
            {"errors": [field_error("If-Match", ValidationCode.INVALID_VALUE)]},
        )
    return int(match.group(1))
