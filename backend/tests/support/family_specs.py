"""Come popolare e scrivere ogni tabella di famiglia nel test RLS generico (08 §6.4).

Una voce per tabella con `family_id` (e per `family`): ogni slice che crea una tabella di
famiglia aggiunge qui la sua. In SL-00b non esistono tabelle di famiglia.
"""

from support.inventory import FamilyTableSpec

FAMILY_TABLE_SPECS: dict[str, FamilyTableSpec] = {}
