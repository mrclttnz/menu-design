"""Schema di identità (migrazione 0005, SL-03a): `account`, `session`, `auth_flow`, FK `person`.

05-data §4.1 (`account`, `session`, `auth_flow`), §4.2 (`person.account_id`), §3.2 (privilegi),
§9.1. SR-014 (campi dell'account), SR-033 (chiave dell'identità = coppia (provider, `sub`), l'email
non è unica), SR-037 (solo hash dei token), SR-049 (nessun account senza famiglia: lo prova
`tests/integration/test_auth_login.py`), THR-005, THR-028.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from support.accounts import make_account, make_family, make_person
from support.owner import Owner

Connect = Callable[..., psycopg.Connection]
H32 = bytes(range(32))


def _columns(catalog: psycopg.Connection, table: str) -> dict[str, tuple[Any, ...]]:
    rows = catalog.execute(
        "select column_name, data_type, is_nullable, character_maximum_length, column_default "
        "from information_schema.columns where table_schema = 'app' and table_name = %s",
        (table,),
    ).fetchall()
    return {r[0]: r[1:] for r in rows}


def _insert_account(owner: Owner, **cols: Any) -> UUID:
    values: dict[str, Any] = {
        "id": uuid4(),
        "auth_subject": f"sub-{uuid4()}",
        "email": "alice.alfa@example.test",
        "display_name": "Alice Alfa",
    }
    values.update(cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.account ({names}) values ({marks})", tuple(values.values()))  # noqa: S608  (nomi di colonna scritti dal test)
    return values["id"]  # type: ignore[no-any-return]


def _insert_session(owner: Owner, account: UUID, **cols: Any) -> UUID:
    values: dict[str, Any] = {
        "id": uuid4(),
        "account_id": account,
        "token_hash": uuid4().bytes + uuid4().bytes,
        "csrf_token_hash": uuid4().bytes + uuid4().bytes,
        "auth_time": datetime(2026, 10, 1, tzinfo=UTC),
    }
    values.update(cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.session ({names}) values ({marks})", tuple(values.values()))  # noqa: S608  (nomi di colonna scritti dal test)
    return values["id"]  # type: ignore[no-any-return]


def _flow_values(**cols: Any) -> dict[str, Any]:
    created = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    values: dict[str, Any] = {
        "handle_hash": uuid4().bytes + uuid4().bytes,
        "purpose": "login",
        "return_to": "/piano",
        "state_hash": H32,
        "nonce_hash": H32,
        "code_verifier": "v" * 43,
        "created_at": created,
        "expires_at": created.replace(minute=10),
    }
    values.update(cols)
    return values


def _insert_flow(owner: Owner, **cols: Any) -> None:
    values = _flow_values(**cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.auth_flow ({names}) values ({marks})", tuple(values.values()))  # noqa: S608  (nomi di colonna scritti dal test)


# --- account --------------------------------------------------------------------------------------


def test_account_columns_follow_the_data_model(catalog: psycopg.Connection) -> None:
    """05-data §4.1: tipi, obbligatorietà e lunghezze; nessun campo oltre SR-014."""
    cols = _columns(catalog, "account")
    assert cols, "tabella app.account assente (migrazione 0005)"
    expected = {
        "id": ("uuid", "NO"),
        "auth_provider": ("text", "NO"),
        "auth_subject": ("character varying", "NO"),
        "email": ("character varying", "NO"),
        "email_sha256": ("bytea", "YES"),
        "email_verified_at": ("timestamp with time zone", "YES"),
        "display_name": ("text", "NO"),
        "age_declared_at": ("timestamp with time zone", "YES"),
        "privacy_version": ("character varying", "YES"),
        "privacy_ack_at": ("timestamp with time zone", "YES"),
        "last_active_on": ("date", "YES"),
        "created_at": ("timestamp with time zone", "NO"),
    }
    assert {k: v[:2] for k, v in cols.items()} == expected
    assert cols["auth_subject"][2] == 255
    assert cols["email"][2] == 254
    assert "google" in str(cols["auth_provider"][3])
    assert "now_utc" in str(cols["created_at"][3]), "il default è app.now_utc(), mai now() nudo"


def test_account_identity_is_provider_and_sub_and_the_email_is_not_unique(owner: Owner) -> None:
    """SR-033: due account con la stessa email sono ammessi (Google riassegna gli indirizzi);
    due con lo stesso (provider, sub) no."""
    _insert_account(owner, auth_subject="sub-1", email="stesso@example.test")
    _insert_account(owner, auth_subject="sub-2", email="stesso@example.test")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_account(owner, auth_subject="sub-1", email="altra@example.test")


@pytest.mark.parametrize(
    ("cols", "why"),
    [
        ({"auth_provider": "password"}, "solo Google nell'MVP (CHG-020)"),
        ({"auth_provider": "apple"}, "provider sconosciuto"),
        ({"auth_subject": None}, "sub obbligatorio"),
        ({"email": None}, "email obbligatoria"),
        ({"email": "x" * 250 + "@e.test"}, "email oltre 254 caratteri"),
        ({"display_name": ""}, "nome vuoto"),
        ({"display_name": "   "}, "nome di soli spazi"),
        ({"display_name": "n" * 61}, "nome oltre 60 caratteri"),
        ({"email_sha256": b"\x01" * 31}, "hash dell'email di 31 byte"),
        ({"email_sha256": b"\x01" * 33}, "hash dell'email di 33 byte"),
        ({"privacy_version": "v1", "privacy_ack_at": None}, "versione senza istante"),
    ],
)
def test_account_constraints_reject_invalid_rows(
    owner: Owner, cols: dict[str, Any], why: str
) -> None:
    # `email` è varchar(254) (05-data §4.1): oltre la lunghezza PostgreSQL dà
    # string_data_right_truncation (22001, DataError) prima di qualunque CHECK.
    with pytest.raises(
        (
            psycopg.errors.CheckViolation,
            psycopg.errors.NotNullViolation,
            psycopg.errors.StringDataRightTruncation,
        )
    ):
        _insert_account(owner, **cols)


def test_account_accepts_a_name_of_exactly_60_characters_and_an_email_hash(owner: Owner) -> None:
    _insert_account(owner, display_name="n" * 60, email_sha256=H32)
    assert owner.scalar("select count(*) from app.account") == 1


def test_account_has_no_row_level_security_and_menu_app_has_full_dml(
    catalog: psycopg.Connection,
) -> None:
    """05-data §6.1 (decisione dell'utente): `account` senza RLS, solo `system_tx` in `identity`;
    05-data §3.2: SELECT, INSERT, UPDATE, DELETE a `menu_app`, niente TRUNCATE."""
    assert catalog.execute(
        "select relrowsecurity from pg_class where oid = 'app.account'::regclass"
    ).fetchone() == (False,)
    for priv, expected in (
        ("SELECT", True),
        ("INSERT", True),
        ("UPDATE", True),
        ("DELETE", True),
        ("TRUNCATE", False),
    ):
        got = catalog.execute(
            "select has_table_privilege('menu_app', 'app.account'::regclass, %s)", (priv,)
        ).fetchone()
        assert got == (expected,), priv


# --- person.account_id ------------------------------------------------------------------------


def test_person_account_id_references_account(owner: Owner) -> None:
    """Piano §9 ordine 5: la FK nasce con `account`."""
    family = make_family(owner)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        make_person(owner, family, uuid4(), "admin")
    account = make_account(owner)
    make_person(owner, family, account, "admin")


def test_an_account_with_an_active_person_cannot_be_deleted(owner: Owner) -> None:
    """05-data §4.2: `ON DELETE RESTRICT`; l'eliminazione passa dalla procedura (§7.3, §9.2)."""
    family = make_family(owner)
    account = make_account(owner)
    make_person(owner, family, account, "admin")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        owner.execute("delete from app.account where id = %s", (account,))
    assert owner.scalar("select count(*) from app.account where id = %s", (account,)) == 1


def test_deleting_an_account_without_person_removes_its_sessions(owner: Owner) -> None:
    """05-data §4.1: `session.account_id` ON DELETE CASCADE (SR-005: eliminazione dell'account)."""
    account = make_account(owner)
    _insert_session(owner, account)
    _insert_session(owner, account)
    owner.execute("delete from app.account where id = %s", (account,))
    assert owner.scalar("select count(*) from app.session") == 0


# --- session --------------------------------------------------------------------------------------


def test_session_columns_follow_the_data_model(catalog: psycopg.Connection) -> None:
    cols = _columns(catalog, "session")
    assert cols, "tabella app.session assente (migrazione 0005)"
    assert {k: v[:2] for k, v in cols.items()} == {
        "id": ("uuid", "NO"),
        "account_id": ("uuid", "NO"),
        "token_hash": ("bytea", "NO"),
        "csrf_token_hash": ("bytea", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "last_used_at": ("timestamp with time zone", "NO"),
        "auth_time": ("timestamp with time zone", "NO"),
        "device_label": ("character varying", "YES"),
        "ip_prefix": ("inet", "YES"),
    }
    assert cols["device_label"][2] == 80
    assert "now_utc" in str(cols["created_at"][3])
    assert "now_utc" in str(cols["last_used_at"][3])
    assert not any("token" in c and c not in {"token_hash", "csrf_token_hash"} for c in cols), (
        "nessuna colonna può contenere un token in chiaro (SR-037)"
    )


def test_session_timestamps_default_to_the_database_clock(
    owner: Owner, frozen_now: Callable[[datetime], None]
) -> None:
    instant = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
    frozen_now(instant)
    account = make_account(owner)
    session = _insert_session(owner, account)
    row = owner.rows("select created_at, last_used_at from app.session where id = %s", (session,))
    assert row == [(instant, instant)]


@pytest.mark.parametrize(
    "cols",
    [
        {"token_hash": b"\x01" * 31},
        {"token_hash": b"\x01" * 33},
        {"csrf_token_hash": b"\x01" * 16},
        {"ip_prefix": "203.0.113.77/32"},
        {"ip_prefix": "203.0.113.0/16"},
        {"ip_prefix": "2001:db8::/64"},
    ],
)
def test_session_constraints_reject_invalid_rows(owner: Owner, cols: dict[str, Any]) -> None:
    account = make_account(owner)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_session(owner, account, **cols)


@pytest.mark.parametrize("prefix", ["203.0.113.0/24", "2001:db8:abcd::/48"])
def test_session_accepts_truncated_ip_prefixes_only(owner: Owner, prefix: str) -> None:
    """SR-051: l'IP si conserva già troncato (/24 o /48)."""
    account = make_account(owner)
    _insert_session(owner, account, ip_prefix=prefix, device_label="Chrome · Android")


def test_session_token_hash_is_unique(owner: Owner) -> None:
    account = make_account(owner)
    _insert_session(owner, account, token_hash=H32)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_session(owner, account, token_hash=H32)


def test_session_has_account_rls_enabled_and_forced_with_the_standard_policies(
    catalog: psycopg.Connection,
) -> None:
    from support.inventory import app_tables

    info = app_tables(catalog)["session"]
    assert info["rls"]
    assert info["force"]
    assert {"p_session_self", "p_owner", "p_backup"} <= set(info["policies"])
    assert (
        info["policies"]["p_session_self"]["using"]
        .replace(" ", "")
        .startswith("(account_id=app.current_account_id()")
    )


# --- auth_flow --------------------------------------------------------------------------------


def test_auth_flow_columns_follow_the_data_model(catalog: psycopg.Connection) -> None:
    cols = _columns(catalog, "auth_flow")
    assert cols, "tabella app.auth_flow assente (migrazione 0005)"
    required = {
        "handle_hash": ("bytea", "NO"),
        "purpose": ("text", "NO"),
        "session_id": ("uuid", "YES"),
        "return_to": ("character varying", "YES"),
        "state_hash": ("bytea", "NO"),
        "nonce_hash": ("bytea", "NO"),
        "code_verifier": ("character varying", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "expires_at": ("timestamp with time zone", "NO"),
    }
    assert {k: v[:2] for k, v in cols.items() if k in required} == required
    assert cols["return_to"][2] == 200
    assert cols["code_verifier"][2] == 128
    # Lo stato del flusso non contiene state e nonce in chiaro: solo hash (SR-033, THR-002).
    assert "state" not in cols
    assert "nonce" not in cols
    assert "handle" not in cols


def test_auth_flow_accepts_a_login_flow(owner: Owner) -> None:
    _insert_flow(owner)
    assert owner.scalar("select count(*) from app.auth_flow") == 1


@pytest.mark.parametrize(
    "cols",
    [
        {"purpose": "signup"},
        {"purpose": "login", "session_id": uuid4()},
        {"purpose": "reauth", "session_id": None},
        {"handle_hash": b"\x01" * 31},
        {"state_hash": b"\x01" * 31},
        {"nonce_hash": b"\x01" * 33},
        {"code_verifier": "v" * 42},
        {"code_verifier": "v" * 129},
        {"return_to": "https://evil.example/piano"},
        {"return_to": "//evil.example"},
        {"return_to": "piano"},
        {"return_to": "/pi ano"},
        {"return_to": "/piano#x"},
        {"return_to": "/piano\r\nSet-Cookie: x=y"},
        {"return_to": "/" + "a" * 200},
        {"expires_at": datetime(2026, 10, 1, 12, 10, 1, tzinfo=UTC)},
    ],
)
def test_auth_flow_constraints_reject_invalid_rows(owner: Owner, cols: dict[str, Any]) -> None:
    """05-data §4.1: finalità, legame con la sessione, lunghezze, `return_to` relativo, durata
    massima di 10 minuti (THR-002, THR-010)."""
    with pytest.raises(
        (
            psycopg.errors.CheckViolation,
            psycopg.errors.ForeignKeyViolation,
            psycopg.errors.DataError,
        )
    ):
        _insert_flow(owner, **cols)


def test_auth_flow_reauth_is_bound_to_a_session(owner: Owner) -> None:
    """Il flusso `reauth` ha sempre `session_id` (ADR-0004 rev. 2, SR-068); si cancella con lei."""
    account = make_account(owner)
    session = _insert_session(owner, account)
    _insert_flow(owner, purpose="reauth", session_id=session)
    owner.execute("delete from app.session where id = %s", (session,))
    assert owner.scalar("select count(*) from app.auth_flow") == 0


def test_auth_flow_allows_a_flow_without_return_to(owner: Owner) -> None:
    _insert_flow(owner, return_to=None)


def test_menu_app_has_full_dml_on_auth_flow_and_session(catalog: psycopg.Connection) -> None:
    """05-data §3.2: `account`, `auth_flow`, `session` sì/sì/sì/sì (RLS per account sulla."""
    for table in ("auth_flow", "session"):
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            got = catalog.execute(
                "select has_table_privilege('menu_app', %s::regclass, %s)", (f"app.{table}", priv)
            ).fetchone()
            assert got == (True,), f"menu_app senza {priv} su {table}"
