"""Registro di sicurezza `security_event`: sola aggiunta, immutabile, senza FK (05-data §4.1,
§3.2; SR-020, SR-057; THR-111, THR-026). SL-02.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from support.owner import Owner

Connect = Callable[..., psycopg.Connection]
INSERT = (
    "insert into app.security_event (event_type, outcome, actor_kind) "
    "values ('login.success', 'success', 'account')"
)


def _seed_one(owner: Owner) -> None:
    owner.execute(INSERT)


# --- menu_app: solo INSERT (SR-057, THR-111) --------------------------------------------------


def test_menu_app_can_insert_an_event(owner: Owner, connect_app: Connect) -> None:
    with connect_app() as conn:
        conn.execute(INSERT)
    assert owner.scalar("select count(*) from app.security_event") == 1


def test_menu_app_insert_fills_server_utc_time_and_identity(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    """SR-057: orario UTC del server (app.now_utc()), id generato dal database."""
    frozen_now(datetime(2026, 10, 22, 9, 30, tzinfo=UTC))
    with connect_app() as conn:
        conn.execute(INSERT)
    row = owner.rows("select occurred_at, id from app.security_event")[0]
    assert row[0] == datetime(2026, 10, 22, 9, 30, tzinfo=UTC)
    assert isinstance(row[1], int)


@pytest.mark.parametrize(
    "statement",
    [
        "select count(*) from app.security_event",
        "select event_type from app.security_event",
        "update app.security_event set outcome = 'failure'",
        "delete from app.security_event",
        "truncate app.security_event",
    ],
)
def test_menu_app_is_denied_select_update_delete_and_truncate(
    owner: Owner, connect_app: Connect, statement: str
) -> None:
    """SR-057, 05-data §3.2: `menu_app` ha solo INSERT; lettura solo dalla console."""
    _seed_one(owner)
    with connect_app() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)
    assert owner.scalar("select outcome from app.security_event") == "success"


def test_menu_app_cannot_read_events_back_with_insert_returning(connect_app: Connect) -> None:
    with connect_app() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(INSERT.encode() + b" returning event_type")


def test_menu_backup_can_read_the_log(owner: Owner, connect_app: Connect) -> None:
    """Il dump con `menu_backup` contiene il registro (THR-085)."""
    _seed_one(owner)
    with connect_app("menu_backup") as conn:
        assert conn.execute("select count(*) from app.security_event").fetchone() == (1,)


# --- immutabilità anche per il proprietario (08 §6.4, trigger BEFORE UPDATE) ------------------


@pytest.mark.parametrize(
    "assignment",
    [
        "outcome = 'failure'",
        "event_type = 'login.failure'",
        "actor_kind = 'system'",
        "details = '{\"x\": 1}'::jsonb",
        "occurred_at = occurred_at + interval '1 day'",
        "family_id = gen_random_uuid()",
        "ip = '203.0.113.0', outcome = 'failure'",  # IP ammesso + altra colonna: ramo 1
    ],
)
def test_trigger_rejects_updates_even_for_menu_owner(owner: Owner, assignment: str) -> None:
    """THR-111: unica modifica ammessa è la sola colonna `ip` (retention, SR-051).
    05-data §4.1: l'errore è `insufficient_privilege` (42501)."""
    _seed_one(owner)
    before = owner.rows("select * from app.security_event")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner.execute(f"update app.security_event set {assignment}")  # noqa: S608
    assert owner.rows("select * from app.security_event") == before


def test_trigger_allows_the_ip_only_update_of_the_retention_job(owner: Owner) -> None:
    """05-data §4.1: la sola colonna `ip` si può aggiornare (troncamento a 90 giorni)."""
    owner.execute(
        "insert into app.security_event (event_type, outcome, actor_kind, ip) "
        "values ('login.failure', 'failure', 'anonymous', '203.0.113.77')"
    )
    owner.execute("update app.security_event set ip = '203.0.113.0'")
    assert str(owner.scalar("select host(ip) from app.security_event")) == "203.0.113.0"


# --- vincoli ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("event_type", "Login.Success"),
        ("event_type", "loginsuccess"),
        ("event_type", "login."),
        ("event_type", "1login.success"),
        ("event_type", "login success"),
        ("outcome", "ok"),
        ("actor_kind", "admin"),
        ("actor_role", "gestore"),
    ],
)
def test_check_constraints_reject_invalid_values(owner: Owner, column: str, value: str) -> None:
    row = {"event_type": "login.success", "outcome": "success", "actor_kind": "account"}
    row[column] = value
    cols = ", ".join(row)
    marks = ", ".join(["%s"] * len(row))
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute(
            f"insert into app.security_event ({cols}) values ({marks})",  # noqa: S608
            tuple(row.values()),
        )


def test_event_type_longer_than_64_characters_is_rejected(owner: Owner) -> None:
    with pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.StringDataRightTruncation)):
        owner.execute(
            "insert into app.security_event (event_type, outcome, actor_kind) "
            "values (%s, 'success', 'system')",
            ("a." + "b" * 63,),
        )


def test_details_are_limited_to_1024_bytes(owner: Owner) -> None:
    """Solo codici e ID nei dettagli (SR-021): il database impone anche la dimensione."""
    owner.execute(
        "insert into app.security_event (event_type, outcome, actor_kind, details) "
        "values ('x.small', 'success', 'system', '{\"k\": \"v\"}'::jsonb)"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute(
            "insert into app.security_event (event_type, outcome, actor_kind, details) "
            "values ('x.big', 'success', 'system', jsonb_build_object('k', repeat('x', 2000)))"
        )


def test_events_survive_the_deletion_of_account_and_family_references(owner: Owner) -> None:
    """Nessuna FK: l'evento sopravvive alla famiglia e all'account per 12 mesi (05-data §4.1)."""
    family = uuid4()
    owner.execute(
        "insert into app.family (id, name, frozen_through) values (%s, 'F', '2026-01-01')",
        (family,),
    )
    owner.execute(
        "insert into app.security_event (event_type, outcome, actor_kind, family_id, "
        "actor_account_id) values ('x.kept', 'success', 'account', %s, %s)",
        (family, uuid4()),
    )
    owner.execute("delete from app.family where id = %s", (family,))
    assert owner.scalar("select family_id from app.security_event") == family


def test_security_event_has_no_email_or_secret_columns(catalog: psycopg.Connection) -> None:
    cols = {
        r[0]
        for r in catalog.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'app' and table_name = 'security_event'"
        ).fetchall()
    }
    assert cols >= {"id", "occurred_at", "event_type", "outcome", "actor_kind", "details", "ip"}
    assert not {c for c in cols if "email" in c or "token" in c or "secret" in c or "hash" in c}


def test_security_event_is_not_a_family_table_for_rls(catalog: psycopg.Connection) -> None:
    """05-data §6.3: registro globale senza RLS di famiglia (protezione = privilegi)."""
    from support.inventory import NON_FAMILY_TABLES, app_tables, family_tables

    assert "security_event" in app_tables(catalog), "precondizione: la tabella esiste"
    assert "security_event" in NON_FAMILY_TABLES
    assert "security_event" not in family_tables(catalog)


# --- ramo `ip` del trigger, isolato (CR-SL02-005): cambia SOLO la colonna ip ---------------------


def _seed_with_ip(owner: Owner, ip: str | None) -> None:
    owner.execute(
        "insert into app.security_event (event_type, outcome, actor_kind, ip) "
        "values ('login.failure', 'failure', 'anonymous', %s)",
        (ip,),
    )


def _ip_text(owner: Owner) -> str | None:
    value = owner.scalar("select host(ip) from app.security_event")
    return None if value is None else str(value)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("203.0.113.77", "198.51.100.1", id="v4-altro-indirizzo"),
        pytest.param("203.0.113.77", "203.0.114.0", id="v4-altra-rete-/24"),
        pytest.param("203.0.113.77", "203.0.113.78", id="v4-altro-host-stessa-rete"),
        pytest.param("203.0.113.77", "2001:db8::1", id="v4-a-v6"),
        pytest.param("2001:db8:1234:5678::1", "2001:db8:1234:5678::2", id="v6-intero-indirizzo"),
        pytest.param("2001:db8:1234:5678::1", "2001:db8:9999::", id="v6-altra-rete-/48"),
        pytest.param("2001:db8:1234:5678::1", "203.0.113.0", id="v6-a-v4"),
        pytest.param(None, "203.0.113.0", id="da-NULL-a-un-indirizzo"),
    ],
)
def test_ip_only_update_to_a_different_address_is_refused_with_42501(
    owner: Owner, old: str | None, new: str
) -> None:
    """Il troncamento non può diventare riscrittura dell'IP (SR-051, THR-111)."""
    _seed_with_ip(owner, old)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner.execute("update app.security_event set ip = %s", (new,))
    assert _ip_text(owner) == old


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        pytest.param("203.0.113.77", "203.0.113.0", "203.0.113.0", id="v4-a-/24"),
        pytest.param("2001:db8:1234:5678::1", "2001:db8:1234::", "2001:db8:1234::", id="v6-a-/48"),
        pytest.param("203.0.113.77", None, None, id="v4-azzerato"),
        pytest.param("2001:db8:1234:5678::1", None, None, id="v6-azzerato"),
        pytest.param("203.0.113.77", "203.0.113.77", "203.0.113.77", id="v4-invariato"),
        pytest.param(None, None, None, id="NULL-invariato"),
    ],
)
def test_ip_only_update_allows_truncation_clearing_and_no_change(
    owner: Owner, old: str | None, new: str | None, expected: str | None
) -> None:
    _seed_with_ip(owner, old)
    owner.execute("update app.security_event set ip = %s", (new,))
    assert _ip_text(owner) == expected
