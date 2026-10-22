"""Contesto di famiglia sotto concorrenza (THR-027, SR-042; 08 §9): connessioni del pool in
parallelo e riusate non si scambiano il contesto. Invariante: ogni transazione vede SOLO il
proprio `family_id`; una transazione senza contesto non vede mai quello di un'altra.
"""

import importlib
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from support.ctx import make_ctx

pytestmark = pytest.mark.concurrency

THREADS = 6
ROUNDS = 8
READ = text("select current_setting('app.family_id', true), pg_backend_pid()")


@pytest.fixture
def tenancy(app_url: str) -> Iterator[Any]:
    module: Any = importlib.import_module("menu.tenancy")
    module.init(app_url)
    try:
        yield module
    finally:
        module.dispose()


def test_parallel_family_transactions_never_see_each_others_context(tenancy: Any) -> None:
    barrier = threading.Barrier(THREADS)
    families = [uuid4() for _ in range(THREADS)]
    seen: list[tuple[UUID, str | None, str | None]] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        fam = families[index]
        for _ in range(ROUNDS):
            barrier.wait(timeout=30)
            with tenancy.family_tx(make_ctx(fam)) as tx:
                inside = tx.execute(READ).one()[0]
            with tenancy.system_tx() as tx:
                outside = tx.execute(READ).one()[0]
            with lock:
                seen.append((fam, inside, outside))

    with ThreadPoolExecutor(THREADS) as pool:
        for f in [pool.submit(worker, i) for i in range(THREADS)]:
            f.result(timeout=120)
    assert len(seen) == THREADS * ROUNDS
    assert all(inside == str(fam) for fam, inside, _ in seen), "contesto scambiato tra famiglie"
    assert all(outside in (None, "") for _, _, outside in seen), "contesto sopravvissuto alla tx"
