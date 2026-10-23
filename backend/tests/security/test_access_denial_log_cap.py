"""Tetto agli eventi di rifiuto (SEC-SL04-001, CWE-779): niente flood del registro di sicurezza.

Per account e ora al massimo 20 eventi, poi uno solo `suppressed`; le risposte `403`/`404` non
cambiano; l'allarme SR-058 (> 10 all'ora) resta rilevabile; se il contatore fallisce la risposta
resta `404`, mai `500`.
"""

import json
from collections.abc import Callable
from uuid import uuid4

import pytest

from menu.access import rules
from support.accounts import security_events
from support.dishes import Actor, Who, World, payload
from support.owner import Owner

pytestmark = [pytest.mark.sec, pytest.mark.integration]
Login = Callable[[Who], Actor]
CAP = rules.DENIAL_LOG_LIMIT


def _mine(owner: Owner, actor: Actor, like: str) -> list[dict[str, object]]:
    return [e for e in security_events(owner, like) if e["actor_account_id"] == actor.who.account]


def test_100_random_id_reads_write_at_most_cap_plus_one_events(
    world: World, login: Login, owner: Owner
) -> None:
    actor = login(world.alfa.who("member"))
    codes = {actor.get(f"/api/v1/dishes/{uuid4()}").status_code for _ in range(100)}
    assert codes == {404}
    events = _mine(owner, actor, "access.cross_family")
    assert len(events) == CAP + 1
    assert all("suppressed" not in str(e["details"]) for e in events[:CAP])
    assert json.loads(str(events[CAP]["details"])) == {
        "operation": "catalog.dish.read",
        "suppressed": True,
    }


def test_the_sr_058_threshold_stays_detectable(world: World, login: Login, owner: Owner) -> None:
    assert CAP > 10
    actor = login(world.alfa.who("planner"))
    for _ in range(12):
        actor.get(f"/api/v1/dishes/{uuid4()}")
    assert len(_mine(owner, actor, "access.cross_family")) == 12


def test_50_member_creates_write_at_most_cap_plus_one_denied_events(
    world: World, login: Login, owner: Owner
) -> None:
    actor = login(world.alfa.who("member"))
    codes = {actor.post("/api/v1/dishes", payload(world.alfa)).status_code for _ in range(50)}
    assert codes == {403}
    events = _mine(owner, actor, "access.denied")
    assert len(events) == CAP + 1
    assert json.loads(str(events[CAP]["details"]))["suppressed"] is True


def test_the_cap_is_per_account_one_flooder_does_not_silence_another(
    world: World, login: Login, owner: Owner
) -> None:
    flooder = login(world.alfa.who("member"))
    other = login(world.beta.who("member"))
    for _ in range(CAP + 5):
        flooder.get(f"/api/v1/dishes/{uuid4()}")
    other.get(f"/api/v1/dishes/{uuid4()}")
    assert len(_mine(owner, other, "access.cross_family")) == 1


def test_a_counter_failure_keeps_the_404_and_never_returns_500(
    world: World, login: Login, owner: Owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object) -> None:
        raise RuntimeError("database giù")

    monkeypatch.setattr(rules, "bump", broken)
    actor = login(world.alfa.who("member"))
    response = actor.get(f"/api/v1/dishes/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert _mine(owner, actor, "access.cross_family") == []
