"""Chi può entrare: account esistente, riscatto del bootstrap, `not_member` (US-001, US-002).

Implementa `identity.LoginResolver` (piano §2.2) nella transazione del callback.
- Account già membro: entra nella propria famiglia (ASM-050: una famiglia per account); il suo
  login non consuma mai il bootstrap di altri.
- Altrimenti si cerca un bootstrap non riscattato e non scaduto per l'hash dell'email verificata
  (`app.bootstrap_resolve`, confronto esatto: né punti né suffissi `+`, THR-003). Il bootstrap si
  blocca con `SELECT … FOR UPDATE` **prima** di creare l'account, così chi perde la corsa non
  lascia nulla (SR-049, AC-002.4); poi si crea la persona Amministratore e si riscatta con lo
  stesso predicato (`expires_at >= app.now_utc()`, scadenza inclusa); da qui conta solo il `sub`.
- Nessun bootstrap: `NotMember`, senza account né persona.
"""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import text

from menu import tenancy
from menu.common import email_sha256
from menu.identity import GoogleIdentity, LoginOutcome, Member, NotMember
from menu.tenancy import Tx

_MEMBERSHIP = text(
    "select id, family_id, role from app.person where account_id = :account_id "
    "and status = 'active'"
)
_BOOTSTRAPS = text("select bootstrap_id, family_id from app.bootstrap_resolve(:email_sha256)")
_LOCK = text(
    "select id from app.family_bootstrap where id = :bootstrap_id and redeemed_at is null "
    "and expires_at >= app.now_utc() for update"
)
_NEW_ADMIN = text(
    "insert into app.person (family_id, kind, status, account_id, role, joined_on) "
    "values (:family_id, 'account', 'active', :account_id, 'admin', app.family_today()) "
    "returning id"
)
_REDEEM = text(
    "update app.family_bootstrap set redeemed_at = app.now_utc(), "
    "redeemed_person_id = :person_id, email_sha256 = null "
    "where id = :bootstrap_id and redeemed_at is null and expires_at >= app.now_utc()"
)


class FamilyOnboarding:
    def resolve(
        self,
        tx: Tx,
        who: GoogleIdentity,
        existing_account: UUID | None,
        ensure_account: Callable[[], UUID],
    ) -> LoginOutcome:
        if existing_account is not None:
            member = self._existing_member(tx, existing_account)
            if member is not None:
                return member
        candidates = tx.execute(_BOOTSTRAPS, {"email_sha256": email_sha256(who.email)}).all()
        for bootstrap_id, family_id in candidates:
            member = self._redeem(tx, bootstrap_id, family_id, ensure_account)
            if member is not None:
                return member
        return NotMember()

    @staticmethod
    def _existing_member(tx: Tx, account_id: UUID) -> Member | None:
        tenancy.bind_context(tx, account_id=account_id)
        row = tx.execute(_MEMBERSHIP, {"account_id": account_id}).mappings().first()
        if row is None:
            return None
        return Member(account_id, row["family_id"], row["id"], row["role"])

    @staticmethod
    def _redeem(
        tx: Tx, bootstrap_id: UUID, family_id: UUID, ensure_account: Callable[[], UUID]
    ) -> Member | None:
        tenancy.bind_context(tx, family_id=family_id, role="admin")
        locked = tx.execute(_LOCK, {"bootstrap_id": bootstrap_id}).scalar_one_or_none()
        if locked is None:
            return None  # riscattato da un login concorrente, o scaduto nel frattempo
        account_id = ensure_account()
        tenancy.bind_context(tx, family_id=family_id, account_id=account_id, role="admin")
        person_id: UUID = tx.execute(
            _NEW_ADMIN, {"family_id": family_id, "account_id": account_id}
        ).scalar_one()
        redeemed = tx.execute(_REDEEM, {"person_id": person_id, "bootstrap_id": bootstrap_id})
        if redeemed.rowcount != 1:
            raise RuntimeError("bootstrap non riscattabile dopo il blocco")
        return Member(account_id, family_id, person_id, "admin")
