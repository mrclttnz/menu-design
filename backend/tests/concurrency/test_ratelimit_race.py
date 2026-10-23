"""Concorrenza sui contatori e sul massimo di sessioni (SL-03b; 08 §9, ADR-0006, THR-013).

Invarianti (non si asserisce quale richiesta vince, solo i conteggi):
- N richieste parallele sullo stesso limite: passano ESATTAMENTE `limite`, le altre sono 429
  (l'incremento è un solo upsert atomico: niente «controlla e poi scrivi»);
- login paralleli sullo stesso account: mai più di 20 sessioni (e 20 se ce n'erano abbastanza).
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from support.accounts import AlfaWorld, sessions
from support.browser_sim import Browser
from support.fake_oidc import FakeOidc
from support.owner import Owner
from support.ratelimit import insert_session

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]

Factory = Callable[..., TestClient]
T0 = datetime(2026, 10, 23, 12, 7, 30, tzinfo=UTC)
START_LIMIT = 30
PARALLEL = 60
ORIGIN = "https://testserver"


def _raw_start(client: TestClient, csrf: str, barrier: threading.Barrier) -> int:
    """Una `POST start` anonima, con intestazioni esplicite (senza il vasetto di cookie)."""
    barrier.wait(timeout=15)
    response = client.post(
        "/api/v1/auth/google/start",
        content=b'{"purpose":"login"}',
        headers={
            "content-type": "application/json",
            "origin": ORIGIN,
            "sec-fetch-site": "same-origin",
            "cookie": f"__Host-csrf={csrf}",
            "x-csrf-token": csrf,
        },
    )
    status: int = response.status_code
    return status


def test_60_parallel_starts_let_exactly_30_through(
    app_factory: Factory, frozen_now: Callable[[datetime], None]
) -> None:
    frozen_now(T0)
    client = app_factory()
    csrf = Browser(client).anonymous_csrf()
    barrier = threading.Barrier(PARALLEL)
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futures = [pool.submit(_raw_start, client, csrf, barrier) for _ in range(PARALLEL)]
        statuses = [f.result(timeout=60) for f in futures]
    assert statuses.count(200) == START_LIMIT, statuses
    assert statuses.count(429) == PARALLEL - START_LIMIT, statuses


def test_parallel_logins_never_leave_more_than_20_sessions(
    app_factory: Factory, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    client = app_factory()
    for _ in range(15):
        insert_session(owner, alfa.admin_account, used_days_ago=3)
    contenders = []
    for _ in range(8):
        browser = Browser(client)
        started = browser.start_login()
        assert started.status_code == 200
        grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
        contenders.append((browser, grant.callback_path))
    barrier = threading.Barrier(len(contenders))

    def go(item: tuple[Browser, str]) -> Response:
        barrier.wait(timeout=15)
        return item[0].get(item[1])

    with ThreadPoolExecutor(max_workers=len(contenders)) as pool:
        responses = list(pool.map(go, contenders))
    assert [r.status_code for r in responses] == [302] * len(contenders)
    assert len(sessions(owner, alfa.admin_account)) == 20, "15 + 8 accessi = 23: il tetto è 20"
