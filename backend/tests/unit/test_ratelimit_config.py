"""Configurazione dei limiti di frequenza (SL-03b): fail closed all'avvio, catalogo eventi.

SEC-SL00a-005: `TRUSTED_PROXY_HOPS` non ha valore predefinito (0 renderebbe globali i limiti per IP
dietro Cloud Run). ADR-0006: il pepper delle chiavi HMAC è un segreto obbligatorio
(`SESSION_PEPPER`, già annunciato da `.env.example` per SL-03b), mai nei log né nel repr.
SR-020: gli eventi `rate_limit.exceeded` e `session.evicted` sono nel catalogo.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from menu.audit import EVENT_TYPES
from menu.platform import Settings


def _start() -> None:
    from menu.app import create_app

    with TestClient(create_app()):
        pass


def test_startup_refused_without_trusted_proxy_hops(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TRUSTED_PROXY_HOPS")
    with pytest.raises(Exception, match=r"(?i)trusted_proxy_hops"):
        _start()


def test_the_settings_model_has_no_default_for_trusted_proxy_hops(app_env: None) -> None:
    assert Settings.model_fields["trusted_proxy_hops"].is_required()


@pytest.mark.parametrize("value", ["", "   "])
def test_startup_refused_with_an_empty_trusted_proxy_hops(
    app_env: None, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", value)
    with pytest.raises(Exception, match=r"(?i)trusted_proxy_hops"):
        _start()


@pytest.mark.parametrize("hops", ["0", "1", "2"])
def test_startup_accepts_explicit_trusted_proxy_hops(
    app_env: None, monkeypatch: pytest.MonkeyPatch, hops: str
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", hops)
    _start()


def test_startup_refused_without_the_pepper(app_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_PEPPER")
    with pytest.raises(Exception, match=r"(?i)session_pepper"):
        _start()


@pytest.mark.parametrize("value", ["", "   "])
def test_startup_refused_with_an_empty_pepper(
    app_env: None, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SESSION_PEPPER", value)
    with pytest.raises(Exception, match=r"(?i)session_pepper"):
        _start()


def test_the_pepper_is_refused_when_it_is_the_placeholder_or_too_short(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.env.example` porta `CHANGE_ME`: copiarlo senza sostituirlo non deve avviare l'app."""
    for weak in ("CHANGE_ME", "short"):
        monkeypatch.setenv("SESSION_PEPPER", weak)
        with pytest.raises(Exception, match=r"(?i)session_pepper"):
            _start()


def test_the_pepper_is_a_secret_never_shown_in_repr_or_errors(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "unit-test-pepper-0123456789abcdef0123456789abcdef"  # noqa: S105  (segnaposto sintetico)
    monkeypatch.setenv("SESSION_PEPPER", secret)
    settings = Settings()
    assert isinstance(settings.session_pepper, SecretStr)
    assert secret not in repr(settings)
    assert secret not in str(settings)
    assert secret not in settings.model_dump_json()


def test_the_catalog_has_the_events_of_this_slice() -> None:
    assert {"rate_limit.exceeded", "session.evicted"} <= EVENT_TYPES


@pytest.mark.parametrize("env", ["staging", "production"])
def test_sec_sl03b_003_zero_proxy_hops_is_refused_in_strict_environments(
    app_env: None, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    with pytest.raises(Exception, match=r"TRUSTED_PROXY_HOPS deve essere almeno 1"):
        Settings()


@pytest.mark.parametrize("env", ["dev", "test"])
def test_sec_sl03b_003_zero_proxy_hops_is_still_fine_locally(
    app_env: None, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    assert Settings().trusted_proxy_hops == 0
