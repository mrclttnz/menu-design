"""SEC-SL00b-003 (THR-106, A-24): con il database lento il controllo non si ripete per richiesta
e i chiamanti non si accodano dietro il lock."""

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, cast

import psycopg
import pytest
from fastapi.testclient import TestClient


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(db_env: None, clock: Clock) -> Iterator[TestClient]:
    from menu.app import create_app

    with TestClient(
        cast(Any, create_app)(health_clock=clock),
        base_url="https://testserver",
        raise_server_exceptions=False,
    ) as c:
        yield c


def _patch_select_1(monkeypatch: pytest.MonkeyPatch, on_probe: Callable[[], None]) -> list[int]:
    probes: list[int] = []
    original = psycopg.Cursor.execute

    def wrapper(self: Any, query: Any, *args: Any, **kwargs: Any) -> Any:
        text = query.decode() if isinstance(query, bytes) else str(query)
        if " ".join(text.lower().replace(";", " ").split()) == "select 1":
            probes.append(1)
            on_probe()
        return original(self, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "execute", wrapper)
    return probes


def test_a_probe_slower_than_the_window_is_still_cached_afterwards(
    client: TestClient, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La finestra parte DOPO il controllo: un probe di 6 s non rende subito stale l'esito."""

    def slow() -> None:
        clock.now += 6.0

    probes = _patch_select_1(monkeypatch, slow)
    assert client.get("/healthz").status_code == 200
    for _ in range(10):
        assert client.get("/healthz").status_code == 200
    assert len(probes) == 1, f"{len(probes)} controlli per 11 richieste"


def test_concurrent_callers_do_not_queue_behind_a_slow_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()
    entered = threading.Event()

    def block() -> None:
        entered.set()
        assert release.wait(timeout=30)

    probes = _patch_select_1(monkeypatch, block)
    first: dict[str, int] = {}
    t = threading.Thread(target=lambda: first.update(code=client.get("/healthz").status_code))
    t.start()
    assert entered.wait(timeout=10), "il primo controllo non è partito"
    started = time.monotonic()
    others = [client.get("/healthz").status_code for _ in range(5)]
    waited = time.monotonic() - started
    release.set()
    t.join(timeout=30)
    assert waited < 3.0, f"i chiamanti hanno aspettato {waited:.1f}s dietro il lock"
    assert set(others) <= {200, 503}
    assert len(probes) == 1
    assert first["code"] == 200
