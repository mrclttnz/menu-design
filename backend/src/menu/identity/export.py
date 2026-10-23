"""Contributore di export di `identity` (05-data §9.3, SR-072): solo perimetro `self`.

Dell'account: la propria riga (nome, email, date), senza `auth_subject`, `email_sha256` né
altri identificativi del provider. Delle sessioni: dispositivo e date, senza IP né hash.
Il perimetro `family` non riceve nulla: l'Amministratore non ottiene email né sessioni altrui.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from menu.common import ExportRows

_ACCOUNT = text(
    "select id, auth_provider, email, email_verified_at, display_name, age_declared_at, "
    "privacy_version, privacy_ack_at, created_at from app.account where id = :account_id"
)
_SESSIONS = text(
    "select id, device_label, created_at, last_used_at from app.session "
    "where account_id = :account_id order by created_at, id"
)


class IdentityExport:
    tables = frozenset({"account", "session"})

    def export_family(self, tx: Any) -> ExportRows:
        return {}

    def export_self(self, tx: Any, account_id: UUID, person_id: UUID | None) -> ExportRows:
        params = {"account_id": account_id}
        return {
            "account": [dict(r) for r in tx.execute(_ACCOUNT, params).mappings()],
            "session": [dict(r) for r in tx.execute(_SESSIONS, params).mappings()],
        }
