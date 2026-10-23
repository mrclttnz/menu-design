"""Costruttori di dati di identità per i test (08 §5.1): via `owner`, mai dall'API.

Dati sintetici: email `@example.test`, nomi inventati. Le righe si scrivono con il ruolo
proprietario, così non dipendono dalle funzioni sotto test; i flussi di fiducia (login,
riscatto del bootstrap) si provano invece dall'API.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from menu.common import email_sha256
from support.fake_oidc import Identity
from support.owner import Owner

FROZEN = "2026-01-01"


def make_family(owner: Owner, name: str = "Famiglia Alfa") -> UUID:
    family = uuid4()
    owner.execute(
        "insert into app.family (id, name, frozen_through) values (%s, %s, %s)",
        (family, name, FROZEN),
    )
    return family


def make_account(
    owner: Owner,
    *,
    account_id: UUID | None = None,
    sub: str | None = None,
    email: str | None = None,
    display_name: str = "Alice Alfa",
) -> UUID:
    """Account Google sintetico; `email_sha256` come lo scrive il servizio (ADR-0004)."""
    account = account_id or uuid4()
    address = email or f"acc-{str(account)[:8]}@example.test"
    owner.execute(
        "insert into app.account (id, auth_provider, auth_subject, email, email_sha256, "
        "email_verified_at, display_name) values (%s, 'google', %s, %s, %s, %s, %s) "
        "on conflict (id) do nothing",
        (
            account,
            sub or f"sub-{account}",
            address,
            email_sha256(address),
            datetime.now(UTC),
            display_name,
        ),
    )
    return account


def make_person(
    owner: Owner, family: UUID, account: UUID, role: str = "member", **cols: Any
) -> UUID:
    person = uuid4()
    values: dict[str, Any] = {
        "id": person,
        "family_id": family,
        "kind": "account",
        "status": "active",
        "account_id": account,
        "role": role,
        "joined_on": FROZEN,
    }
    values.update(cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.person ({names}) values ({marks})", tuple(values.values()))  # noqa: S608  (nomi di colonna scritti dal test)
    return person


def make_member(
    owner: Owner,
    family: UUID,
    *,
    sub: str,
    email: str,
    role: str = "member",
    display_name: str = "Mario Membro",
) -> tuple[UUID, UUID]:
    """Account con la sua persona attiva nella famiglia: `(account_id, person_id)`."""
    account = make_account(owner, sub=sub, email=email, display_name=display_name)
    return account, make_person(owner, family, account, role)


def make_bootstrap(owner: Owner, family: UUID, email: str, *, age_days: float = 0) -> UUID:
    """Bootstrap non riscattato per `email` creato `age_days` giorni fa (scadenza a 168 ore)."""
    created = datetime.now(UTC) - timedelta(days=age_days)
    bootstrap = uuid4()
    owner.execute(
        "insert into app.family_bootstrap (id, family_id, email_sha256, created_at, expires_at) "
        "values (%s, %s, %s, %s, %s)",
        (bootstrap, family, email_sha256(email), created, created + timedelta(hours=168)),
    )
    return bootstrap


# --- lo stato letto dal database (solo lettura, via owner) --------------------------------------


def count(owner: Owner, table: str) -> int:
    return int(owner.scalar(f"select count(*) from app.{table}"))  # noqa: S608  (tabella scelta dal test)


def sessions(owner: Owner, account: UUID | None = None) -> list[tuple[Any, ...]]:
    query = (
        "select id, account_id, token_hash, csrf_token_hash, created_at, last_used_at, "
        "auth_time, device_label, ip_prefix from app.session"
    )
    if account is None:
        return owner.rows(query + " order by created_at, id")
    return owner.rows(query + " where account_id = %s order by created_at, id", (account,))


def age_session(owner: Owner, session_id: UUID, *, created_days: float, used_days: float) -> None:
    """Sposta i dati, non l'orologio (08 §4.4): `created_at` e `last_used_at` a N giorni fa."""
    now = datetime.now(UTC)
    owner.execute(
        "update app.session set created_at = %s, last_used_at = %s, auth_time = %s where id = %s",
        (
            now - timedelta(days=created_days),
            now - timedelta(days=used_days),
            now - timedelta(days=created_days),
            session_id,
        ),
    )


def security_events(owner: Owner, like: str = "%") -> list[dict[str, Any]]:
    cols = (
        "event_type, outcome, actor_kind, actor_account_id, actor_role, family_id, "
        "target_type, target_id, details::text"
    )
    rows = owner.rows(
        f"select {cols} from app.security_event where event_type like %s order by id",  # noqa: S608
        (like,),
    )
    names = [c.split("::")[0].strip() for c in cols.split(",")]
    return [dict(zip(names, r, strict=True)) for r in rows]


def all_text_of_tables(owner: Owner, tables: list[str]) -> str:
    """Tutto il contenuto testuale e binario delle tabelle, per cercarvi i segreti (THR-005)."""
    chunks: list[str] = []
    for table in tables:
        for row in owner.rows(f"select t::text from app.{table} t"):  # noqa: S608
            chunks.append(str(row[0]))
    return "\n".join(chunks)


# --- il mondo di prova dell'accesso (08 §5.2, ridotto alle famiglie che servono a SL-03a) ---------


@dataclass(frozen=True)
class AlfaWorld:
    """Famiglia Alfa con un Amministratore e un Membro; più un'identità senza famiglia."""

    family: UUID
    admin: Identity
    admin_account: UUID
    admin_person: UUID
    member: Identity
    member_account: UUID
    member_person: UUID
    outsider: Identity


ADMIN = Identity(sub="sub-alfa-admin", email="alfa.admin@example.test", name="Alice Alfa")
MEMBER = Identity(sub="sub-alfa-member", email="alfa.member@example.test", name="Mario Membro")
OUTSIDER = Identity(sub="sub-orfano", email="orfano.canary@example.test", name="Orfeo Orfano")


def make_alfa(owner: Owner) -> AlfaWorld:
    family = make_family(owner, "Famiglia Alfa")
    admin_account, admin_person = make_member(
        owner, family, sub=ADMIN.sub, email=ADMIN.email, role="admin", display_name="Alice Alfa"
    )
    member_account, member_person = make_member(
        owner,
        family,
        sub=MEMBER.sub,
        email=MEMBER.email,
        role="member",
        display_name="Mario Membro",
    )
    return AlfaWorld(
        family, ADMIN, admin_account, admin_person, MEMBER, member_account, member_person, OUTSIDER
    )
