"""`menu.tenancy`: family_tx / system_tx e riuso della connessione (ADR-0003, 05-data §6.1;
SR-042; THR-027, THR-026). Contesto SOLO con `set_config(..., true)`, locale alla transazione.

Contratto assunto (plan §3, nota nel report): `tenancy.init(url)`/`tenancy.dispose()` creano e
chiudono l'engine; `family_tx(ctx)` e `system_tx()` sono context manager SINCRONI che restituiscono
una `sqlalchemy.Connection` (`Tx`) in una transazione.
"""

import importlib
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from support import pg
from support.ctx import make_ctx
from support.owner import Owner
from support.paths import SRC
from support.sqlscan import session_scope_violations

SETTINGS = text(
    "select current_setting('app.family_id', true), current_setting('app.account_id', true), "
    "current_setting('app.role', true), pg_backend_pid(), current_user"
)


@pytest.fixture
def tenancy(app_url: str) -> Iterator[Any]:
    module: Any = importlib.import_module("menu.tenancy")

    module.init(app_url)
    try:
        yield module
    finally:
        module.dispose()


def test_family_tx_sets_family_account_and_role_inside_the_transaction(tenancy: Any) -> None:
    fam, acc = uuid4(), uuid4()
    with tenancy.family_tx(make_ctx(fam, acc, "admin")) as tx:
        row = tx.execute(SETTINGS).one()
    assert (row[0], row[1], row[2]) == (str(fam), str(acc), "admin")
    assert row[4] == "menu_app", "l'app lavora sempre come menu_app (SR-042)"


def test_context_does_not_survive_the_transaction(tenancy: Any) -> None:
    """THR-027: nessun `set_config(..., false)`: sulla stessa connessione il contesto sparisce."""
    fam = uuid4()
    with tenancy.family_tx(make_ctx(fam, uuid4(), "admin")) as tx:
        first = tx.execute(SETTINGS).one()
    with tenancy.system_tx() as tx:
        second = tx.execute(SETTINGS).one()
    assert first[3] == second[3], "precondizione: stessa connessione del pool (stesso backend)"
    assert second[0] in (None, "")
    assert second[1] in (None, "")
    assert second[2] in (None, "")


def test_context_is_cleared_after_a_failed_transaction(tenancy: Any) -> None:
    fam = uuid4()

    def fail() -> None:
        with tenancy.family_tx(make_ctx(fam)) as tx:
            tx.execute(SETTINGS)
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        fail()
    with tenancy.system_tx() as tx:
        row = tx.execute(SETTINGS).one()
    assert row[0] in (None, "")


def test_family_tx_refuses_a_context_without_family(tenancy: Any) -> None:
    """Fail closed: nessun accesso di famiglia senza `family_id` (SR-008)."""
    with pytest.raises(ValueError, match="family"), tenancy.family_tx(make_ctx(None)):
        pass


def test_system_tx_has_no_family_context_even_after_a_family_tx(tenancy: Any) -> None:
    with tenancy.family_tx(make_ctx(uuid4())):
        pass
    with tenancy.system_tx() as tx:
        row = tx.execute(SETTINGS).one()
    assert row[0] in (None, "")
    assert row[4] == "menu_app"


def test_connections_use_psycopg_without_prepared_statements(tenancy: Any) -> None:
    """ADR-0003 / ADR-0014: `prepare_threshold=None` per il pooler in modalità transazione."""
    with tenancy.system_tx() as tx:
        raw = tx.connection.driver_connection
    assert raw.prepare_threshold is None


def test_rls_applies_through_tenancy_and_is_not_leaked_by_connection_reuse(
    tenancy: Any, make_probe_table: Any, owner: Owner
) -> None:
    """THR-027 + THR-026 su una tabella di famiglia SINTETICA (non esistono ancora tabelle vere)."""
    table, spec = make_probe_table()
    fam_a, fam_b = uuid4(), uuid4()
    spec.seed(owner, fam_a)
    spec.seed(owner, fam_b)
    probe = sa.table(table, sa.column("family_id"), schema="app")
    count = sa.select(sa.func.count()).select_from(probe)
    with tenancy.family_tx(make_ctx(fam_a)) as tx:
        pid_a = tx.execute(SETTINGS).one()[3]
        assert tx.execute(count).scalar_one() == 1
    with tenancy.system_tx() as tx:
        pid_none = tx.execute(SETTINGS).one()[3]
        assert tx.execute(count).scalar_one() == 0, "senza contesto: zero righe"
    with tenancy.family_tx(make_ctx(fam_b)) as tx:
        assert tx.execute(count).scalar_one() == 1
    assert pid_a == pid_none, "precondizione: stessa connessione riusata"


def test_family_tx_rejects_a_write_for_another_family(tenancy: Any, make_probe_table: Any) -> None:
    table, _ = make_probe_table()
    probe = sa.table(table, sa.column("family_id"), schema="app")
    insert = sa.insert(probe).values(family_id=sa.bindparam("f"))
    with (
        pytest.raises(DBAPIError, match="row-level security"),
        tenancy.family_tx(make_ctx(uuid4())) as tx,
    ):
        tx.execute(insert, {"f": uuid4()})


def test_engine_hides_sql_parameters_in_errors(tenancy: Any) -> None:
    """SEC-SL00a-006: `hide_parameters=True`, i valori non finiscono nei messaggi d'errore."""
    canary = "CANARY-SQL-PARAMETER-VALUE"
    with pytest.raises(DBAPIError) as info, tenancy.system_tx() as tx:
        tx.execute(text("select 1 / 0 where :p = :p"), {"p": canary})
    assert canary not in str(info.value)


def test_tenancy_sources_never_set_session_scoped_context() -> None:
    """Rete statica (oltre a semgrep): in `tenancy` solo `set_config(..., true)`, nessun SET."""
    sources = list((SRC / "tenancy").rglob("*.py"))
    code = "\n".join(p.read_text(encoding="utf-8") for p in sources)
    assert "set_config" in code, "tenancy deve impostare il contesto con set_config"
    assert session_scope_violations(code) == []


def test_uninitialised_tenancy_fails_closed_and_dispose_is_idempotent(app_url: str) -> None:
    """Rami di `init`/`dispose`/`_require_engine`: niente engine implicito, ripetibile."""
    module: Any = importlib.import_module("menu.tenancy")
    module.dispose()
    module.dispose()
    with pytest.raises(RuntimeError, match="tenancy"), module.system_tx():
        pass
    module.init(app_url)
    module.init(app_url)  # re-init: chiude il pool precedente
    try:
        with module.system_tx() as tx:
            assert tx.execute(text("select 1")).scalar_one() == 1
    finally:
        module.dispose()


def test_ping_recovers_after_the_pooled_connection_was_killed(tenancy: Any, worker_db: str) -> None:
    """`ping` ritenta una volta se la connessione del pool era caduta (riavvio del DB/pooler)."""
    tenancy.ping()
    with pg.admin_connect() as admin:
        admin.execute(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where datname = %s and usename = 'menu_app'",
            (worker_db,),
        )
    tenancy.ping()
