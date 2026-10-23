"""Valori scambiati tra `identity` e il resto dell'app, e il protocollo `LoginResolver`."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from menu.tenancy import Tx

AuthOutcomeCode = Literal["not_member", "auth_cancelled", "auth_failed", "reauth_wrong_account"]


@dataclass(frozen=True)
class GoogleIdentity:
    """Ciò che serve del token ID verificato (SR-014: nome, email, `sub`)."""

    subject: str = field(repr=False)
    email: str = field(repr=False)
    display_name: str = field(repr=False)


@dataclass(frozen=True)
class SessionInfo:
    """Sessione valida risolta dal cookie. Il token CSRF non compare in `repr`."""

    session_id: UUID
    account_id: UUID
    display_name: str = field(repr=False)
    created_at: datetime
    last_used_at: datetime
    auth_time: datetime
    csrf_token: str = field(repr=False)
    csrf_token_hash: bytes = field(repr=False)
    renewed_max_age: int | None = None  # secondi, se la finestra mobile è stata rinnovata ora


@dataclass(frozen=True)
class Member:
    account_id: UUID
    family_id: UUID
    person_id: UUID
    role: Literal["admin", "planner", "member"]


@dataclass(frozen=True)
class NotMember:
    """Nessuna famiglia: l'accesso non crea account, persona né sessione (SR-049)."""


LoginOutcome = Member | NotMember


class LoginResolver(Protocol):
    """Implementato da `family.onboarding`, collegato in `menu.app` (piano §2.2).

    Gira nella transazione di `identity` (`tx`, senza contesto di famiglia). `existing_account`
    è l'account già noto per quel `sub`; `ensure_account` crea o aggiorna la riga `account`
    e va chiamata solo dopo aver deciso che la persona può entrare (nessun account senza famiglia).
    """

    def resolve(
        self,
        tx: Tx,
        who: GoogleIdentity,
        existing_account: UUID | None,
        ensure_account: Callable[[], UUID],
    ) -> LoginOutcome: ...


@dataclass(frozen=True)
class AuthOutcomeRead:
    code: str
    params: dict[str, str] | None
