"""Eventi di sicurezza dell'accesso ai dati (SL-04; SR-020, SR-057, THR-020, THR-023).

`access.denied` (permesso mancante) e `access.cross_family` (risorsa di un'altra famiglia) entrano
nel catalogo di `menu.audit`; il formato `dominio.azione` è imposto anche dal CHECK del database.
"""

import re

from menu.audit import EVENT_TYPES, EventType

FORMAT = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def test_access_events_are_in_the_catalog() -> None:
    assert {"access.denied", "access.cross_family"} <= EVENT_TYPES


def test_the_enum_names_the_access_events() -> None:
    values = {e.value for e in EventType}
    assert {"access.denied", "access.cross_family"} <= values


def test_every_event_type_has_the_domain_action_format() -> None:
    assert all(FORMAT.match(e) for e in EVENT_TYPES)
