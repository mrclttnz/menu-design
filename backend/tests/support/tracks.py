"""Aiuti per le scritture tracciate (SL-05): eventi di modifica e contatore `tracked_family`.

08 §6.3: marker `@pytest.mark.tracks("<operationId>")` e helper `assert_tracks`. Il contatore
`tracked_family` (SR-070, 05-data §9.x) è una riga di `rate_counter` con chiave
HMAC-SHA-256(pepper, `tracked_family` NUL `family_id`) e finestra = il giorno locale della famiglia
(mezzanotte locale in UTC). La chiave si calcola qui in modo INDIPENDENTE dal codice, così il test
vede un'implementazione che usi un altro nome di regola, un altro identificativo o il giorno UTC.
"""

import hashlib
import hmac
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from httpx import Response

from support.dishes import Fam, event_rows, family_state_hash
from support.owner import Owner
from support.ratelimit import PEPPER_A

RULE = "tracked_family"
DAILY_LIMIT = 5000


def tracked_key(family: UUID, pepper: str = PEPPER_A) -> bytes:
    return hmac.new(pepper.encode(), f"{RULE}\x00{family}".encode(), hashlib.sha256).digest()


def tracked_count(owner: Owner, family: UUID, pepper: str = PEPPER_A) -> int:
    """Somma dei conteggi della famiglia su tutte le finestre (indipendente dal calcolo di esse)."""
    return int(
        owner.scalar(
            "select coalesce(sum(count), 0) from app.rate_counter where key = %s",
            (tracked_key(family, pepper),),
        )
    )


def local_day_start_utc(instant: datetime, timezone: str) -> datetime:
    """Mezzanotte locale del giorno che contiene `instant`, espressa in UTC."""
    zone = ZoneInfo(timezone)
    local_day: date = instant.astimezone(zone).date()
    return datetime.combine(local_day, time(0), tzinfo=zone).astimezone(UTC)


def next_local_midnight_utc(instant: datetime, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    local_day = instant.astimezone(zone).date() + timedelta(days=1)
    return datetime.combine(local_day, time(0), tzinfo=zone).astimezone(UTC)


def seed_tracked(
    owner: Owner, family: UUID, count: int, window_start: datetime, pepper: str = PEPPER_A
) -> None:
    """Porta il contatore della famiglia a `count` nella finestra indicata (08 §7.4)."""
    owner.execute(
        "insert into app.rate_counter (key, window_start, count) values (%s, %s, %s) "
        "on conflict (key, window_start) do update set count = excluded.count",
        (tracked_key(family, pepper), window_start, count),
    )


def set_timezone(owner: Owner, fam: Fam, timezone: str) -> None:
    owner.execute("update app.family set timezone = %s where id = %s", (timezone, fam.id))


def assert_tracks(
    *,
    owner: Owner,
    fam: Fam,
    happy: Callable[[], Response],
    expected: Sequence[dict[str, Any]],
    failing: Sequence[tuple[str, Callable[[], Response], int]],
) -> Response:
    """08 §6.3: (b) ogni richiesta fallita lascia zero eventi, nessuna modifica e il contatore
    `tracked_family` com'era; (a) il successo scrive ESATTAMENTE gli eventi attesi; (c) e il
    contatore sale di uno solo (SR-070).

    `expected`: un dizionario di colonne attese per evento (sottoinsieme delle colonne di
    `change_event`), nell'ordine di scrittura.
    """
    base_events = len(event_rows(owner))
    base_count = tracked_count(owner, fam.id)
    for label, send, status in failing:
        state = family_state_hash(owner, fam)
        response = send()
        assert response.status_code == status, (label, response.status_code, response.text)
        assert len(event_rows(owner)) == base_events, f"{label}: evento scritto (AC-049.4)"
        assert family_state_hash(owner, fam) == state, f"{label}: stato modificato"
        assert tracked_count(owner, fam.id) == base_count, (
            f"{label}: ha consumato il tetto (SR-070)"
        )
    response = happy()
    assert response.status_code == 200, (response.status_code, response.text)
    events = event_rows(owner)[base_events:]
    assert len(events) == len(expected), events
    for event, want in zip(events, expected, strict=True):
        for column, value in want.items():
            assert event[column] == value, (column, event[column], value)
    assert tracked_count(owner, fam.id) == base_count + 1, "il successo incrementa di uno (SR-070)"
    return response
