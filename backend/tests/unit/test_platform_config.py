"""APP_ENV obbligatorio e configurazione fail-closed (piano §6.4 A-25, THR-134; SR-076 area)."""

import pytest
from fastapi.testclient import TestClient

from menu.app import create_app


def _start() -> None:
    with TestClient(create_app()):
        pass


def test_startup_refused_without_app_env(app_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV")
    with pytest.raises(Exception, match=r"(?i)app_env"):
        _start()


@pytest.mark.parametrize("value", ["", "prod", "development", "local", "stagging", "none"])
def test_startup_refused_with_unknown_app_env(
    app_env: None, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("APP_ENV", value)
    with pytest.raises(Exception, match=r"(?i)app_env"):
        _start()


@pytest.mark.parametrize("value", ["dev", "test", "staging", "production"])
def test_startup_accepts_each_allowed_app_env(
    app_env: None, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("APP_ENV", value)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")  # SEC-SL03b-003: >= 1 in staging e production
    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 503  # DB di prova irraggiungibile (SL-00b)


@pytest.mark.parametrize("value", ["dev", "test", "staging", "production"])
def test_debug_is_off_in_every_environment(
    app_env: None, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """APP_ENV non disattiva né attiva controlli: il debug resta spento (piano §5.2, A-25)."""
    monkeypatch.setenv("APP_ENV", value)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")  # SEC-SL03b-003: >= 1 in staging e production
    assert create_app().debug is False


@pytest.mark.parametrize("value", ["-1", "abc", "1.5"])
def test_startup_refused_with_invalid_trusted_proxy_hops(
    app_env: None, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", value)
    with pytest.raises(Exception, match=r"(?i)trusted_proxy_hops"):
        _start()
