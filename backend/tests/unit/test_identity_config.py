"""Configurazione dell'accesso con Google (SL-03a): emittente OIDC fissato per ambiente.

ASM-073, 08 §4.2: con `APP_ENV=production` o `staging` la configurazione rifiuta qualunque
emittente diverso da `https://accounts.google.com` e l'avvio fallisce; il provider finto vive
solo in `dev` e `test`. THR-001 (token di uno stub non accettati dalla produzione), THR-131,
THR-134 (APP_ENV non disattiva controlli), SR-001, SR-076 (segreti non negli errori).

Contratto assunto (variabili d'ambiente, nel report di slice):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET   obbligatorie in `staging` e `production`
  OIDC_ISSUER                              predefinito `https://accounts.google.com`
  APP_BASE_URL                             origine pubblica dell'app (redirect URI, controllo
                                           di `Origin`); `https` in `staging` e `production`
All'avvio l'app non fa richieste di rete (la discovery è pigra, al primo accesso).
"""

import pytest
from fastapi.testclient import TestClient

from menu.app import create_app
from support.fake_oidc import FAKE_ISSUER, GOOGLE_ISSUER

CANARY_SECRET = "CANARY-GOOGLE-SECRET-0123456789"  # noqa: S105


def _start() -> None:
    with TestClient(create_app()):
        pass


@pytest.mark.parametrize("env", ["production", "staging"])
@pytest.mark.parametrize(
    "issuer",
    [
        FAKE_ISSUER,
        "http://127.0.0.1:8099",
        "http://localhost:8099",
        "https://accounts.google.com/",
        "http://accounts.google.com",
        "https://accounts.google.com.evil.example",
        "https://evil.example/accounts.google.com",
        "https://ACCOUNTS.GOOGLE.COM",
        "https://accounts.google.com:444",
        "https://user@accounts.google.com",
        "accounts.google.com",
        "",
    ],
)
def test_production_and_staging_refuse_any_issuer_other_than_google(
    app_env: None, monkeypatch: pytest.MonkeyPatch, env: str, issuer: str
) -> None:
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("OIDC_ISSUER", issuer)
    with pytest.raises(Exception, match=r"(?i)oidc_issuer"):
        _start()


@pytest.mark.parametrize("env", ["production", "staging"])
def test_production_and_staging_accept_google_explicitly_and_by_default(
    app_env: None, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")  # SEC-SL03b-003: >= 1 in staging e production
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    _start()  # predefinito = Google
    monkeypatch.setenv("OIDC_ISSUER", GOOGLE_ISSUER)
    _start()


@pytest.mark.parametrize("env", ["dev", "test"])
@pytest.mark.parametrize("issuer", [FAKE_ISSUER, "http://127.0.0.1:8099", GOOGLE_ISSUER])
def test_dev_and_test_accept_the_stub_issuer(
    app_env: None, monkeypatch: pytest.MonkeyPatch, env: str, issuer: str
) -> None:
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("OIDC_ISSUER", issuer)
    _start()


@pytest.mark.parametrize("name", ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"])
@pytest.mark.parametrize("env", ["production", "staging"])
@pytest.mark.parametrize("value", [None, ""])
def test_production_and_staging_refuse_to_start_without_the_google_client(
    app_env: None, monkeypatch: pytest.MonkeyPatch, name: str, env: str, value: str | None
) -> None:
    """Fail closed (piano §5.2): un accesso senza client OAuth non parte a metà."""
    monkeypatch.setenv("APP_ENV", env)
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    with pytest.raises(Exception, match=rf"(?i){name}"):
        _start()


@pytest.mark.parametrize("env", ["production", "staging"])
@pytest.mark.parametrize("base", ["http://app.example.test", "app.example.test", "ftp://x"])
def test_production_and_staging_require_an_https_base_url(
    app_env: None, monkeypatch: pytest.MonkeyPatch, env: str, base: str
) -> None:
    """I cookie `__Host-` esigono `Secure`; il redirect URI registrato è https (SR-023)."""
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("APP_BASE_URL", base)
    with pytest.raises(Exception, match=r"(?i)app_base_url"):
        _start()


def test_configuration_errors_never_echo_the_client_secret(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CWE-532: né il messaggio dell'eccezione né la sua rappresentazione contengono il segreto."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", CANARY_SECRET)
    monkeypatch.setenv("OIDC_ISSUER", FAKE_ISSUER)
    with pytest.raises(Exception, match=r"(?i)oidc_issuer") as raised:
        _start()
    assert CANARY_SECRET not in str(raised.value)
    assert CANARY_SECRET not in repr(raised.value)


def test_settings_hold_the_client_secret_as_a_secret_str_that_repr_hides(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CWE-532: il segreto del client è un `SecretStr`; repr, str e JSON non lo mostrano."""
    from pydantic import SecretStr

    from menu.platform import Settings

    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", CANARY_SECRET)
    settings = Settings()
    held = [
        v
        for v in vars(settings).values()
        if isinstance(v, SecretStr) and v.get_secret_value() == CANARY_SECRET
    ]
    assert held, "il segreto del client deve essere letto in un campo SecretStr"
    assert CANARY_SECRET not in repr(settings)
    assert CANARY_SECRET not in str(settings)
    assert CANARY_SECRET not in settings.model_dump_json()


def test_startup_makes_no_network_request(app_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """La discovery è pigra: avviare l'app (anche con l'emittente di Google) non esce in rete."""
    import socket

    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("richiesta di rete all'avvio")

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setenv("OIDC_ISSUER", GOOGLE_ISSUER)
    _start()
