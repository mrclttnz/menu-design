"""Validazione del testo libero dell'archivio: lunghezze e caratteri prima del database."""

from urllib.parse import urlsplit

from pydantic_core import PydanticCustomError


def check_storable(value: str) -> str:
    """PostgreSQL rifiuta NUL e il driver non codifica i surrogati isolati: 422, mai 500."""
    if "\x00" in value:
        raise PydanticCustomError("invalid_value", "carattere non ammesso")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise PydanticCustomError("invalid_value", "carattere non ammesso") from error
    return value


def check_required(value: str) -> str:
    if not value:
        raise PydanticCustomError("value_required", "valore obbligatorio")
    return value


def is_http_url(value: str) -> bool:
    """URL assoluto `http`/`https` con host, senza credenziali né spazi (SR-024, AC-004.4)."""
    if any(c.isspace() or ord(c) < 0x20 for c in value):
        return False
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(host) and "@" not in parts.netloc
