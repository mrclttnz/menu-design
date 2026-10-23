"""Fixture condivise (SL-00a): ambiente pulito, app reale, app con rotte di prova."""

import json
import secrets
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from support import pg
from support.accounts import AlfaWorld, make_alfa
from support.browser_sim import Browser
from support.fake_oidc import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, FakeOidc
from support.fake_oidc_server import StubServer
from support.inventory import FamilyTableSpec
from support.owner import Owner
from support.paths import REPO

BASE_URL = "https://testserver"
# Database per i test senza cluster: pool pigro, mai connesso (porta 1 chiusa).
DUMMY_DATABASE_URL = (
    "postgresql+psycopg://" + "menu_app:" + "dummy-unit-tests" + "@localhost:1/menu"
    "?sslmode=verify-full&sslrootcert=/nonexistent/ca.crt"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Marker `db` automatico per ogni test che usa il database di test (08 §2)."""
    for item in items:
        if "worker_db" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.db)


@pytest.fixture
def app_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ambiente deterministico: nessun `.env` letto dalla cwd, APP_ENV=test, nessun proxy."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    monkeypatch.setenv("DATABASE_URL_APP", DUMMY_DATABASE_URL)
    # SL-03a: configurazione di Google (segnaposto sintetici). L'emittente resta quello di
    # default (Google): all'avvio l'app non fa alcuna richiesta di rete, la discovery è pigra.
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("APP_BASE_URL", BASE_URL)


@pytest.fixture
def probe_calls() -> list[str]:
    """Registro delle esecuzioni degli handler di prova."""
    return []


@pytest.fixture
def probe_client(app_env: None, probe_calls: list[str]) -> Iterator[TestClient]:
    """App reale + rotte di prova. Le eccezioni non gestite diventano risposte 500."""
    from menu.app import create_app  # import tardivo: i test di architettura non lo richiedono
    from support.probe import build_probe_router

    app = create_app(extra_routers=[build_probe_router(probe_calls)])
    with TestClient(app, base_url=BASE_URL, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def real_client(app_env: None) -> Iterator[TestClient]:
    """App reale, senza rotte di prova."""
    from menu.app import create_app

    with TestClient(create_app(), base_url=BASE_URL, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def generated_schema(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    from menu.app import create_app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    monkeypatch.setenv("DATABASE_URL_APP", DUMMY_DATABASE_URL)
    schema: dict[str, Any] = create_app().openapi()
    return schema


@pytest.fixture
def committed_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads((REPO / "openapi.json").read_text(encoding="utf-8"))
    return schema


# --- database di test (SL-00b): cluster PostgreSQL 17 reale, template + un database per worker ---

_ORIGINAL_NOW: dict[str, str] = {}


@pytest.fixture(scope="session")
def pg_templates() -> tuple[str, str]:
    pg.check_cluster_or_exit()
    return pg.ensure_templates()


@pytest.fixture(scope="session")
def worker_db(pg_templates: tuple[str, str]) -> Iterator[str]:
    """Database del worker, clonato dal template `upgrade head` (08 §4.1)."""
    name = f"menu_w_{pg.worker_id()}_{secrets.token_hex(4)}"
    with pg.admin_connect() as admin:
        pg.create_db(admin, name, template=pg_templates[1])
    try:
        yield name
    finally:
        pg.drop_db(name)


def _restore_now_if_replaced(db: str) -> bool:
    original = _ORIGINAL_NOW.get(db)
    if original is None:
        return False
    with pg.admin_connect(db) as admin:
        row = admin.execute(
            "select p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'app' and p.proname = 'now_utc'"
        ).fetchone()
        if row is None or row[0] == original:
            return False
        admin.execute(
            (
                "create or replace function app.now_utc() returns timestamptz language sql "
                "stable parallel safe as $body$" + original + "$body$"
            ).encode()
        )
    return True


@pytest.fixture(autouse=True)
def _db_hygiene(request: pytest.FixtureRequest) -> Iterator[None]:
    """Dopo ogni test su DB: TRUNCATE dei dati e ripristino di `app.now_utc()` (08 §4.1, §4.4)."""
    if "worker_db" not in request.fixturenames:
        yield
        return
    db: str = request.getfixturevalue("worker_db")
    if db not in _ORIGINAL_NOW:
        with pg.admin_connect(db) as admin:
            row = admin.execute(
                "select p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                "where n.nspname = 'app' and p.proname = 'now_utc'"
            ).fetchone()
        if row is not None:
            _ORIGINAL_NOW[db] = row[0]
    yield
    with pg.admin_connect(db) as admin:
        tables = admin.execute(
            "select quote_ident(schemaname) || '.' || quote_ident(tablename) from pg_tables "
            "where schemaname = 'app' and tablename <> 'alembic_version'"
        ).fetchall()
        if tables:
            admin.execute(("truncate " + ", ".join(t[0] for t in tables) + " cascade").encode())
    assert not _restore_now_if_replaced(db), "test ha lasciato app.now_utc() sostituita (08 §4.4)"


@pytest.fixture
def owner(worker_db: str) -> Owner:
    return Owner(worker_db)


@pytest.fixture
def connect_app(worker_db: str) -> Callable[..., psycopg.Connection]:
    """Apre una connessione TLS come `menu_app` (chiamare nel test, non in una fixture)."""

    def _connect(role: str = "menu_app", *, autocommit: bool = True) -> psycopg.Connection:
        return pg.connect_as(role, worker_db, autocommit=autocommit)

    return _connect


@pytest.fixture
def frozen_now(owner: Owner, worker_db: str) -> Iterator[Callable[[datetime], None]]:
    """Sposta l'orologio del database (solo test, via owner) e lo ripristina all'uscita."""
    yield owner.set_test_now
    original = _ORIGINAL_NOW.get(worker_db)
    if original is not None:
        owner.restore_now(original)


@pytest.fixture
def app_url(worker_db: str) -> str:
    return pg.cluster().role_url("menu_app", worker_db, sqlalchemy=True)


@pytest.fixture
def db_env(app_env: None, monkeypatch: pytest.MonkeyPatch, app_url: str) -> None:
    """Ambiente dell'app collegata al database di test come `menu_app` (verify-full)."""
    monkeypatch.setenv("DATABASE_URL_APP", app_url)


@pytest.fixture
def db_client(db_env: None) -> Iterator[TestClient]:
    """App reale collegata al database di test (pool reale, ruolo `menu_app`)."""
    from menu.app import create_app

    with TestClient(create_app(), base_url=BASE_URL, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def make_probe_table(owner: Owner) -> Iterator[Callable[..., tuple[str, FamilyTableSpec]]]:
    """Tabelle SINTETICHE di famiglia per provare che gli inventari sanno fallire.

    Create e distrutte dal test; compaiono negli inventari solo mentre il test le usa.
    """
    created: list[str] = []

    def make(
        *,
        policy_using: str = "family_id = app.current_family_id()",
        policy_check: str | None = "family_id = app.current_family_id()",
        rls: bool = True,
        force: bool = True,
        p_owner: bool = True,
        p_backup: bool = True,
        family_column: bool = True,
        name: str | None = None,
    ) -> tuple[str, FamilyTableSpec]:
        table = name or f"zz_probe_{secrets.token_hex(3)}"
        created.append(table)
        col = "family_id uuid not null," if family_column else ""
        stmts = [
            f"create table app.{table} (id uuid primary key default gen_random_uuid(), {col} "
            "label text not null default 'x')",
            f"grant select, insert, update, delete on app.{table} to menu_app",
        ]
        if rls:
            stmts.append(f"alter table app.{table} enable row level security")
        if force:
            stmts.append(f"alter table app.{table} force row level security")
        check = f" with check ({policy_check})" if policy_check else ""
        if family_column:
            stmts.append(
                f"create policy p_family on app.{table} for all to menu_app "
                f"using ({policy_using}){check}"
            )
        if p_owner:
            stmts.append(
                f"create policy p_owner on app.{table} for all to menu_owner "
                "using (true) with check (true)"
            )
        if p_backup:
            stmts.append(
                f"create policy p_backup on app.{table} for select to menu_backup using (true)"
            )
        owner.script("; ".join(stmts))

        def seed(o: Owner, family: UUID) -> None:
            o.execute(f"insert into app.{table} (family_id, label) values (%s, 'seed')", (family,))  # noqa: S608  (identificatore generato dal test o dal catalogo)

        def insert_sql(family: UUID) -> tuple[str, tuple[Any, ...]]:
            return f"insert into app.{table} (family_id, label) values (%s, 'x')", (family,)  # noqa: S608  (identificatore generato dal test o dal catalogo)

        return table, FamilyTableSpec(seed=seed, insert_sql=insert_sql)

    yield make
    for table in created:
        owner.execute(f"drop table if exists app.{table} cascade")


@pytest.fixture
def two_families() -> tuple[UUID, UUID]:
    return uuid4(), uuid4()


@pytest.fixture
def catalog(worker_db: str) -> Iterator[psycopg.Connection]:
    """Connessione di sola lettura del catalogo (superutente del cluster di test)."""
    with pg.admin_connect(worker_db) as conn:
        yield conn


# --- accesso con Google (SL-03a): provider OIDC finto su HTTP locale, app su database reale ------


@pytest.fixture(scope="session")
def oidc_server() -> Iterator[StubServer]:
    """Un server OIDC finto per worker (127.0.0.1, porta libera); stato nuovo per test."""
    server = StubServer()
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def oidc(oidc_server: StubServer) -> FakeOidc:
    return oidc_server.fresh(redirect_uri=REDIRECT_URI)


@pytest.fixture
def auth_env(db_env: None, oidc: FakeOidc, monkeypatch: pytest.MonkeyPatch) -> None:
    """App con database di test e `OIDC_ISSUER` = il provider finto (solo con `APP_ENV=test`)."""
    monkeypatch.setenv("OIDC_ISSUER", oidc.issuer)


@pytest.fixture
def auth_client(auth_env: None) -> Iterator[TestClient]:
    from menu.app import create_app

    with TestClient(create_app(), base_url=BASE_URL, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def browser(auth_client: TestClient) -> Browser:
    return Browser(auth_client)


@pytest.fixture
def other_browser(auth_client: TestClient) -> Browser:
    """Un secondo browser sullo stesso server (la vittima e l'aggressore, un altro dispositivo)."""
    return Browser(auth_client)


@pytest.fixture
def alfa(owner: Owner) -> AlfaWorld:
    """Famiglia Alfa (Amministratore e Membro con account) e un'identità senza famiglia."""
    return make_alfa(owner)
