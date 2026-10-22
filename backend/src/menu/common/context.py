"""`RequestContext`: contesto della richiesta autenticata (piano §3), valore immutabile."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class RequestContext:
    correlation_id: UUID
    account_id: UUID | None
    session_id: UUID | None
    auth_time: datetime | None
    family_id: UUID | None
    person_id: UUID | None
    role: Literal["admin", "planner", "member"] | None
    family_status: Literal["active", "pending_deletion"] | None
