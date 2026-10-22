"""Guardia ad allow-list del comando `seed` (A-22, THR-133, SR-029).

Si parte solo con `APP_ENV` esattamente `dev` o `staging`, `SEED_TARGET` esplicito `local` o
`staging` e host del database presente per intero in `SEED_ALLOWED_DB_HOSTS`. Non apre mai
connessioni e i messaggi non contengono l'URL (contiene la password).
"""

from urllib.parse import parse_qsl, urlsplit

ALLOWED_APP_ENVS = frozenset({"dev", "staging"})
ALLOWED_TARGETS = frozenset({"local", "staging"})
# Parametri di libpq che sostituiscono l'host dell'URL (l'allow-list vedrebbe un altro host).
_HOST_OVERRIDES = frozenset({"host", "hostaddr", "service"})


class SeedNotAllowed(Exception):  # noqa: N818 - nome del contratto
    """Il seed è rifiutato; il messaggio dice il motivo, mai valori sensibili."""


def _database_host(database_url: str | None) -> str | None:
    if not database_url:
        return None
    try:
        parts = urlsplit(database_url)
        host = parts.hostname
        overrides = {k.lower() for k, _ in parse_qsl(parts.query, keep_blank_values=True)}
    except ValueError:
        return None
    if overrides & _HOST_OVERRIDES:
        raise SeedNotAllowed("l'URL non deve sostituire l'host nei parametri")
    return host.lower() if host else None


def assert_seed_allowed(
    *,
    app_env: str | None,
    database_url: str | None,
    seed_target: str | None,
    allowed_hosts: str | None,
) -> None:
    if app_env not in ALLOWED_APP_ENVS:
        raise SeedNotAllowed("APP_ENV deve essere esattamente dev o staging")
    if seed_target not in ALLOWED_TARGETS:
        raise SeedNotAllowed("SEED_TARGET deve essere esplicitamente local o staging")
    host = _database_host(database_url)
    if host is None:
        raise SeedNotAllowed("host del database non determinabile")
    allowed = {h.strip().lower() for h in (allowed_hosts or "").split(",") if h.strip()}
    if host not in allowed:
        raise SeedNotAllowed("host del database fuori da SEED_ALLOWED_DB_HOSTS")
