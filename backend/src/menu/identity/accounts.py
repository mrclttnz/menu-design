"""Tabella `account` (nessuna RLS: solo `system_tx` e solo da questo modulo, 05-data §6.1).

L'identità è la coppia (provider, `sub`): l'email non lo è (Google riassegna gli indirizzi,
SR-033). `display_name` è proposto da Google alla creazione e poi appartiene all'utente
(SR-054): l'upsert non lo tocca. Si conservano solo nome, email e `sub` (SR-014).
"""

import re
import unicodedata
from uuid import UUID

from sqlalchemy import text

from menu.common import email_sha256
from menu.identity.models import GoogleIdentity
from menu.tenancy import Tx

DISPLAY_NAME_MAX = 60
FALLBACK_NAME = "Utente"
SUBJECT_MAX = 255
EMAIL_MAX = 254
_EMAIL = re.compile(r"[^@\s\x00-\x1f\x7f]+@[^@\s\x00-\x1f\x7f]+")

_FIND = text(
    "select id from app.account where auth_provider = 'google' and auth_subject = :subject"
)
_UPSERT = text(
    "insert into app.account (auth_provider, auth_subject, email, email_sha256, "
    "email_verified_at, display_name) "
    "values ('google', :subject, :email, :email_sha256, app.now_utc(), :display_name) "
    "on conflict (auth_provider, auth_subject) do update set email = excluded.email, "
    "email_sha256 = excluded.email_sha256, email_verified_at = excluded.email_verified_at "
    "returning id"
)


def valid_email(value: object) -> str | None:
    """Email del token ID se conforme al `CHECK` della tabella, altrimenti `None`."""
    if not isinstance(value, str):
        return None
    email = value.strip()
    if len(email) > EMAIL_MAX or _EMAIL.fullmatch(email) is None:
        return None
    return email


def clean_display_name(name: object, email: str) -> str:
    """Nome proposto da Google ridotto al `CHECK` (1..60 caratteri, non vuoto, senza controlli)."""
    candidates = [name if isinstance(name, str) else "", email.partition("@")[0], FALLBACK_NAME]
    for candidate in candidates:
        cleaned = (
            "".join(ch for ch in candidate if not unicodedata.category(ch).startswith("C"))
            .strip()[:DISPLAY_NAME_MAX]
            .strip()
        )
        if cleaned:
            return cleaned
    return FALLBACK_NAME


def find_account(tx: Tx, subject: str) -> UUID | None:
    found: UUID | None = tx.execute(_FIND, {"subject": subject}).scalar_one_or_none()
    return found


def upsert_account(tx: Tx, who: GoogleIdentity) -> UUID:
    """Crea l'account o ne aggiorna email e hash (a ogni login, 05-data §4.1)."""
    account_id: UUID = tx.execute(
        _UPSERT,
        {
            "subject": who.subject,
            "email": who.email,
            "email_sha256": email_sha256(who.email),
            "display_name": who.display_name,
        },
    ).scalar_one()
    return account_id
