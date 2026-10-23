"""Helper `assert_cross_family` (08 §6.2, SR-008, SR-041, THR-020, THR-021).

Quattro verifiche per una richiesta di Beta contro una risorsa di Alfa (e viceversa):
1. `404 not_found`, MAI `403`, e corpo identico a quello di un identificativo inesistente;
2. almeno un evento `access.cross_family` con attore, ruolo e famiglia dell'AGGRESSORE e nessun
   identificativo o valore della vittima nei campi liberi (`details`);
3. nessun valore canarino della vittima nella risposta;
4. lo stato della vittima non cambia (impronta delle righe prima e dopo).
"""

from collections.abc import Callable

from httpx import Response

from support.accounts import security_events
from support.dishes import Actor, Fam, family_state_hash
from support.owner import Owner


def assert_cross_family(
    *,
    owner: Owner,
    attacker: Actor,
    attacker_fam: Fam,
    victim: Fam,
    send_foreign: Callable[[], Response],
    send_missing: Callable[[], Response],
    victim_ids: tuple[str, ...] = (),
) -> Response:
    before_state = family_state_hash(owner, victim)
    before_events = len(security_events(owner, "access.cross_family"))

    foreign = send_foreign()
    after_events = security_events(owner, "access.cross_family")
    missing = send_missing()

    # 1. 404 (mai 403) e corpo indistinguibile da un identificativo inesistente
    assert foreign.status_code == 404, (foreign.status_code, foreign.text)
    assert foreign.json()["code"] == "not_found"
    assert foreign.json() == missing.json(), "il corpo rivela che la risorsa esiste altrove"
    assert missing.status_code == 404
    assert foreign.headers["content-type"] == missing.headers["content-type"]

    # 2. evento di sicurezza dell'aggressore, senza dati della vittima
    new = after_events[before_events:]
    assert new, "nessun evento access.cross_family (THR-020)"
    for event in new:
        assert event["actor_account_id"] == attacker.who.account
        assert event["actor_role"] == attacker.who.role
        assert event["family_id"] == attacker_fam.id, "la famiglia dell'evento è quella dell'attore"
        assert event["actor_kind"] == "account"
        free_text = f"{event['details']} {event['target_type']}"
        for forbidden in (str(victim.id), victim.canary, *victim_ids):
            assert forbidden not in free_text, "dato della vittima nei campi liberi"

    # 3. nessun canarino della vittima nella risposta
    assert victim.canary not in foreign.text
    assert str(victim.id) not in foreign.text

    # 4. nessuna scrittura sulla vittima
    assert family_state_hash(owner, victim) == before_state, "la richiesta ha modificato la vittima"
    return foreign
