"""Nessun contenuto dei piatti nei log né nel registro di sicurezza (SR-021, SR-047, SR-057).

Si percorrono scritture riuscite, rifiutate (422, 403, 412, 428) e accessi altrui (404 con evento)
con nomi, note e URL CANARINO, e si cerca ogni valore in stdout, stderr, log catturati e nelle
righe di `security_event`. Il contenuto del piatto compare solo nelle risposte al suo autore.
"""

from collections.abc import Callable

import pytest

from support.dishes import Actor, Who, World, link, make_dish, payload
from support.owner import Owner

pytestmark = [pytest.mark.sec, pytest.mark.integration]
Login = Callable[[Who], Actor]

NAME = "CANARY-NAME-8f3a1"
NOTE = "CANARY-NOTE-5c2d9"
URL = "https://canary-url-77be.example.test/ricetta"
QUERY = "CANARY-QUERY-91ac"


def test_dish_content_never_reaches_logs_security_events_or_error_bodies(
    world: World,
    login: Login,
    owner: Owner,
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    planner = login(world.alfa.who("planner"))
    member = login(world.alfa.who("member"))
    beta = login(world.beta.who("planner"))
    created = planner.post(
        "/api/v1/dishes", payload(world.alfa, NAME, notes=NOTE, sources=[link(URL)])
    )
    assert created.status_code == 201
    dish = created.json()["id"]
    foreign_dish = make_dish(owner, world.beta, "CANARY-BETA-DISH-9", notes="CANARY-BETA-NOTE")

    bodies = [
        # rifiuti con il canarino nel corpo della richiesta: la risposta non lo riflette
        planner.post("/api/v1/dishes", payload(world.alfa, "", notes=NOTE, courseIds=[])).text,
        planner.post(
            "/api/v1/dishes", payload(world.alfa, NAME, sources=[link("javascript:" + NAME)])
        ).text,
        planner.post("/api/v1/dishes", payload(world.alfa, NAME) | {NAME: 1}).text,
        planner.put(f"/api/v1/dishes/{dish}", payload(world.alfa, NAME, notes=NOTE)).text,  # 428
        planner.put(
            f"/api/v1/dishes/{dish}", payload(world.alfa, NAME, notes=NOTE), if_match=9
        ).text,  # 412
        planner.put(
            f"/api/v1/dishes/{dish}", payload(world.alfa, NAME, notes=NOTE), if_match="abc"
        ).text,  # 422
        member.post("/api/v1/dishes", payload(world.alfa, NAME, notes=NOTE)).text,  # 403
        member.put(f"/api/v1/dishes/{dish}", payload(world.alfa, NAME), if_match=1).text,  # 403
        beta.get(f"/api/v1/dishes/{dish}").text,  # 404 con evento
        beta.put(f"/api/v1/dishes/{dish}", payload(world.beta, NAME, notes=NOTE), if_match=1).text,
        planner.get(f"/api/v1/dishes/{foreign_dish}").text,
        planner.get(f"/api/v1/dishes?q={QUERY}").text,
        planner.get(f"/api/v1/dishes?q={QUERY}&status=zzz").text,
    ]
    # Il 412 (indice 4) riporta lo stato attuale al suo autore (ADR-0008): è l'unica eccezione.
    for index, body in enumerate(bodies):
        if index == 4:
            continue
        assert NAME not in body, f"risposta {index} riflette il nome"
        assert NOTE not in body, f"risposta {index} riflette le note"
        assert "canary-url" not in body, f"risposta {index}"
        assert "CANARY-BETA" not in body, f"risposta {index}"

    out = capfd.readouterr()
    logged = out.out + out.err + caplog.text
    assert "security_event" in logged, "gli eventi di accesso negato sono registrati anche nei log"
    registry = str(owner.rows("select t::text from app.security_event t"))
    for secret in (NAME, NOTE, "canary-url-77be", QUERY, "CANARY-BETA-NOTE", "CANARY-BETA-DISH-9"):
        assert secret not in logged, f"{secret} nei log"
        assert secret not in registry, f"{secret} nel registro di sicurezza"
