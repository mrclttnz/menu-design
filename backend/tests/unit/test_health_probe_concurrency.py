"""SEC-SL00b-003 (THR-106, A-24): con il DB lento, un solo controllo e nessuno in coda."""

import threading
import time

import pytest

from menu.app.health import WINDOW_SECONDS, HealthProbe


class SlowPing:
    def __init__(self, duration: float) -> None:
        self.duration = duration
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self) -> None:
        with self._lock:
            self.calls += 1
        time.sleep(self.duration)


def test_slow_probe_runs_once_and_concurrent_callers_do_not_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ping = SlowPing(0.6)
    monkeypatch.setattr("menu.app.health.tenancy.ping", ping)
    probe = HealthProbe(time.monotonic)
    results: list[tuple[bool, float]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(5)

    def caller() -> None:
        barrier.wait(timeout=5)
        started = time.monotonic()
        ok = probe.database_ok()
        with lock:
            results.append((ok, time.monotonic() - started))

    threads = [threading.Thread(target=caller) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert ping.calls == 1
    waits = sorted(w for _, w in results)
    assert waits[-2] < 0.3, "i chiamanti concorrenti non devono aspettare il controllo in corso"


def test_window_starts_after_the_probe_not_before(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]

    def clock() -> float:
        return now[0]

    calls: list[int] = []

    def ping() -> None:
        calls.append(1)
        now[0] += WINDOW_SECONDS + 1  # controllo più lento della finestra

    monkeypatch.setattr("menu.app.health.tenancy.ping", ping)
    probe = HealthProbe(clock)
    assert probe.database_ok() is True
    assert probe.database_ok() is True
    assert len(calls) == 1, "l'esito deve restare valido dopo un controllo lento"
