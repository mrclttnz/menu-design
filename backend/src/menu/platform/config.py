"""Configurazione fail-closed: l'avvio è rifiutato se manca `APP_ENV` o un valore non è valido.

`APP_ENV` non attiva né disattiva alcun controllo di sicurezza (piano §6.4, A-25, THR-134).
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["dev", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    app_env: AppEnv
    trusted_proxy_hops: int = Field(default=0, ge=0, le=10)
