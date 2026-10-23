"""Contesto di famiglia di una sessione, riletto a ogni richiesta (SR-005, piano §3).

`context_for` costruisce il `RequestContext` dal ruolo **attuale** della persona: un cambio di
ruolo o una rimozione valgono dalla richiesta successiva. Il ruolo non viene mai dal client.
La persona si trova senza conoscere la famiglia grazie a `p_person_self` (RLS per account);
poi la transazione passa al contesto di quella famiglia per leggerne i dati.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import text

from menu import tenancy
from menu.common import RequestContext
from menu.identity import SessionInfo

Role = Literal["admin", "planner", "member"]
FamilyStatus = Literal["active", "pending_deletion"]

_PERSON = text(
    "select id, family_id, role from app.person where account_id = :account_id "
    "and status = 'active'"
)
_FAMILY = text(
    "select id, name, timezone, status, deletion_due_at, app.family_today() as today "
    "from app.family where id = :family_id"
)


@dataclass(frozen=True)
class FamilyBrief:
    id: UUID
    name: str
    timezone: str
    today: date
    status: FamilyStatus
    deletion_due_at: datetime | None


@dataclass(frozen=True)
class Membership:
    context: RequestContext
    family: FamilyBrief | None


def membership_for(session: SessionInfo, correlation_id: UUID) -> Membership:
    base = RequestContext(
        correlation_id=correlation_id,
        account_id=session.account_id,
        session_id=session.session_id,
        auth_time=session.auth_time,
        family_id=None,
        person_id=None,
        role=None,
        family_status=None,
    )
    with tenancy.account_tx(session.account_id) as tx:
        person = tx.execute(_PERSON, {"account_id": session.account_id}).mappings().first()
        if person is None:
            return Membership(base, None)
        role = cast(Role, person["role"])
        tenancy.bind_context(
            tx, family_id=person["family_id"], account_id=session.account_id, role=role
        )
        row = tx.execute(_FAMILY, {"family_id": person["family_id"]}).mappings().first()
    if row is None:
        return Membership(base, None)
    status = cast(FamilyStatus, row["status"])
    context = RequestContext(
        correlation_id=correlation_id,
        account_id=session.account_id,
        session_id=session.session_id,
        auth_time=session.auth_time,
        family_id=person["family_id"],
        person_id=person["id"],
        role=role,
        family_status=status,
    )
    brief = FamilyBrief(
        id=row["id"],
        name=row["name"],
        timezone=row["timezone"],
        today=row["today"],
        status=status,
        deletion_due_at=row["deletion_due_at"],
    )
    return Membership(context, brief)


def context_for(session: SessionInfo, correlation_id: UUID) -> RequestContext:
    return membership_for(session, correlation_id).context
