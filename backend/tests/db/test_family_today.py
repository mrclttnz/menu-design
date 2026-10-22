"""`app.family_today()` con orologio spostato attorno alla mezzanotte locale (05-data §7.1,
§11.1; ADR-0009; 08 §4.4, §8.1 casi fissi). SL-02.

L'orologio è `app.now_utc()` sostituita dall'helper `owner` (`frozen_now`), mai `now()`.
La funzione gira come `menu_app` nel contesto della famiglia (SECURITY INVOKER, RLS attiva).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import psycopg
import pytest

from support.owner import Owner

FrozenNow = Callable[[datetime], None]
Connect = Callable[..., psycopg.Connection]


def _family(owner: Owner, timezone: str = "Europe/Rome") -> UUID:
    family = uuid4()
    owner.execute(
        "insert into app.family (id, name, timezone, frozen_through) values (%s, %s, %s, %s)",
        (family, "Famiglia Orologio", timezone, date(2026, 1, 1)),
    )
    return family


def _today(connect_app: Connect, family: UUID | None) -> date | None:
    with connect_app() as conn:
        conn.autocommit = False
        if family is not None:
            conn.execute("select set_config('app.family_id', %s, true)", (str(family),))
        row = conn.execute("select app.family_today()").fetchone()
    assert row is not None
    value: date | None = row[0]
    return value


def _utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


@pytest.mark.sqlfunc("family_today")
@pytest.mark.parametrize(
    ("timezone", "instant", "expected"),
    [
        # Europe/Rome, ora legale (UTC+2): la mezzanotte locale è alle 22:00 UTC.
        ("Europe/Rome", _utc(2026, 10, 22, 21, 59, 59), date(2026, 10, 22)),
        ("Europe/Rome", _utc(2026, 10, 22, 22, 0, 0), date(2026, 10, 23)),
        # Fine dell'ora legale (domenica 25 ottobre 2026, 01:00 UTC): dopo, UTC+1.
        ("Europe/Rome", _utc(2026, 10, 24, 21, 59, 59), date(2026, 10, 24)),
        ("Europe/Rome", _utc(2026, 10, 24, 22, 0, 0), date(2026, 10, 25)),
        ("Europe/Rome", _utc(2026, 10, 25, 22, 59, 59), date(2026, 10, 25)),
        ("Europe/Rome", _utc(2026, 10, 25, 23, 0, 0), date(2026, 10, 26)),
        # Inizio dell'ora legale (domenica 29 marzo 2026, 01:00 UTC).
        ("Europe/Rome", _utc(2026, 3, 28, 22, 59, 59), date(2026, 3, 28)),
        ("Europe/Rome", _utc(2026, 3, 28, 23, 0, 0), date(2026, 3, 29)),
        ("Europe/Rome", _utc(2026, 3, 29, 21, 59, 59), date(2026, 3, 29)),
        ("Europe/Rome", _utc(2026, 3, 29, 22, 0, 0), date(2026, 3, 30)),
        # Altri fusi: oltreoceano e con mezzora di scarto.
        ("America/New_York", _utc(2026, 10, 23, 3, 59, 59), date(2026, 10, 22)),
        ("America/New_York", _utc(2026, 10, 23, 4, 0, 0), date(2026, 10, 23)),
        ("Asia/Kolkata", _utc(2026, 10, 22, 18, 29, 59), date(2026, 10, 22)),
        ("Asia/Kolkata", _utc(2026, 10, 22, 18, 30, 0), date(2026, 10, 23)),
        ("UTC", _utc(2026, 12, 31, 23, 59, 59), date(2026, 12, 31)),
        ("UTC", _utc(2027, 1, 1, 0, 0, 0), date(2027, 1, 1)),
    ],
)
def test_family_today_follows_the_family_timezone_across_midnight(
    owner: Owner,
    connect_app: Connect,
    frozen_now: FrozenNow,
    timezone: str,
    instant: datetime,
    expected: date,
) -> None:
    family = _family(owner, timezone)
    frozen_now(instant)
    assert _today(connect_app, family) == expected


def test_family_today_changes_when_the_family_timezone_changes(
    owner: Owner, connect_app: Connect, frozen_now: FrozenNow
) -> None:
    """ADR-0009 / AC-003.6: "oggi" si calcola nel fuso corrente della famiglia."""
    family = _family(owner, "Europe/Rome")
    frozen_now(_utc(2026, 10, 22, 22, 30))  # 00:30 del 23 a Roma, 18:30 del 22 a New York
    assert _today(connect_app, family) == date(2026, 10, 23)
    owner.execute("update app.family set timezone = 'America/New_York' where id = %s", (family,))
    assert _today(connect_app, family) == date(2026, 10, 22)


def test_family_today_is_driven_by_now_utc_not_by_the_system_clock(
    owner: Owner, connect_app: Connect, frozen_now: FrozenNow
) -> None:
    """D-T1: nessun `now()` nudo. Con l'orologio fissato nel passato il risultato è quello
    del passato (il calendario reale di oggi sarebbe diverso)."""
    family = _family(owner)
    frozen_now(_utc(2001, 9, 9, 12, 0))
    assert _today(connect_app, family) == date(2001, 9, 9)


def test_family_today_uses_only_the_family_of_the_context(
    owner: Owner, connect_app: Connect, frozen_now: FrozenNow
) -> None:
    """RLS: con il contesto di A il fuso è quello di A, non di B; senza contesto, NULL."""
    rome, tokyo = _family(owner, "Europe/Rome"), _family(owner, "Asia/Tokyo")
    frozen_now(_utc(2026, 10, 22, 16, 0))  # 18:00 a Roma, 01:00 del 23 a Tokyo
    assert _today(connect_app, rome) == date(2026, 10, 22)
    assert _today(connect_app, tokyo) == date(2026, 10, 23)
    assert _today(connect_app, None) is None


def test_family_today_is_null_for_an_unknown_family_context(
    connect_app: Connect, frozen_now: FrozenNow
) -> None:
    frozen_now(_utc(2026, 10, 22, 16, 0))
    assert _today(connect_app, uuid4()) is None
