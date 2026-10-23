"""Configurazione fail-closed: l'avvio è rifiutato se manca `APP_ENV` o un valore non è valido.

`APP_ENV` non attiva né disattiva alcun controllo di sicurezza (piano §6.4, A-25, THR-134).
`DATABASE_URL_APP` deve avere `sslmode=verify-full` in ogni ambiente (A-13, THR-043); l'URL
contiene la password: resta un `SecretStr` e non compare in errori, repr o log (CWE-532).
"""

from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["dev", "test", "staging", "production"]

_DB_SCHEMES = frozenset({"postgresql", "postgresql+psycopg"})
GOOGLE_ISSUER = "https://accounts.google.com"
_STRICT_ENVS = frozenset({"staging", "production"})


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


def _origin(value: str) -> str | None:
    """`scheme://host[:porta]` di un URL http(s) senza percorso, query, frammento né credenziali."""
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        return None
    if parts.path not in {"", "/"} or parts.query or parts.fragment or "\\" in value:
        return None
    host = parts.hostname
    host = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{host}" + (f":{port}" if port is not None else "")


def _issuer_problem(env: str, issuer: str) -> str | None:
    if env in _STRICT_ENVS:
        if issuer != GOOGLE_ISSUER:
            return f"OIDC_ISSUER deve essere {GOOGLE_ISSUER} in {env}"
        return None
    if _origin(issuer) is None:
        return "OIDC_ISSUER deve essere un URL http(s) senza percorso"
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", frozen=True, hide_input_in_errors=True
    )

    app_env: AppEnv
    trusted_proxy_hops: int = Field(default=0, ge=0, le=10)
    database_url_app: SecretStr
    web_dist_dir: Path | None = None
    # Accesso con Google (SL-03a, ASM-073). L'emittente è Google in `staging` e `production`;
    # solo `dev` e `test` ammettono il provider finto. Nessuna richiesta di rete all'avvio.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    oidc_issuer: str = GOOGLE_ISSUER
    app_base_url: str = "http://localhost:8000"

    @field_validator("database_url_app")
    @classmethod
    def _verify_full_only(cls, value: SecretStr) -> SecretStr:
        check_database_url(value.get_secret_value())
        return value

    @field_validator("web_dist_dir", mode="before")
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("web_dist_dir")
    @classmethod
    def _dist_has_index(cls, value: Path | None) -> Path | None:
        if value is not None and not (value.is_dir() and (value / "index.html").is_file()):
            raise ValueError("WEB_DIST_DIR deve essere una cartella con index.html")
        return value

    @field_validator("google_client_id", "google_client_secret", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def _login_configuration(self) -> Settings:
        problems: list[str] = []
        strict = self.app_env in _STRICT_ENVS
        if strict and self.google_client_id is None:
            problems.append("GOOGLE_CLIENT_ID è obbligatorio")
        if strict and self.google_client_secret is None:
            problems.append("GOOGLE_CLIENT_SECRET è obbligatorio")
        issuer_problem = _issuer_problem(self.app_env, self.oidc_issuer)
        if issuer_problem:
            problems.append(issuer_problem)
        origin = _origin(self.app_base_url)
        if origin is None:
            problems.append("APP_BASE_URL deve essere un URL http(s) senza percorso")
        elif strict and not origin.startswith("https://"):
            problems.append(f"APP_BASE_URL deve usare https in {self.app_env}")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def app_origin(self) -> str:
        """Origine pubblica dell'app (controllo di `Origin`, URI di ritorno registrato)."""
        origin = _origin(self.app_base_url)
        if origin is None:
            raise ValueError("APP_BASE_URL non valido")
        return origin

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.app_origin}/api/v1/auth/google/callback"
