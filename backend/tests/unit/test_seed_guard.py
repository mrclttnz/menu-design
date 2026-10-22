"""Guardia del comando `seed` ad allow-list (A-22, THR-133, SR-029; 08 §14.1).

Parte solo con `APP_ENV` esattamente `dev` o `staging`, `SEED_TARGET` esplicito `local` o
`staging` e host del database in `SEED_ALLOWED_DB_HOSTS`. Qualunque altro caso esce con codice
≠ 0 SENZA connettersi. Contratto: `menu.seeding.guard.assert_seed_allowed(app_env=, database_url=,
seed_target=, allowed_hosts=)` solleva `SeedNotAllowed`; comando `python -m menu seed --dataset X`.
"""

import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from support.paths import BACKEND, SRC, TESTS

PW = "CANARY-SEED-PASSWORD"


def _url(host: str, port: int = 5432) -> str:
    return (
        f"postgresql+psycopg://menu_owner:{PW}@{host}:{port}/menu"
        "?sslmode=verify-full&sslrootcert=/nonexistent/ca.crt"
    )


@pytest.mark.parametrize(
    ("app_env", "target"), [("dev", "local"), ("staging", "staging"), ("dev", "staging")]
)
def test_guard_allows_the_allow_listed_combination(app_env: str, target: str) -> None:
    from menu.seeding.guard import assert_seed_allowed

    assert_seed_allowed(
        app_env=app_env,
        database_url=_url("localhost"),
        seed_target=target,
        allowed_hosts="localhost,db.staging.example.test",
    )


@pytest.mark.parametrize(
    "app_env",
    [None, "", " ", "production", "prod", "Production", "PRODUCTION", "test", "Dev", "DEV",
     "dev ", " dev", "staging ", "Staging", "development", "stage", "local"],
)  # fmt: skip
def test_guard_refuses_every_app_env_but_exactly_dev_or_staging(app_env: str | None) -> None:
    from menu.seeding.guard import SeedNotAllowed, assert_seed_allowed

    with pytest.raises(SeedNotAllowed):
        assert_seed_allowed(
            app_env=app_env,
            database_url=_url("localhost"),
            seed_target="local",
            allowed_hosts="localhost",
        )


@pytest.mark.parametrize(
    "target", [None, "", "production", "prod", "Local", "LOCAL", "test", "local ", "all"]
)
def test_guard_requires_an_explicit_target(target: str | None) -> None:
    from menu.seeding.guard import SeedNotAllowed, assert_seed_allowed

    with pytest.raises(SeedNotAllowed):
        assert_seed_allowed(
            app_env="dev",
            database_url=_url("localhost"),
            seed_target=target,
            allowed_hosts="localhost",
        )


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("db.production.example.test", "localhost"),
        ("localhost", None),
        ("localhost", ""),
        ("db.example.test.evil.test", "db.example.test"),
        ("evil-db.example.test", "db.example.test"),
        ("localhost.evil.test", "localhost"),
        ("aws-0-eu-central-1.pooler.supabase.com", "localhost,staging.example.test"),
    ],
)
def test_guard_refuses_a_database_host_outside_the_allow_list(
    host: str, allowed: str | None
) -> None:
    """THR-133: l'host deve coincidere per intero (non sottostringa) con la lista."""
    from menu.seeding.guard import SeedNotAllowed, assert_seed_allowed

    with pytest.raises(SeedNotAllowed):
        assert_seed_allowed(
            app_env="dev", database_url=_url(host), seed_target="local", allowed_hosts=allowed
        )


def test_guard_error_never_contains_the_database_password() -> None:
    from menu.seeding.guard import SeedNotAllowed, assert_seed_allowed

    with pytest.raises(SeedNotAllowed) as info:
        assert_seed_allowed(
            app_env="production",
            database_url=_url("db.prod.example.test"),
            seed_target="local",
            allowed_hosts="localhost",
        )
    assert PW not in str(info.value)
    assert PW not in repr(info.value)


@contextmanager
def _listener() -> Iterator[tuple[int, list[int]]]:
    """Porta TCP locale che conta le connessioni: la guardia non deve mai toccarla."""
    accepted: list[int] = []
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    server.settimeout(0.2)
    stop = threading.Event()

    def run() -> None:
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError, OSError:
                continue
            accepted.append(1)
            conn.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield server.getsockname()[1], accepted
    finally:
        stop.set()
        thread.join(2)
        server.close()


def _run_seed(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    import os

    base = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    return subprocess.run(
        [sys.executable, "-I", "-m", "menu", "seed", "--dataset", "isolation"],
        cwd=BACKEND,
        env={**base, **env},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _assert_refused_by_the_guard(proc: subprocess.CompletedProcess[str]) -> None:
    """Contratto: la guardia esce con codice 2 e `seed refused: <motivo>` su stderr.

    Il codice 1 di "No module named menu.__main__" NON vale come rifiuto.
    """
    assert proc.returncode == 2, (proc.returncode, proc.stderr[-300:])
    assert "seed refused" in proc.stderr


def _env(port: int, **override: str) -> dict[str, str]:
    url = _url("127.0.0.1", port)
    env = {
        "APP_ENV": "dev",
        "SEED_TARGET": "local",
        "SEED_ALLOWED_DB_HOSTS": "127.0.0.1",
        "DATABASE_URL_APP": url,
        "DATABASE_URL_OWNER": url,
        "TRUSTED_PROXY_HOPS": "0",
        "PYTHONPATH": str(SRC.parent),
    }
    env.update(override)
    return {k: v for k, v in env.items() if v != "__unset__"}


@pytest.mark.parametrize(
    "app_env", ["production", "prod", "Production", "test", "", "__unset__", "DEV", "Staging"]
)
def test_seed_command_refuses_without_connecting_for_non_allow_listed_app_env(
    app_env: str,
) -> None:
    with _listener() as (port, accepted):
        proc = _run_seed(_env(port, APP_ENV=app_env))
    _assert_refused_by_the_guard(proc)
    assert accepted == [], "la guardia ha aperto una connessione al database"
    assert PW not in proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "override",
    [
        {"SEED_TARGET": "__unset__"},
        {"SEED_TARGET": "production"},
        {"SEED_ALLOWED_DB_HOSTS": "__unset__"},
        {"SEED_ALLOWED_DB_HOSTS": "db.production.example.test"},
    ],
)
def test_seed_command_refuses_without_connecting_for_target_or_host_outside_allow_list(
    override: dict[str, str],
) -> None:
    with _listener() as (port, accepted):
        proc = _run_seed(_env(port, **override))
    _assert_refused_by_the_guard(proc)
    assert accepted == []
    assert PW not in proc.stdout + proc.stderr


def test_seed_command_with_app_env_test_exits_nonzero_without_connecting() -> None:
    """08 §14.1: con `APP_ENV=test` il comando non parte; i test usano la libreria."""
    with _listener() as (port, accepted):
        proc = _run_seed(_env(port, APP_ENV="test"))
    _assert_refused_by_the_guard(proc)
    assert accepted == []


def test_no_test_imports_the_seed_command_module() -> None:
    """08 §14.1: nessun file sotto `tests/` importa il modulo del comando (né `menu.__main__`)."""
    assert (SRC / "seeding" / "command.py").is_file(), "modulo del comando assente"
    assert (SRC / "__main__.py").is_file()
    offenders: list[str] = []
    import ast

    for path in TESTS.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[Any] = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or "", *[f"{node.module}.{a.name}" for a in node.names]]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            if any(n in {"menu.seeding.command", "menu.__main__", "menu"} and n != "menu"
                   for n in names):  # fmt: skip
                offenders.append(f"{path}:{getattr(node, 'lineno', 0)}")
    assert offenders == []


@pytest.mark.parametrize("url", [None, "", "not a url", "postgresql://[bad"])
def test_guard_refuses_when_the_database_host_cannot_be_determined(url: str | None) -> None:
    from menu.seeding.guard import SeedNotAllowed, assert_seed_allowed

    with pytest.raises(SeedNotAllowed):
        assert_seed_allowed(
            app_env="dev", database_url=url, seed_target="local", allowed_hosts="localhost"
        )
