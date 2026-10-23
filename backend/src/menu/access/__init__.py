"""Modulo access (strato 4): la matrice dichiarativa dei permessi e `authorize` (SR-009, THR-023).

Una riga per operazione (`area.risorsa.azione`), anche per quelle di slice future: la regola per
Amministratore, Pianificatore e Membro esiste prima della rotta. Il default è il rifiuto:
un'operazione sconosciuta o un contesto senza ruolo non passano mai. Le rotte derivano il proprio
`x-authz` dalla stessa tabella (`family_authz`), quindi la dichiarazione e il controllo non possono
divergere. I fatti sulla risorsa (`facts`: «proprio», «da provare», «mai pianificato») servono
alle regole condizionate del Membro (`member_own_to_try`, SL-17); oggi nessuna riga li usa.
"""

from menu.access.matrix import OPERATIONS, family_authz
from menu.access.rules import authorize, configure_denial_cap, cross_family

__all__ = ["OPERATIONS", "authorize", "configure_denial_cap", "cross_family", "family_authz"]
