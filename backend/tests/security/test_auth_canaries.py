"""Nessun segreto di accesso nei log, nelle risposte d'errore né nel registro di sicurezza.

SR-021 (i log non contengono segreti, token, codici, email), SR-051 (IP troncato), SR-020 (gli
eventi di accesso ci sono, strutturati), CWE-532, THR-005, THR-110. ADR-0004 rev. 3 punto 3:
«l'email mascherata non compare mai in un URL, né nei log di accesso».

Si percorrono tutti gli esiti (accesso riuscito, senza famiglia, annullato, token manipolato,
logout) e si cerca in stdout, stderr e log catturati ogni valore segreto o personale visto.
"""

import pytest

from support.accounts import AlfaWorld, make_bootstrap, make_family, security_events
from support.browser_sim import CSRF, FLOW, SESSION, Browser
from support.fake_oidc import FakeOidc, Identity
from support.owner import Owner

pytestmark = [pytest.mark.sec, pytest.mark.integration]

BOOT_EMAIL = "gestore.canary@example.test"


def test_no_secret_or_personal_value_reaches_logs_responses_or_the_security_log(
    browser: Browser,
    other_browser: Browser,
    oidc: FakeOidc,
    alfa: AlfaWorld,
    owner: Owner,
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    make_bootstrap(owner, make_family(owner, "Famiglia Gamma"), BOOT_EMAIL)
    secrets: set[str] = set()
    texts: list[str] = []

    # 1. accesso riuscito con ritorno al callback
    started = browser.start_login("/piatti")
    secrets.add(browser.cookies[FLOW])
    grant = oidc.authorize(started.json()["redirectUrl"], alfa.admin)
    secrets |= {grant.state, grant.params["nonce"], grant.code or ""}
    callback = browser.get(grant.callback_path)
    texts += [started.text, callback.text, str(callback.headers)]
    secrets.add(browser.cookies[SESSION])
    secrets.add(browser.cookies[CSRF])
    view = browser.session()
    secrets.add(view.json()["csrfToken"])
    texts.append(view.text)

    # 2. senza famiglia, annullato, token manipolato
    for index, action in enumerate(("not_member", "cancelled", "forged")):
        other = Browser(browser.client)
        started = other.start_login()
        secrets.add(other.cookies[FLOW])
        url = started.json()["redirectUrl"]
        if action == "cancelled":
            grant = oidc.deny(url)
        else:
            who = (
                alfa.outsider
                if action == "not_member"
                else Identity(sub=f"sub-forged-{index}", email=BOOT_EMAIL, email_verified=False)
            )
            grant = oidc.authorize(url, who)
        secrets |= {grant.state, grant.params["nonce"], grant.code or ""}
        result = other.get(grant.callback_path)
        outcome = other.session()
        texts += [result.text, outcome.text]

    # 3. logout
    texts.append(browser.logout().text)

    out = capfd.readouterr()
    logged = out.out + out.err + caplog.text
    assert "security_event" in logged, "gli eventi di accesso vengono registrati anche come log"
    secrets |= set(oidc.issued) | {oidc.client_secret}
    secrets.discard("")
    personal = {
        alfa.admin.email,
        alfa.admin.sub,
        alfa.outsider.email,
        alfa.outsider.sub,
        BOOT_EMAIL,
        "Alice Alfa",
        "Orfeo Orfano",
    }
    for value in sorted(secrets | personal):
        assert value, "valore vuoto nella lista dei segreti"
        assert value not in logged, f"valore sensibile nei log: {value[:12]}…"

    # Le risposte d'errore e gli esiti non riportano segreti altrui né identità.
    blob = "\n".join(texts)
    for value in (
        oidc.client_secret,
        *oidc.issued,
        alfa.outsider.email,
        alfa.outsider.sub,
        BOOT_EMAIL,
    ):
        assert value not in blob

    # Il registro di sicurezza: solo codici e identificativi (SR-021).
    dump = str(security_events(owner))
    for value in (*secrets, *personal):
        assert value not in dump, f"valore sensibile nel registro di sicurezza: {value[:12]}…"
    kinds = {(e["event_type"], e["outcome"]) for e in security_events(owner, "auth.%")}
    assert ("auth.login", "success") in kinds
    assert ("auth.login", "failure") in kinds
    assert ("auth.logout", "success") in kinds
