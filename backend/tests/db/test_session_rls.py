"""RLS per account su `session` e risolutori `session_resolve` / `bootstrap_resolve` (SL-03a).

05-data §6.1-6.2, §6.4 («`session`: senza `app.account_id` zero sessioni valide; con l'account A
non legge né revoca le sessioni di B (AC-047.3); `session_resolve` non restituisce sessioni
scadute»). AC-001.2/001.3 (30 giorni di inattività, 90 dalla creazione), AC-002.1/002.4 (bootstrap
valido 7 giorni), SR-005, SR-037, SR-042, SR-033, THR-003, THR-044.

L'orologio del database è spostato con `frozen_now` (08 §4.4): i confini sono esatti, non
dipendono da quando gira il test.
"""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from menu.common import email_sha256
from support.accounts import make_account, make_family
from support.owner import Owner

Connect = Callable[..., psycopg.Connection]
NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)
RESOLVE = (
    "select session_id, account_id, created_at, last_used_at, auth_time, csrf_token_hash "
    "from app.session_resolve(%s)"
)


def _token_hash(label: str) -> bytes:
    return hashlib.sha256(label.encode()).digest()


def _session(
    owner: Owner,
    account: UUID,
    *,
    created: datetime = NOW - timedelta(days=1),
    used: datetime | None = None,
    label: str | None = None,
) -> tuple[UUID, bytes]:
    session, digest = uuid4(), _token_hash(label or str(uuid4()))
    owner.execute(
        "insert into app.session (id, account_id, token_hash, csrf_token_hash, created_at, "
        "last_used_at, auth_time) values (%s, %s, %s, %s, %s, %s, %s)",
        (
            session,
            account,
            digest,
            _token_hash("csrf" + str(session)),
            created,
            used or created,
            created,
        ),
    )
    return session, digest


def _in_account(conn: psycopg.Connection, account: UUID | None) -> None:
    if account is not None:
        conn.execute("select set_config('app.account_id', %s, true)", (str(account),))


# --- RLS per account ---------------------------------------------------------------------------


def test_without_account_context_menu_app_sees_no_valid_session(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    frozen_now(NOW)
    _session(owner, make_account(owner))
    with connect_app(autocommit=False) as conn:
        assert conn.execute("select count(*) from app.session").fetchone() == (0,)


def test_an_account_sees_and_revokes_only_its_own_sessions(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    """AC-047.3 (SR-038): l'elenco e la revoca sono per account; il rifiuto è silenzioso (0."""
    frozen_now(NOW)
    alice, bruno = make_account(owner), make_account(owner)
    mine, _ = _session(owner, alice)
    theirs, _ = _session(owner, bruno)
    with connect_app(autocommit=False) as conn:
        _in_account(conn, alice)
        assert {r[0] for r in conn.execute("select id from app.session").fetchall()} == {mine}
        assert conn.execute("delete from app.session where id = %s", (theirs,)).rowcount == 0
        assert (
            conn.execute(
                "update app.session set device_label = 'x' where id = %s", (theirs,)
            ).rowcount
            == 0
        )
        assert conn.execute("delete from app.session where id = %s", (mine,)).rowcount == 1
        conn.commit()
    assert owner.scalar("select count(*) from app.session where id = %s", (theirs,)) == 1


def test_an_account_cannot_insert_a_session_for_another_account(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    """WITH CHECK: nessuna sessione a nome di un altro account (SR-005, SR-037)."""
    frozen_now(NOW)
    alice, bruno = make_account(owner), make_account(owner)
    with connect_app(autocommit=False) as conn:
        _in_account(conn, alice)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "insert into app.session (account_id, token_hash, csrf_token_hash, auth_time) "
                "values (%s, %s, %s, %s)",
                (bruno, _token_hash("a"), _token_hash("b"), NOW),
            )


def test_an_account_can_create_its_own_session_with_the_account_context(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    """05-data §6.1: la creazione al login avviene con `app.account_id` già impostato."""
    frozen_now(NOW)
    alice = make_account(owner)
    with connect_app(autocommit=False) as conn:
        _in_account(conn, alice)
        conn.execute(
            "insert into app.session (account_id, token_hash, csrf_token_hash, auth_time) "
            "values (%s, %s, %s, %s)",
            (alice, _token_hash("a"), _token_hash("b"), NOW),
        )
        conn.commit()
    assert owner.scalar("select count(*) from app.session where account_id = %s", (alice,)) == 1


@pytest.mark.parametrize(
    ("created_days", "used_days", "label"),
    [
        (10, 31, "31 giorni di inattività (AC-001.3)"),
        (91, 0, "91 giorni dalla creazione (AC-001.3)"),
    ],
)
def test_expired_sessions_are_visible_and_deletable_for_cleanup_without_context(
    owner: Owner,
    connect_app: Connect,
    frozen_now: Callable[[datetime], None],
    created_days: int,
    used_days: int,
    label: str,
) -> None:
    """`p_session_expired` (SELECT e DELETE): la pulizia del worker non ha un account (§6.1)."""
    frozen_now(NOW)
    account = make_account(owner)
    expired, _ = _session(
        owner,
        account,
        created=NOW - timedelta(days=created_days),
        used=NOW - timedelta(days=used_days),
    )
    valid, _ = _session(owner, account)
    with connect_app(autocommit=False) as conn:
        assert {r[0] for r in conn.execute("select id from app.session").fetchall()} == {expired}, (
            label
        )
        assert (
            conn.execute("delete from app.session where id = any(%s)", ([expired, valid],)).rowcount
            == 1
        )
        conn.commit()
    assert owner.scalar("select count(*) from app.session where id = %s", (valid,)) == 1


@pytest.mark.parametrize(
    ("created_days", "used_days"),
    [(10, 31), (91, 0)],
)
def test_with_account_context_other_accounts_expired_sessions_are_invisible_and_undeletable(
    owner: Owner,
    connect_app: Connect,
    frozen_now: Callable[[datetime], None],
    created_days: int,
    used_days: int,
) -> None:
    """SEC-SL03a-001: le policy di pulizia valgono solo senza contesto (05-data §6.1).

    Con il contesto di A, la sessione scaduta di B (account_id, device_label, ip_prefix) non si
    legge né si cancella; senza contesto la pulizia del worker la cancella ancora.
    """
    frozen_now(NOW)
    alice, bruno = make_account(owner), make_account(owner)
    theirs, _ = _session(
        owner,
        bruno,
        created=NOW - timedelta(days=created_days),
        used=NOW - timedelta(days=used_days),
    )
    owner.execute(
        "update app.session set device_label = 'Chrome · Android', ip_prefix = '203.0.113.0/24' "
        "where id = %s",
        (theirs,),
    )
    mine_expired, _ = _session(
        owner, alice, created=NOW - timedelta(days=45), used=NOW - timedelta(days=40)
    )
    with connect_app(autocommit=False) as conn:
        _in_account(conn, alice)
        assert {r[0] for r in conn.execute("select id from app.session").fetchall()} == {
            mine_expired
        }
        assert conn.execute(
            "select count(*) from app.session where account_id = %s", (bruno,)
        ).fetchone() == (0,)
        assert conn.execute("delete from app.session where id = %s", (theirs,)).rowcount == 0
        assert conn.execute("delete from app.session where account_id = %s", (bruno,)).rowcount == 0
        conn.commit()
    assert owner.scalar("select count(*) from app.session where id = %s", (theirs,)) == 1
    with connect_app(autocommit=False) as conn:  # pulizia del worker: nessun contesto
        purged = conn.execute(
            "delete from app.session where last_used_at < app.now_utc() - interval '720 hours' "
            "or created_at < app.now_utc() - interval '2160 hours'"
        ).rowcount
        assert purged == 2
        conn.commit()
    assert owner.scalar("select count(*) from app.session where id = %s", (theirs,)) == 0


def test_expired_sessions_cannot_be_updated_without_context(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    """La policy delle righe scadute non dà `UPDATE`: una sessione scaduta non si riesuma."""
    frozen_now(NOW)
    old, _ = _session(
        owner, make_account(owner), used=NOW - timedelta(days=40), created=NOW - timedelta(days=45)
    )
    with connect_app(autocommit=False) as conn:
        assert (
            conn.execute(
                "update app.session set last_used_at = %s where id = %s", (NOW, old)
            ).rowcount
            == 0
        )
        conn.commit()
    assert owner.scalar(
        "select last_used_at from app.session where id = %s", (old,)
    ) == NOW - timedelta(days=40)


# --- session_resolve ---------------------------------------------------------------------------


def _resolve(connect_app: Connect, digest: bytes) -> list[tuple[Any, ...]]:
    with connect_app() as conn:  # nessun contesto: il cookie arriva prima dell'appartenenza
        return conn.execute(RESOLVE.encode(), (digest,)).fetchall()


def test_session_resolve_returns_only_ids_and_timestamps_for_a_valid_token(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    frozen_now(NOW)
    account = make_account(owner)
    session, digest = _session(
        owner, account, created=NOW - timedelta(days=3), used=NOW - timedelta(hours=2)
    )
    rows = _resolve(connect_app, digest)
    assert rows == [
        (
            session,
            account,
            NOW - timedelta(days=3),
            NOW - timedelta(hours=2),
            NOW - timedelta(days=3),
            _token_hash("csrf" + str(session)),
        )
    ]


def test_session_resolve_returns_nothing_for_an_unknown_token(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    frozen_now(NOW)
    _session(owner, make_account(owner))
    assert _resolve(connect_app, _token_hash("sconosciuto")) == []
    assert _resolve(connect_app, b"") == []
    assert _resolve(connect_app, b"\x00" * 31) == []


@pytest.mark.parametrize(
    ("created", "used", "valid"),
    [
        (timedelta(days=5), timedelta(days=29), True),
        (timedelta(days=45), timedelta(days=30), True),  # confine: esattamente 30 giorni
        (timedelta(days=45), timedelta(days=30, seconds=1), False),  # AC-001.3: oltre 30 giorni
        (timedelta(days=45), timedelta(days=31), False),
        (timedelta(days=89), timedelta(hours=1), True),
        (timedelta(days=90), timedelta(hours=1), True),  # confine: esattamente 90 giorni
        (timedelta(days=90, seconds=1), timedelta(hours=1), False),  # AC-001.3: oltre 90 giorni
        (timedelta(days=91), timedelta(seconds=0), False),  # usata ora, ma troppo vecchia
    ],
)
def test_session_resolve_applies_the_30_day_and_90_day_limits_exactly(
    owner: Owner,
    connect_app: Connect,
    frozen_now: Callable[[datetime], None],
    created: timedelta,
    used: timedelta,
    valid: bool,
) -> None:
    """AC-001.2/001.3, SR-037, 05-data §6.4: «`session_resolve` non restituisce sessioni."""
    frozen_now(NOW)
    _, digest = _session(owner, make_account(owner), created=NOW - created, used=NOW - used)
    assert bool(_resolve(connect_app, digest)) is valid


def test_session_resolve_is_executable_by_menu_app_without_any_context(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    """La RLS non ostacola la funzione (SECURITY DEFINER): il chiamante non ha ancora un account."""
    frozen_now(NOW)
    _, digest = _session(owner, make_account(owner))
    with connect_app(autocommit=False) as conn:
        assert conn.execute("select count(*) from app.session").fetchone() == (0,)
        assert conn.execute(RESOLVE.encode(), (digest,)).fetchall() != []


def test_session_resolve_never_returns_another_token_s_row(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    frozen_now(NOW)
    a, b = make_account(owner), make_account(owner)
    sa, ha = _session(owner, a)
    sb, hb = _session(owner, b)
    assert [r[0] for r in _resolve(connect_app, ha)] == [sa]
    assert [r[0] for r in _resolve(connect_app, hb)] == [sb]


# --- bootstrap_resolve -------------------------------------------------------------------------

EMAIL = "canary.gestore@example.test"


def _bootstrap(
    owner: Owner, family: UUID, email: str = EMAIL, *, age: timedelta = timedelta(days=1)
) -> UUID:
    created = NOW - age
    bootstrap = uuid4()
    owner.execute(
        "insert into app.family_bootstrap (id, family_id, email_sha256, created_at, expires_at) "
        "values (%s, %s, %s, %s, %s)",
        (bootstrap, family, email_sha256(email), created, created + timedelta(hours=168)),
    )
    return bootstrap


RESOLVE_BOOT = "select bootstrap_id, family_id from app.bootstrap_resolve(%s)"


def test_bootstrap_resolve_returns_the_ids_for_a_valid_unredeemed_bootstrap(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    frozen_now(NOW)
    family = make_family(owner)
    bootstrap = _bootstrap(owner, family)
    with connect_app() as conn:
        assert conn.execute(RESOLVE_BOOT, (email_sha256(EMAIL),)).fetchall() == [
            (bootstrap, family)
        ]


@pytest.mark.parametrize(
    ("age", "valid"),
    [
        (timedelta(days=6, hours=23), True),
        (timedelta(hours=168), True),  # confine: esattamente 7 giorni
        (timedelta(hours=168, seconds=1), False),  # AC-002.4: oltre 7 giorni
        (timedelta(days=8), False),
    ],
)
def test_bootstrap_resolve_honours_the_seven_day_expiry(
    owner: Owner,
    connect_app: Connect,
    frozen_now: Callable[[datetime], None],
    age: timedelta,
    valid: bool,
) -> None:
    frozen_now(NOW)
    _bootstrap(owner, make_family(owner), age=age)
    with connect_app() as conn:
        assert bool(conn.execute(RESOLVE_BOOT, (email_sha256(EMAIL),)).fetchall()) is valid


def test_bootstrap_resolve_ignores_a_redeemed_bootstrap_and_other_hashes(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    """Monouso e legato all'hash esatto dell'email (THR-003): nessuna normalizzazione in SQL."""
    frozen_now(NOW)
    family = make_family(owner)
    account = make_account(owner)
    from support.accounts import make_person

    person = make_person(owner, family, account, "admin")
    bootstrap = _bootstrap(owner, family)
    with connect_app() as conn:
        assert conn.execute(RESOLVE_BOOT, (email_sha256("altro@example.test"),)).fetchall() == []
        assert (
            conn.execute(RESOLVE_BOOT, (email_sha256(EMAIL.replace(".", "", 1)),)).fetchall() == []
        )
        assert conn.execute(RESOLVE_BOOT, (b"\x00" * 32,)).fetchall() == []
    owner.execute(
        "update app.family_bootstrap set redeemed_at = %s, redeemed_person_id = %s, "
        "email_sha256 = null where id = %s",
        (NOW, person, bootstrap),
    )
    with connect_app() as conn:
        assert conn.execute(RESOLVE_BOOT, (email_sha256(EMAIL),)).fetchall() == []


def test_bootstrap_resolve_exposes_no_email_or_name(
    owner: Owner, connect_app: Connect, frozen_now: Callable[[datetime], None]
) -> None:
    """05-data §6.2: «restituiscono solo ID»; il nome della famiglia non esce prima."""
    frozen_now(NOW)
    _bootstrap(owner, make_family(owner, "CANARY-NOME-FAMIGLIA"))
    with connect_app() as conn:
        cursor = conn.execute(RESOLVE_BOOT, (email_sha256(EMAIL),))
        assert [c.name for c in cursor.description or []] == ["bootstrap_id", "family_id"]
        assert "CANARY" not in str(cursor.fetchall())
