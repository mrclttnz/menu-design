"""La tabella dei permessi: operazione -> ruoli ammessi (06-requisiti «Ruoli e permessi»).

Il Membro è in sola lettura sui piatti fino a SL-17: allora create e update passeranno a una
regola `member_own_to_try` (piano §4.3) e questa tabella cambierà insieme ai test.
"""

from typing import Any, Literal

Role = Literal["admin", "planner", "member"]

ADMIN_PLANNER: frozenset[Role] = frozenset({"admin", "planner"})
EVERYONE: frozenset[Role] = frozenset({"admin", "planner", "member"})
_ROLE_ORDER: tuple[Role, ...] = ("admin", "planner", "member")

OPERATIONS: dict[str, frozenset[Role]] = {
    "catalog.course.list": EVERYONE,
    "catalog.dish.list": EVERYONE,
    "catalog.dish.read": EVERYONE,
    "catalog.dish.create": ADMIN_PLANNER,
    "catalog.dish.update": ADMIN_PLANNER,
    "catalog.dish.set_status": ADMIN_PLANNER,
    # Operazioni future dell'archivio (SL-08): la regola c'è prima della rotta.
    "catalog.dish.archive": ADMIN_PLANNER,
    "catalog.dish.restore": ADMIN_PLANNER,
}


# Unità tracciate dalle scritture che registrano un evento di modifica (`x-authz.tracks`, ADR-0012):
# l'inventario in pytest confronta questa tabella con i test marcati `tracks`.
TRACKS: dict[str, tuple[str, ...]] = {
    "catalog.dish.set_status": ("dish",),
}


def family_authz(operation: str) -> dict[str, Any]:
    """`x-authz` di una rotta di famiglia, ricavato dalla riga della matrice (KeyError se manca)."""
    allowed = OPERATIONS[operation]
    authz: dict[str, Any] = {"scope": "family", "roles": [r for r in _ROLE_ORDER if r in allowed]}
    if operation in TRACKS:
        authz["tracks"] = list(TRACKS[operation])
    return authz
