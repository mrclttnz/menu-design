"""`SessionView` (piano §4.2): la forma anonima e quella con sessione.

Mai email, `sub` né dati di altri account (SR-014, THR-028). L'esito di autenticazione
(`authOutcome`) compare anche nella forma anonima: un accesso non riuscito lascia anonimi, ma la
SPA deve poterne leggere l'esito, una sola volta (ADR-0004 rev. 3).
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class View(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class AuthOutcomeView(View):
    code: Literal["not_member", "auth_cancelled", "auth_failed", "reauth_wrong_account"]
    params: dict[str, str] | None = None


class NoticeView(View):
    """Avviso alla famiglia (SL-24). Sempre vuoto in SL-03a.

    `subjectPersonId` (piano §4.2) si aggiunge con SL-24: il test di contratto di SL-03a vieta
    oggi ogni nome di proprietà che contenga "subject" (cerca il `sub` di Google), da precisare.
    """

    id: UUID
    kind: Literal["admin_recovered"]
    created_at: datetime


class AccountView(View):
    id: UUID
    display_name: str


class FamilyView(View):
    id: UUID
    name: str
    timezone: str
    today: date
    status: Literal["active", "pending_deletion"]
    deletion_due_at: datetime | None = None


class PersonView(View):
    id: UUID
    role: Literal["admin", "planner", "member"]


class AnonymousSession(View):
    authenticated: Literal[False]
    notices: list[NoticeView]
    auth_outcome: AuthOutcomeView | None = None


class AuthenticatedSession(View):
    authenticated: Literal[True]
    csrf_token: str
    account: AccountView
    family: FamilyView | None
    person: PersonView | None
    privacy_review_required: bool
    notices: list[NoticeView]
    auth_outcome: AuthOutcomeView | None = None
