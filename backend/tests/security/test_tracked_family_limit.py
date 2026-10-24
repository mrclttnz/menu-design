"""Tetto di 5.000 scritture tracciate al giorno per famiglia (SL-05; SR-070, AC-049.5).

AC-049.5 (CHG-010): «Dato una famiglia con 5.000 scritture tracciate nella giornata, quando
arriva un'altra scrittura, allora riceve `429` e il Gestore riceve un allarme.» THR-046 e THR-100
(esaurimento della quota di 500 MB), SR-058 (allarme: evento `rate_limit.exceeded`), 05-data §9
(contatore `rate_counter` con chiave HMAC(`tracked_family`, `family_id`), finestra = giorno
LOCALE nel fuso della famiglia, non il giorno UTC: CR-SL03b su `tracked_family`), 08 §7.4.

Per non inviare 5.000 richieste, l'helper `owner` porta il contatore a `limite - 1` (08 §7.4): la
richiesta successiva è la 5.000ª e riesce, quella dopo (la 5.001ª) dà `429`. Il contatore si
conta per FAMIGLIA, sommando tutte le persone; le letture e le scritture senza `tracks` non lo
consumano. Gli orologi sono quello del database (`frozen_now`), mai quello del processo.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import Response

from support.accounts import security_events
from support.dishes import Actor, Who, World, event_rows, make_dish, payload
from support.owner import Owner
from support.ratelimit import rate_counter_text
from support.tracks import (
    DAILY_LIMIT,
    local_day_start_utc,
    next_local_midnight_utc,
    seed_tracked,
    set_timezone,
    tracked_count,
)

pytestmark = [pytest.mark.sec, pytest.mark.integration]
Login = Callable[[Who], Actor]
Clock = Callable[[datetime], None]

ROME = "Europe/Rome"
LOS_ANGELES = "America/Los_Angeles"
T0 = datetime(2026, 10, 23, 12, 7, 30, tzinfo=UTC)  # 14:07:30 a Roma, stesso giorno locale
T_NIGHT = datetime(2026, 10, 23, 3, 0, 0, tzinfo=UTC)  # 05:00 a Roma, 20:00 del 22 a Los Angeles


@pytest.fixture
def clock(frozen_now: Clock) -> Clock:
    frozen_now(T0)
    return frozen_now


def flip(actor: Actor, dish: Any, version: int, status: str = "tested") -> Response:
    return actor.post(f"/api/v1/dishes/{dish}/status", {"status": status}, if_match=version)


def assert_daily_429(response: Response) -> int:
    """Contratto del `429` (ADR-0006, SR-004): `problem+json` generico e `Retry-After`."""
    assert response.status_code == 429, (response.status_code, response.text)
    assert response.headers["content-type"].startswith("application/problem+json")
    retry = int(response.headers["retry-after"])
    assert retry >= 1
    body = response.json()
    assert body["code"] == "rate_limited"
    assert body["status"] == 429
    assert body["params"]["retryAfterSeconds"] == retry
    assert set(body) <= {"type", "title", "status", "code", "params"}
    return retry


def at_the_limit(
    owner: Owner, world: World, *, timezone: str = ROME, at: datetime = T0, count: int = DAILY_LIMIT
) -> None:
    set_timezone(owner, world.alfa, timezone)
    seed_tracked(owner, world.alfa.id, count, local_day_start_utc(at, timezone))


# --- il limite: 5.000 passano, la 5.001ª no (AC-049.5) -------------------------------------------


def test_ac_049_5_the_5000th_tracked_write_succeeds_and_the_5001st_gets_429(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    at_the_limit(owner, world, count=DAILY_LIMIT - 1)
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    last_allowed = flip(planner, dish, 1)
    assert last_allowed.status_code == 200, last_allowed.text
    assert tracked_count(owner, world.alfa.id) == DAILY_LIMIT
    assert len(event_rows(owner)) == 1

    refused = flip(planner, dish, 2, "to_try")
    assert_daily_429(refused)
    detail = planner.get(f"/api/v1/dishes/{dish}").json()
    assert (detail["status"], detail["version"]) == ("tested", 2), "il 429 non esegue la scrittura"
    assert len(event_rows(owner)) == 1, "e non scrive nessun evento"


def test_the_429_is_logged_once_for_the_manager_without_personal_data(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    """SR-058: l'allarme è l'evento `rate_limit.exceeded`, una sola volta per finestra."""
    at_the_limit(owner, world)
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "CANARY-ALFA-DISH-1")
    assert not security_events(owner, "rate_limit.%")
    for version in (1, 1, 1):
        assert_daily_429(flip(planner, dish, version))
    events = security_events(owner, "rate_limit.%")
    assert [e["event_type"] for e in events] == ["rate_limit.exceeded"], "una sola volta"
    (event,) = events
    assert event["outcome"] == "denied"
    assert event["actor_kind"] == "account"
    assert event["actor_account_id"] == world.alfa.who("planner").account
    assert event["actor_role"] == "planner"
    assert event["family_id"] == world.alfa.id
    text = json.dumps(event, default=str)
    for forbidden in (str(dish), "CANARY", world.alfa.who("planner").identity.email, "@"):
        assert forbidden not in text


def test_a_denied_request_never_executes_the_handler_or_writes_the_dish(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    at_the_limit(owner, world)
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    for _ in range(3):
        assert_daily_429(flip(planner, dish, 1))
    assert event_rows(owner) == []
    detail = planner.get(f"/api/v1/dishes/{dish}").json()
    assert (detail["status"], detail["version"]) == ("to_try", 1)


# --- per famiglia, non per persona né per sessione -----------------------------------------------


def test_the_cap_is_shared_by_every_member_of_the_family_and_does_not_touch_others(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    at_the_limit(owner, world)
    planner = login(world.alfa.who("planner"))
    admin = login(world.alfa.who("admin"))
    beta = login(world.beta.who("planner"))
    mine = make_dish(owner, world.alfa, "Pasta e ceci")
    theirs = make_dish(owner, world.beta, "Risotto")
    assert_daily_429(flip(planner, mine, 1))
    assert_daily_429(flip(admin, mine, 1))
    assert flip(beta, theirs, 1).status_code == 200, "un'altra famiglia non è toccata"
    assert tracked_count(owner, world.beta.id) == 1
    assert tracked_count(owner, world.alfa.id) == DAILY_LIMIT


def test_a_second_session_of_the_same_person_shares_the_family_counter(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    at_the_limit(owner, world, count=DAILY_LIMIT - 1)
    first = login(world.alfa.who("planner"))
    second = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert flip(first, dish, 1).status_code == 200
    assert_daily_429(flip(second, dish, 2, "to_try"))


def test_reads_and_untracked_writes_are_not_blocked_nor_counted_at_the_cap(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    """Il tetto conta le scritture che generano un evento (SR-070): le altre non lo consumano."""
    at_the_limit(owner, world)
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert planner.get("/api/v1/dishes").status_code == 200
    assert planner.get(f"/api/v1/dishes/{dish}").status_code == 200
    assert planner.get("/api/v1/courses").status_code == 200
    created = planner.post("/api/v1/dishes", payload(world.alfa, "Nuovo piatto"))
    assert created.status_code == 201, created.text
    updated = planner.put(f"/api/v1/dishes/{dish}", payload(world.alfa, "Rinominato"), if_match=1)
    assert updated.status_code == 200, updated.text
    assert tracked_count(owner, world.alfa.id) == DAILY_LIMIT


def test_the_member_403_does_not_consume_the_family_cap(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    """08 §6.3 (c): il contatore sale solo con il successo. Un Membro (nessun permesso di
    scrittura sul piatto) non può esaurire il tetto della famiglia a forza di `403`."""
    at_the_limit(owner, world, count=10)
    member = login(world.alfa.who("member"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    for _ in range(5):
        assert flip(member, dish, 1).status_code == 403
    assert tracked_count(owner, world.alfa.id) == 10


def test_a_412_does_not_consume_the_family_cap_but_a_success_does(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    at_the_limit(owner, world, count=10)
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert flip(planner, dish, 9).status_code == 412
    assert (
        planner.post(f"/api/v1/dishes/{dish}/status", {"status": "x"}, if_match=1).status_code
        == 422
    )
    assert tracked_count(owner, world.alfa.id) == 10
    assert flip(planner, dish, 1).status_code == 200
    assert tracked_count(owner, world.alfa.id) == 11


# --- la finestra è il giorno LOCALE della famiglia -----------------------------------------------


def test_the_counter_key_is_an_hmac_and_the_table_holds_no_family_id(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert flip(planner, dish, 1).status_code == 200
    assert tracked_count(owner, world.alfa.id) == 1, "chiave HMAC(tracked_family, family_id)"
    assert str(world.alfa.id) not in rate_counter_text(owner)
    assert str(world.alfa.id).replace("-", "") not in rate_counter_text(owner)


def test_the_window_is_the_local_day_of_the_family_and_restarts_at_local_midnight(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    at_the_limit(owner, world)
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    midnight = next_local_midnight_utc(T0, ROME)  # 2026-10-23 22:00 UTC = 00:00 del 24 a Roma
    assert midnight == datetime(2026, 10, 23, 22, 0, tzinfo=UTC)
    assert_daily_429(flip(planner, dish, 1))
    clock(midnight - timedelta(seconds=1))
    assert_daily_429(flip(planner, dish, 1))
    clock(midnight)
    assert flip(planner, dish, 1).status_code == 200, "dopo la mezzanotte locale si riparte"
    assert tracked_count(owner, world.alfa.id) == DAILY_LIMIT + 1, "due finestre, due righe"


def test_retry_after_points_at_the_end_of_the_window_not_beyond(
    world: World, login: Login, clock: Clock, owner: Owner
) -> None:
    at_the_limit(owner, world)
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    retry = assert_daily_429(flip(planner, dish, 1))
    seconds_to_midnight = int((next_local_midnight_utc(T0, ROME) - T0).total_seconds())
    assert 1 <= retry <= seconds_to_midnight, (retry, seconds_to_midnight)


@pytest.mark.parametrize(
    ("timezone", "limited_window_utc", "free_window_utc"),
    [
        # 05:00 a Roma (23 ottobre): il giorno locale inizia 22 ottobre 22:00 UTC
        (ROME, datetime(2026, 10, 22, 22, 0, tzinfo=UTC), datetime(2026, 10, 23, 0, 0, tzinfo=UTC)),
        # 20:00 a Los Angeles (22 ottobre): il giorno locale inizia 22 ottobre 07:00 UTC
        (
            LOS_ANGELES,
            datetime(2026, 10, 22, 7, 0, tzinfo=UTC),
            datetime(2026, 10, 23, 0, 0, tzinfo=UTC),
        ),
    ],
)
def test_two_timezones_at_the_same_instant_use_different_windows_never_the_utc_day(
    timezone: str,
    limited_window_utc: datetime,
    free_window_utc: datetime,
    world: World,
    login: Login,
    frozen_now: Clock,
    owner: Owner,
) -> None:
    """Un contatore pieno nella finestra del giorno locale blocca; uno pieno nella finestra
    del giorno UTC (mezzanotte UTC) non blocca: la mezzanotte UTC non è quella della famiglia."""
    frozen_now(T_NIGHT)
    set_timezone(owner, world.alfa, timezone)
    assert local_day_start_utc(T_NIGHT, timezone) == limited_window_utc
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    seed_tracked(owner, world.alfa.id, DAILY_LIMIT, free_window_utc)
    assert flip(planner, dish, 1).status_code == 200, "il giorno UTC non è la finestra"
    seed_tracked(owner, world.alfa.id, DAILY_LIMIT, limited_window_utc)
    assert_daily_429(flip(planner, dish, 2, "to_try"))


def test_changing_the_family_timezone_moves_the_window_for_the_next_request(
    world: World, login: Login, frozen_now: Clock, owner: Owner
) -> None:
    frozen_now(T_NIGHT)
    at_the_limit(owner, world, timezone=ROME, at=T_NIGHT)
    planner = login(world.alfa.who("planner"))
    dish = make_dish(owner, world.alfa, "Pasta e ceci")
    assert_daily_429(flip(planner, dish, 1))
    set_timezone(owner, world.alfa, LOS_ANGELES)  # a Los Angeles è ancora il 22: finestra nuova
    assert flip(planner, dish, 1).status_code == 200
