"""Funzioni `console_*` (SECURITY DEFINER, ADR-0011, 05-data §3.3). SL-02.

US-002: AC-002.1 (parte database della console), AC-002.2, AC-002.3. SR-012, SR-020, SR-033
(bootstrap a 7 giorni, lato dati), SR-040, SR-057. THR-003, THR-051, THR-053.

Assunzioni di contratto (nel report di slice, da confermare con il backend-developer):
- i tipi di evento sono `console.family_bootstrap`, `console.audit_note`; il nome dell'evento di
  `console_security_events` non è fissato: i test contano gli eventi `console.%` senza nominarlo;
- una chiamata non valida SOLLEVA un errore del database (nessuna riga creata);
- `console_security_events` non restituisce l'IP completo (ADR-0011: "IP troncati").
"""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from menu import tenancy
from menu.common import email_sha256
from support import pg
from support.owner import Owner

Connect = Callable[..., psycopg.Connection]
FrozenNow = Callable[[datetime], None]

BASE_COURSES = {"starter", "first", "second", "side", "one_dish", "dessert", "drink", "other"}
CANARY_EMAIL = "CANARY-Console.Admin+tag@Example.test"
GOOD_REF = "AUD-20261022-1"


def _bootstrap(
    connect_app: Connect, name: str = "Famiglia Alfa", email_hash: bytes | None = None
) -> UUID:
    with connect_app("menu_console") as conn:
        row = conn.execute(
            "select app.console_bootstrap_family(%s, %s)",
            (name, email_sha256(CANARY_EMAIL) if email_hash is None else email_hash),
        ).fetchone()
    assert row is not None
    value: UUID = row[0]
    return value


def _counts(owner: Owner) -> dict[str, int]:
    tables = ("family", "family_default_meal", "person", "family_bootstrap", "course")
    out = {t: owner.scalar(f"select count(*) from app.{t}") for t in tables}  # noqa: S608
    out["security_event_success"] = owner.scalar(
        "select count(*) from app.security_event where outcome = 'success'"
    )
    return out


def _events(owner: Owner, like: str = "console.%") -> list[tuple[Any, ...]]:
    return owner.rows(
        "select event_type, outcome, actor_kind, family_id, correlation_id, details, "
        "actor_account_id from app.security_event where event_type like %s order by id",
        (like,),
    )


# --- console_bootstrap_family: successo (AC-002.1, parte console) ----


def test_ac_002_1_bootstrap_creates_the_family_with_defaults_and_a_seven_day_bootstrap(
    owner: Owner, connect_app: Connect, frozen_now: FrozenNow
) -> None:
    frozen_now(datetime(2026, 10, 22, 22, 30, tzinfo=UTC))  # 00:30 del 23 a Roma
    family_id = _bootstrap(connect_app)

    fam = owner.rows(
        "select name, timezone, status, frozen_through, created_at from app.family where id = %s",
        (family_id,),
    )
    assert len(fam) == 1
    name, tz, status, frozen_through, created_at = fam[0]
    assert (name, tz, status) == ("Famiglia Alfa", "Europe/Rome", "active")
    assert frozen_through == date(2026, 10, 22), "oggi locale (23) meno 1"
    assert created_at == datetime(2026, 10, 22, 22, 30, tzinfo=UTC), "orologio = app.now_utc()"

    meals = owner.rows(
        "select meal_type from app.family_default_meal where family_id = %s", (family_id,)
    )
    assert {m[0] for m in meals} == {"lunch", "dinner"}, "Pranzo e Cena (ASM-063)"
    courses = owner.rows(
        "select base_code, name from app.course where family_id = %s", (family_id,)
    )
    assert {c[0] for c in courses} == BASE_COURSES
    assert len(courses) == 8
    assert all(c[1] is None for c in courses), (
        "le portate base non hanno nome (si traduce nel client)"
    )

    boot = owner.rows(
        "select email_sha256, created_at, expires_at, redeemed_at, redeemed_person_id "
        "from app.family_bootstrap where family_id = %s",
        (family_id,),
    )
    assert len(boot) == 1
    digest, created, expires, redeemed_at, redeemed_person = boot[0]
    assert bytes(digest) == email_sha256(CANARY_EMAIL)
    assert expires - created == timedelta(days=7), "SR-033: scadenza a 7 giorni"
    assert (redeemed_at, redeemed_person) == (None, None)
    assert owner.scalar("select count(*) from app.person") == 0, (
        "nessuna persona: l'Amministratore nasce al primo login (SL-03a)"
    )


def test_bootstrap_frozen_through_is_local_today_minus_one_just_before_midnight(
    owner: Owner, connect_app: Connect, frozen_now: FrozenNow
) -> None:
    frozen_now(datetime(2026, 10, 22, 21, 59, 59, tzinfo=UTC))  # 23:59:59 del 22 a Roma
    family_id = _bootstrap(connect_app)
    assert owner.scalar("select frozen_through from app.family where id = %s", (family_id,)) == (
        date(2026, 10, 21)
    )


def test_ac_002_1_bootstrap_writes_a_console_event_in_the_security_log(
    owner: Owner, connect_app: Connect
) -> None:
    """SR-020, SR-040: ogni comando scrive un evento; SR-057."""
    corr = uuid4()
    with connect_app("menu_console", autocommit=False) as conn:
        conn.execute("select set_config('app.correlation_id', %s, true)", (str(corr),))
        row = conn.execute(
            "select app.console_bootstrap_family(%s, %s)", ("Famiglia Alfa", bytes(32))
        ).fetchone()
        conn.commit()
    assert row is not None
    events = _events(owner)
    assert len(events) == 1
    event_type, outcome, actor_kind, family_id, correlation_id, details, account = events[0]
    assert (event_type, outcome, actor_kind) == (
        "console.family_bootstrap",
        "success",
        "platform_operator",
    )
    assert family_id == row[0]
    assert correlation_id == corr, "la funzione legge app.correlation_id (ADR-0011)"
    assert account is None
    assert "@" not in str(details)
    assert bytes(32).hex() not in str(details), "mai l'hash dell'email nell'evento (I-01)"


def test_ac_002_3_bootstrap_returns_only_the_family_id(connect_app: Connect) -> None:
    with connect_app("menu_console") as conn:
        cols = conn.execute(
            "select * from app.console_bootstrap_family(%s, %s)", ("Famiglia Alfa", bytes(32))
        ).fetchall()
    assert len(cols) == 1
    assert len(cols[0]) == 1
    assert isinstance(cols[0][0], UUID)


def test_bootstrap_accepts_a_sixty_character_name(owner: Owner, connect_app: Connect) -> None:
    family_id = _bootstrap(connect_app, name="N" * 60)
    assert owner.scalar("select name from app.family where id = %s", (family_id,)) == "N" * 60


# --- console_bootstrap_family: errori (AC-002.2) ----


CANARY_NAME = "CANARY-FAMILY-NAME-" + "x" * 50  # 68 caratteri: troppo lungo


def _leaks(message: str, *values: str | bytes | None) -> list[str]:
    """Valori ricevuti (non banali) che compaiono nel messaggio d'errore."""
    found = []
    for value in values:
        text = value.hex() if isinstance(value, bytes) else value
        if text and len(text) >= 3 and text in message:
            found.append(text)
    return found


@pytest.mark.parametrize(
    ("name", "digest"),
    [
        pytest.param("Famiglia Alfa", bytes(31), id="hash-31-byte"),
        pytest.param("Famiglia Alfa", bytes(33), id="hash-33-byte"),
        pytest.param("Famiglia Alfa", b"", id="hash-vuoto"),
        pytest.param("Famiglia Alfa", None, id="hash-null"),
        pytest.param("", bytes(32), id="nome-vuoto"),
        pytest.param("   ", bytes(32), id="nome-solo-spazi"),
        pytest.param("N" * 61, bytes(32), id="nome-61-caratteri"),
        pytest.param(CANARY_NAME, bytes(32), id="nome-canarino-troppo-lungo"),
        pytest.param(None, bytes(32), id="nome-null"),
    ],
)
def test_ac_002_2_invalid_arguments_are_refused_and_create_nothing(
    owner: Owner, connect_app: Connect, name: str | None, digest: bytes | None
) -> None:
    """SQLSTATE 22023 e messaggio che non ripete i valori ricevuti (ADR-0011: i log dei job
    conservano l'output); nessuna riga, nemmeno l'evento."""
    before = _counts(owner)
    with (
        connect_app("menu_console") as conn,
        pytest.raises(psycopg.errors.InvalidParameterValue) as raised,
    ):
        conn.execute("select app.console_bootstrap_family(%s, %s)", (name, digest))
    assert _leaks(str(raised.value), name, digest) == []
    assert _counts(owner) == before
    assert _events(owner) == []


def test_a_second_bootstrap_for_the_same_hash_creates_a_separate_family(
    owner: Owner, connect_app: Connect
) -> None:
    """Nessun vincolo di unicità sull'hash (05-data §4.2: UQ solo su family_id): due
    bootstrap per la stessa email sono due famiglie. Il riscatto (SL-03a) sceglie il primo."""
    a, b = _bootstrap(connect_app), _bootstrap(connect_app)
    assert a != b
    assert owner.scalar("select count(*) from app.family_bootstrap") == 2


# --- nessuna email in chiaro (THR-053, SR-021, ADR-0011) ----


def test_no_plaintext_email_or_local_part_in_any_row_after_the_console_commands(
    owner: Owner, connect_app: Connect
) -> None:
    """Dopo bootstrap, nota di audit e lettura del registro nessuna tabella di `app` contiene
    l'email (né la sua parte locale) in nessuna colonna, JSON compresi."""
    _bootstrap(connect_app)
    with connect_app("menu_console") as conn:
        conn.execute("select app.console_audit_note(%s)", (GOOD_REF,))
        conn.execute(
            "select * from app.console_security_events(%s, 100)",
            (datetime(2000, 1, 1, tzinfo=UTC),),
        )
    tables = [
        r[0]
        for r in owner.rows(
            "select tablename from pg_tables "
            "where schemaname = 'app' and tablename <> 'alembic_version'"
        )
    ]
    assert {"family", "family_bootstrap", "security_event"} <= set(tables)
    needles = ["canary-console", "example.test", CANARY_EMAIL.lower()]
    for table in tables:
        dump = owner.scalar(
            f"select coalesce(jsonb_agg(to_jsonb(t))::text, '') from app.{table} t"  # noqa: S608
        ).lower()
        for needle in needles:
            assert needle not in dump, f"{needle!r} compare in app.{table}"


# --- console_audit_note ----


def test_audit_note_records_a_direct_access_event(owner: Owner, connect_app: Connect) -> None:
    """ASM-045: accesso diretto al database annotato; evento `console.audit_note`."""
    with connect_app("menu_console") as conn:
        row = conn.execute("select app.console_audit_note(%s)", (GOOD_REF,)).fetchone()
    assert row is not None
    events = _events(owner, "console.audit_note")
    assert len(events) == 1
    _, outcome, actor_kind, family_id, _, details, account = events[0]
    assert (outcome, actor_kind, family_id, account) == ("success", "platform_operator", None, None)
    assert "@" not in str(details)


@pytest.mark.parametrize(
    "ref",
    ["", "x", "aud-20261022-1", "AUD-2026102-1", "A-20261022-1", "ABCDEF-20261022-1",
     "AUD-20261022-1234", "AUD-20261022-", "AUD-20261022-1 ", "mario.rossi@example.test", None],
)  # fmt: skip
def test_audit_note_rejects_a_malformed_request_ref(
    owner: Owner, connect_app: Connect, ref: str | None
) -> None:
    """ADR-0011: `request_ref` ^[A-Z]{2,5}-[0-9]{8}-[0-9]{1,3}$, validato anche dalla funzione.
    L'errore c'è davvero (22023), non ripete il valore e non lascia nessun evento."""
    with (
        connect_app("menu_console") as conn,
        pytest.raises(psycopg.errors.InvalidParameterValue) as raised,
    ):
        conn.execute("select app.console_audit_note(%s)", (ref,))
    assert _leaks(str(raised.value), ref) == []
    assert _events(owner) == []


# --- console_security_events ----


def _insert_event(owner: Owner, event_type: str, when: datetime, ip: str | None = None) -> None:
    owner.execute(
        "insert into app.security_event (occurred_at, event_type, outcome, actor_kind, ip) "
        "values (%s, %s, 'success', 'system', %s)",
        (when, event_type, ip),
    )


T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _read(connect_app: Connect, since: datetime, limit: int, columns: str = "e.event_type") -> list:  # type: ignore[type-arg]
    with connect_app("menu_console") as conn:
        return conn.execute(
            f"select {columns} from app.console_security_events(%s, %s) e",  # noqa: S608
            (since, limit),
        ).fetchall()


def test_security_events_returns_events_since_the_instant_in_order(
    owner: Owner, connect_app: Connect
) -> None:
    """Ordine (occurred_at, id) senza riordinare il risultato: inseriti fuori ordine, con un
    pareggio di istante risolto dall'id. L'evento del comando non è nel proprio output."""
    _insert_event(owner, "x.late", T0 + timedelta(minutes=2))
    _insert_event(owner, "x.early", T0)
    _insert_event(owner, "x.tie_first", T0 + timedelta(minutes=1))
    _insert_event(owner, "x.tie_second", T0 + timedelta(minutes=1))
    _insert_event(owner, "x.before", T0 - timedelta(seconds=1))
    rows = _read(connect_app, T0, 100)
    assert [r[0] for r in rows] == ["x.early", "x.tie_first", "x.tie_second", "x.late"]


def test_security_events_since_is_inclusive(owner: Owner, connect_app: Connect) -> None:
    _insert_event(owner, "x.exact", T0)
    _insert_event(owner, "x.older", T0 - timedelta(microseconds=1))
    assert [r[0] for r in _read(connect_app, T0, 100)] == ["x.exact"]


def test_security_events_respects_the_limit_and_keeps_the_oldest_first(
    owner: Owner, connect_app: Connect
) -> None:
    for i in range(5):
        _insert_event(owner, f"x.event{i}", T0 + timedelta(minutes=i))
    assert [r[0] for r in _read(connect_app, T0, 2)] == ["x.event0", "x.event1"]


@pytest.mark.parametrize("limit", [1, 1000])
def test_security_events_accepts_the_limit_boundaries(
    owner: Owner, connect_app: Connect, limit: int
) -> None:
    _insert_event(owner, "x.one", T0)
    assert [r[0] for r in _read(connect_app, T0, limit)] == ["x.one"]


@pytest.mark.parametrize(
    ("since", "limit"),
    [
        pytest.param(None, 10, id="since-null"),
        pytest.param(T0, 0, id="limit-0"),
        pytest.param(T0, -1, id="limit-negativo"),
        pytest.param(T0, 1001, id="limit-1001"),
        pytest.param(T0, 100000, id="limit-100000"),
        pytest.param(T0, None, id="limit-null"),
    ],
)
def test_security_events_rejects_invalid_arguments_with_22023_and_no_event(
    owner: Owner, connect_app: Connect, since: datetime | None, limit: int | None
) -> None:
    """Un argomento non valido solleva `invalid_parameter_value`, non ripete il valore ricevuto
    e non lascia nemmeno l'evento `console.security_log` (0004)."""
    _insert_event(owner, "x.one", T0)
    with (
        connect_app("menu_console") as conn,
        pytest.raises(psycopg.errors.InvalidParameterValue) as raised,
    ):
        conn.execute("select * from app.console_security_events(%s, %s)", (since, limit))
    assert raised.value.sqlstate == "22023"
    message = str(raised.value)
    assert _leaks(message, str(limit), "" if since is None else since.isoformat()) == []
    assert "2026" not in message
    assert _events(owner) == []


def test_security_events_writes_its_own_event_after_reading_with_the_arguments(
    owner: Owner, connect_app: Connect
) -> None:
    """SR-040: un evento `console.security_log`, scritto dopo la lettura: non è nell'output e
    i suoi `details` sono esattamente `since` e `limit`."""
    _insert_event(owner, "x.one", T0)
    rows = _read(connect_app, T0, 7)
    assert [r[0] for r in rows] == ["x.one"]
    events = _events(owner, "console.security_log")
    assert len(events) == 1
    _, outcome, actor_kind, family_id, _, details, account = events[0]
    assert (outcome, actor_kind, family_id, account) == ("success", "platform_operator", None, None)
    assert set(details) == {"since", "limit"}
    assert details["limit"] == 7
    assert datetime.fromisoformat(details["since"]) == T0
    # una seconda lettura vede il primo evento, e solo quello (non il proprio)
    again = _read(connect_app, T0, 100)
    assert [r[0] for r in again] == ["x.one", "console.security_log"]
    assert len(_events(owner, "console.security_log")) == 2


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        pytest.param("203.0.113.77", "203.0.113.0", id="v4-a-/24"),
        pytest.param("203.0.113.0", "203.0.113.0", id="v4-gia-di-rete"),
        pytest.param("2001:db8:1234:5678::1", "2001:db8:1234::", id="v6-a-/48"),
        pytest.param("2001:db8:1234:ffff:ffff:ffff:ffff:ffff", "2001:db8:1234::", id="v6-pieno"),
        pytest.param(None, None, id="senza-ip"),
    ],
)
def test_security_events_truncates_the_ip(
    owner: Owner, connect_app: Connect, ip: str | None, expected: str | None
) -> None:
    """ADR-0011 ("security-log restituisce gli IP troncati"), SR-051: /24 per IPv4, /48 per
    IPv6; mai l'indirizzo completo, mai NULL se l'evento ha un IP."""
    _insert_event(owner, "login.failure", T0, ip=ip)
    rows = _read(connect_app, T0, 100, "host(e.ip), e.ip::text")
    assert len(rows) == 1
    host, full = rows[0]
    assert host == expected
    if ip is not None and expected != ip:
        assert ip not in full


def test_security_events_returns_the_columns_of_the_contract(
    owner: Owner, connect_app: Connect
) -> None:
    corr, family = uuid4(), uuid4()
    owner.execute(
        "insert into app.security_event (occurred_at, event_type, outcome, actor_kind, "
        "family_id, target_type, target_id, correlation_id, details) "
        "values (%s, 'x.full', 'denied', 'account', %s, 'thing', %s, %s, '{\"k\": 1}')",
        (T0, family, family, corr),
    )
    rows = _read(
        connect_app,
        T0,
        10,
        "e.outcome, e.actor_kind, e.family_id, e.target_type, e.target_id, e.correlation_id, "
        "e.details",
    )
    assert rows == [("denied", "account", family, "thing", family, corr, {"k": 1})]


def test_every_console_command_writes_one_platform_operator_event(
    owner: Owner, connect_app: Connect
) -> None:
    """SR-040 ("ogni comando eseguito scrive un evento"), 05-data §3.3."""
    with connect_app("menu_console") as conn:
        conn.execute(
            "select * from app.console_security_events(%s, 10)", (datetime(2000, 1, 1, tzinfo=UTC),)
        )
    ops = [e for e in _events(owner) if e[2] == "platform_operator"]
    assert len(ops) == 1, ops
    with connect_app("menu_console") as conn:
        conn.execute("select app.console_audit_note(%s)", (GOOD_REF,))
    assert len([e for e in _events(owner) if e[2] == "platform_operator"]) == 2


# --- privilegi: chi può chiamare (SR-040, THR-044, THR-051) ----


@pytest.mark.parametrize(
    "call",
    [
        "select app.console_bootstrap_family('Famiglia Alfa', decode(repeat('00', 32), 'hex'))",
        "select app.console_audit_note('AUD-20261022-1')",
        "select * from app.console_security_events('2000-01-01T00:00:00Z', 10)",
    ],
)
@pytest.mark.parametrize("role", ["menu_app", "menu_backup"])
def test_other_roles_cannot_call_the_console_functions(
    owner: Owner, connect_app: Connect, role: str, call: str
) -> None:
    before = _counts(owner)
    with connect_app(role) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(call.encode())
    assert _counts(owner) == before


# --- correlation_id dal job (console_tx, ADR-0011) ----


@pytest.fixture
def console_engine(worker_db: str) -> Iterator[None]:
    tenancy.init(pg.cluster().role_url("menu_console", worker_db, sqlalchemy=True))
    try:
        yield
    finally:
        tenancy.dispose()


CALLS = ("bootstrap", "audit-note", "security-log")


def _call(tx: Any, command: str) -> None:
    """Esegue la funzione console con SQL letterale (la regola semgrep ammette solo letterali)."""
    if command == "bootstrap":
        tx.exec_driver_sql(
            "select app.console_bootstrap_family('Famiglia Alfa', decode(repeat('00', 32), 'hex'))"
        ).fetchall()
    elif command == "audit-note":
        tx.exec_driver_sql("select app.console_audit_note('AUD-20261022-1')").fetchall()
    else:
        tx.exec_driver_sql(
            "select * from app.console_security_events('2000-01-01T00:00:00Z', 10)"
        ).fetchall()


@pytest.mark.parametrize("command", CALLS)
def test_console_tx_correlation_id_ends_up_on_the_event(
    owner: Owner, console_engine: None, command: str
) -> None:
    """ADR-0011: `console_tx` imposta `app.correlation_id` locale; ogni funzione lo copia
    nell'evento. Se `console_tx` smette di impostarlo, questo test fallisce."""
    corr = uuid4()
    with tenancy.console_tx(corr) as tx:
        _call(tx, command)
    events = _events(owner)
    assert len(events) == 1
    assert events[0][4] == corr


@pytest.mark.parametrize("command", CALLS)
def test_correlation_id_does_not_leak_to_the_next_transaction(
    owner: Owner, console_engine: None, command: str
) -> None:
    """`set_config(..., true)` è locale: la transazione successiva sulla stessa connessione
    scrive l'evento senza correlation_id."""
    with tenancy.console_tx(uuid4()) as tx:
        tx.exec_driver_sql("select 1")
    with tenancy.system_tx() as tx:  # stesso engine, nessun app.correlation_id
        _call(tx, command)
    events = _events(owner)
    assert len(events) == 1
    assert events[0][4] is None
