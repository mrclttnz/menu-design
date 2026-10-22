"""GET /healthz con controllo del database (Q-T2, A-24, THR-106; NFR-005/007).

`SELECT 1` con `menu_app` sul pool esistente, esito in memoria per circa 5 s, `503` con il
database fermo. Contratto assunto: `create_app(..., health_clock=<callable monotono>)` è l'unico
gancio di tempo (come "tempo simulato nella cache", 08 §13 NFR-005).
"""

import time
from collections.abc import Callable, Iterator
from typing import Any, cast

import psycopg
import pytest
from fastapi.testclient import TestClient

from support import pg

BASE_URL = "https://testserver"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def select1_count(monkeypatch: pytest.MonkeyPatch) -> Callable[[], int]:
    """Conta gli `SELECT 1` eseguiti sul driver, qualunque sia il livello che li lancia."""
    seen: list[str] = []
    original = psycopg.Cursor.execute

    def counting(self: Any, query: Any, *args: Any, **kwargs: Any) -> Any:
        text = (
            query
            if isinstance(query, str)
            else getattr(query, "as_string", lambda _c: "")(self.connection)
            if not isinstance(query, bytes)
            else query.decode()
        )
        seen.append(" ".join(str(text).lower().replace(";", " ").split()))
        return original(self, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "execute", counting)
    return lambda: sum(1 for q in seen if q == "select 1")


@pytest.fixture
def connects(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    calls: list[float] = []
    original = psycopg.Connection.connect.__func__  # type: ignore[attr-defined]

    def counting(cls: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(time.monotonic())
        return original(cls, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(counting))
    return calls


@pytest.fixture
def client(db_env: None, clock: FakeClock) -> Iterator[TestClient]:
    from menu.app import create_app

    with TestClient(
        cast(Any, create_app)(health_clock=clock), base_url=BASE_URL, raise_server_exceptions=False
    ) as c:
        yield c


def test_healthz_is_200_ok_when_the_database_answers(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["content-type"].split(";")[0] == "application/json"
    assert "no-store" in resp.headers["cache-control"].lower()
    assert "set-cookie" not in resp.headers


def test_healthz_runs_select_1_as_menu_app_on_the_pool(
    client: TestClient, worker_db: str, select1_count: Callable[[], int]
) -> None:
    assert client.get("/healthz").status_code == 200
    assert select1_count() == 1
    with pg.admin_connect() as admin:
        users = {
            r[0]
            for r in admin.execute(
                "select usename from pg_stat_activity where datname = %s", (worker_db,)
            ).fetchall()
        }
    assert "menu_app" in users
    assert "menu_owner" not in users


def test_burst_inside_the_window_runs_a_single_select_1(
    client: TestClient, clock: FakeClock, select1_count: Callable[[], int]
) -> None:
    for _ in range(25):
        assert client.get("/healthz").status_code == 200
        clock.advance(0.1)
    assert select1_count() == 1, "A-24: un solo SELECT 1 per finestra di circa 5 s"


def test_result_is_refreshed_after_the_window(
    client: TestClient, clock: FakeClock, select1_count: Callable[[], int]
) -> None:
    client.get("/healthz")
    clock.advance(3.0)
    client.get("/healthz")
    assert select1_count() == 1, "dentro la finestra: ancora in memoria"
    clock.advance(3.5)  # 6,5 s dalla prima misura
    client.get("/healthz")
    assert select1_count() == 2


def test_refreshes_reuse_the_pool_and_open_no_new_connection_per_request(
    client: TestClient, clock: FakeClock, connects: list[float]
) -> None:
    client.get("/healthz")
    opened = len(connects)
    for _ in range(4):
        clock.advance(6.0)
        assert client.get("/healthz").status_code == 200
    assert len(connects) == opened, "THR-106: mai una connessione nuova per richiesta"


@pytest.fixture
def database_down(worker_db: str) -> Iterator[Callable[[bool], None]]:
    """Simula il database fermo: limite 0 sul solo database del worker + backend terminati."""

    def set_down(down: bool) -> None:
        with pg.admin_connect() as admin:
            admin.execute(
                f"alter database {worker_db} connection limit {0 if down else -1}".encode()
            )
            if down:
                admin.execute(
                    "select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname = %s and usename = 'menu_app'",
                    (worker_db,),
                )

    yield set_down
    set_down(False)


def test_healthz_is_503_when_the_database_stops_and_recovers_afterwards(
    client: TestClient, clock: FakeClock, database_down: Callable[[bool], None]
) -> None:
    assert client.get("/healthz").status_code == 200
    database_down(True)
    clock.advance(6.5)
    started = time.monotonic()
    resp = client.get("/healthz")
    assert time.monotonic() - started < 4.0, "THR-106: risposta entro il timeout breve"
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
    assert "no-store" in resp.headers["cache-control"].lower()
    assert "set-cookie" not in resp.headers
    database_down(False)
    clock.advance(6.5)
    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}


def test_503_body_leaks_nothing_about_the_database(
    client: TestClient,
    clock: FakeClock,
    database_down: Callable[[bool], None],
    worker_db: str,
) -> None:
    client.get("/healthz")
    database_down(True)
    clock.advance(6.5)
    resp = client.get("/healthz")
    assert resp.status_code == 503
    body = resp.text.lower()
    for word in ("postgres", "psycopg", "connection", "menu_app", "sqlalchemy", "timeout", "ssl"):
        assert word not in body
    assert set(resp.json()) == {"status"}
