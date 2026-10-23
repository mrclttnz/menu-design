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
    # Operazioni future dell'archivio (SL-05, SL-08): la regola c'è prima della rotta.
    "catalog.dish.set_status": ADMIN_PLANNER,
    "catalog.dish.archive": ADMIN_PLANNER,
    "catalog.dish.restore": ADMIN_PLANNER,
}


def family_authz(operation: str) -> dict[str, Any]:
    """`x-authz` di una rotta di famiglia, ricavato dalla riga della matrice (KeyError se manca)."""
    allowed = OPERATIONS[operation]
    return {"scope": "family", "roles": [r for r in _ROLE_ORDER if r in allowed]}
