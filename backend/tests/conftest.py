"""Fixture condivise (SL-00a): ambiente pulito, app reale, app con rotte di prova."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from support.paths import REPO

BASE_URL = "https://testserver"


@pytest.fixture
def app_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ambiente deterministico: nessun `.env` letto dalla cwd, APP_ENV=test, nessun proxy."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")


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
    schema: dict[str, Any] = create_app().openapi()
    return schema


@pytest.fixture
def committed_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads((REPO / "openapi.json").read_text(encoding="utf-8"))
    return schema
