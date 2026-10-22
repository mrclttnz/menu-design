"""Configurazione del database: `sslmode=verify-full` obbligatorio all'avvio (A-13, ADR-0003,
ADR-0016; THR-043; SR-023, SR-075). Contratto: variabile `DATABASE_URL_APP`, campo
`Settings.database_url_app`; l'URL non compare mai in repr, errori o log (CWE-532)."""

import pytest
from fastapi.testclient import TestClient

from menu.app import create_app

PW = "CANARY-DB-PASSWORD-9c1"
CA = "sslrootcert=/etc/ssl/certs/test-ca.crt"


def _url(query: str, scheme: str = "postgresql+psycopg") -> str:
    return f"{scheme}://menu_app:{PW}@db.example.test:5432/menu" + (f"?{query}" if query else "")


def _start() -> None:
    with TestClient(create_app()):
        pass


@pytest.mark.parametrize(
    "query",
    [
        "",
        CA,
        f"sslmode=require&{CA}",
        f"sslmode=prefer&{CA}",
        f"sslmode=allow&{CA}",
        f"sslmode=disable&{CA}",
        f"sslmode=verify-ca&{CA}",
        f"sslmode=&{CA}",
        f"sslmode=VERIFY-FULL&{CA}",
        f"sslmode=verify-full&sslmode=require&{CA}",
        f"sslmode=require&sslmode=verify-full&{CA}",
        f"sslmode=verify-fullx&{CA}",
    ],
    ids=lambda q: q or "no-query",
)
def test_startup_refused_unless_sslmode_is_exactly_verify_full(
    app_env: None, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    monkeypatch.setenv("DATABASE_URL_APP", _url(query))
    with pytest.raises(Exception, match=r"verify-full") as info:
        _start()
    assert PW not in str(info.value), "la password non deve comparire nell'errore di avvio"


@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg"])
def test_startup_accepts_verify_full_urls(
    app_env: None, monkeypatch: pytest.MonkeyPatch, scheme: str
) -> None:
    monkeypatch.setenv("DATABASE_URL_APP", _url(f"sslmode=verify-full&{CA}", scheme))
    _start()


@pytest.mark.parametrize("url", ["", "not a url", "mysql://u:p@h/db?sslmode=verify-full"])
def test_startup_refused_with_missing_or_invalid_database_url(
    app_env: None, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL_APP", url)
    with pytest.raises(Exception, match=r"(?i)database_url_app"):
        _start()


def test_startup_refused_without_database_url(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL_APP")
    with pytest.raises(Exception, match=r"(?i)database_url_app"):
        _start()


@pytest.mark.parametrize("app_env_value", ["dev", "test", "staging", "production"])
def test_verify_full_is_required_in_every_environment(
    app_env: None, monkeypatch: pytest.MonkeyPatch, app_env_value: str
) -> None:
    """A-25 / THR-134: APP_ENV non allenta il controllo (nemmeno in dev e test)."""
    monkeypatch.setenv("APP_ENV", app_env_value)
    monkeypatch.setenv("DATABASE_URL_APP", _url(f"sslmode=require&{CA}"))
    with pytest.raises(Exception, match=r"verify-full"):
        _start()


def test_pgsslmode_environment_variable_cannot_weaken_the_check(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PGSSLMODE", "disable")
    monkeypatch.setenv("DATABASE_URL_APP", _url(f"sslmode=require&{CA}"))
    with pytest.raises(Exception, match=r"verify-full"):
        _start()


def test_settings_repr_and_str_do_not_reveal_the_password(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from menu.platform import Settings

    monkeypatch.setenv("DATABASE_URL_APP", _url(f"sslmode=verify-full&{CA}"))
    settings = Settings()
    assert PW not in repr(settings)
    assert PW not in str(settings)
    assert PW not in settings.model_dump_json()
