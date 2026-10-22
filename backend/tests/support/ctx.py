"""Costruzione di `RequestContext` per i test (plan §3: definito in `menu.common`)."""

from typing import Any, Literal
from uuid import UUID, uuid4


def make_ctx(
    family_id: UUID | None,
    account_id: UUID | None = None,
    role: Literal["admin", "planner", "member"] | None = "planner",
) -> Any:
    from menu.common import RequestContext

    return RequestContext(
        correlation_id=uuid4(),
        account_id=account_id,
        session_id=None,
        auth_time=None,
        family_id=family_id,
        person_id=None,
        role=role,
        family_status="active" if family_id else None,
    )
