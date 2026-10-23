"""Regole dichiarative dei limiti di frequenza (SR-059, SR-070): una riga per regola.

Finestra fissa allineata all'orologio del database (`app.now_utc()`): il contatore riparte
alla finestra successiva e `Retry-After` è l'attesa fino alla sua fine (al massimo 15 minuti).
Il nome della regola entra nella chiave HMAC: lo stesso identificativo in due regole non
condivide il contatore.
"""

from dataclasses import dataclass

MAX_WINDOW_SECONDS = 900


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window_seconds: int


# SR-059: avvio dell'accesso, 30 per IP in 15 minuti (AC-001.9, THR-011).
OIDC_START = Rule("oidc_start_ip", limit=30, window_seconds=900)
# SR-059: API autenticata, 300 richieste al minuto per sessione, di cui al massimo 60 scritture.
API_SESSION = Rule("api_session", limit=300, window_seconds=60)
WRITE_SESSION = Rule("write_session", limit=60, window_seconds=60)
# SR-070: 60 scritture al minuto per account, sommando le sue sessioni (THR-013).
WRITE_ACCOUNT = Rule("write_account", limit=60, window_seconds=60)

API_PREFIX = "/api/v1/"
# Rotte anonime limitate per IP, per (metodo, percorso). `/healthz` e la SPA restano fuori.
ROUTE_RULES: dict[tuple[str, str], tuple[Rule, ...]] = {
    ("POST", "/api/v1/auth/google/start"): (OIDC_START,),
}

# Rotte di uscita: contano nei 300/min della sessione ma mai nelle scritture (SEC-SL03b-002),
# così chi ha saturato le scritture dell'account può sempre chiudere la propria sessione.
WRITE_EXEMPT: frozenset[tuple[str, str]] = frozenset({("POST", "/api/v1/auth/logout")})
