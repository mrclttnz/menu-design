"""Richieste e risposte di `identity` (piano §4.2, §4.3): chiavi `camelCase`, corpi chiusi."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ClosedBody(BaseModel):
    """Corpo di una richiesta: campi sconosciuti rifiutati (`unknown_field`), SR-010."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel)


class StartRequest(ClosedBody):
    purpose: Literal["login", "reauth"]
    return_to: str | None = None


class StartResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    redirect_url: str


class LogoutRequest(ClosedBody):
    """Corpo `{}`."""
