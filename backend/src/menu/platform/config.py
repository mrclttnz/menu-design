"""Configurazione fail-closed: l'avvio è rifiutato se manca `APP_ENV` o un valore non è valido.

`APP_ENV` non attiva né disattiva alcun controllo di sicurezza (piano §6.4, A-25, THR-134).
`DATABASE_URL_APP` deve avere `sslmode=verify-full` in ogni ambiente (A-13, THR-043); l'URL
contiene la password: resta un `SecretStr` e non compare in errori, repr o log (CWE-532).
"""

from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["dev", "test", "staging", "production"]

_DB_SCHEMES = frozenset({"postgresql", "postgresql+psycopg"})


def check_database_url(value: str) -> None:
    """Solleva `ValueError` (senza mai citare l'URL) se non è un URL PostgreSQL `verify-full`."""
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        modes = [v for k, v in parse_qsl(parts.query, keep_blank_values=True) if k == "sslmode"]
    except ValueError:
        raise ValueError("DATABASE_URL_APP non è un URL valido") from None
    if parts.scheme not in _DB_SCHEMES or not hostname:
        raise ValueError("DATABASE_URL_APP deve essere un URL postgresql o postgresql+psycopg")
    if modes != ["verify-full"]:
        raise ValueError("DATABASE_URL_APP richiede esattamente sslmode=verify-full")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", frozen=True, hide_input_in_errors=True
    )

    app_env: AppEnv
    trusted_proxy_hops: int = Field(default=0, ge=0, le=10)
    database_url_app: SecretStr

    @field_validator("database_url_app")
    @classmethod
    def _verify_full_only(cls, value: SecretStr) -> SecretStr:
        check_database_url(value.get_secret_value())
        return value
