"""Al massimo 20 sessioni attive per account (SL-03b; US-047 AC-047.4, SR-070, THR-013, THR-100).

AC-047.4: «Dato un account con 20 sessioni attive, quando fa un nuovo login, allora la sessione
usata meno di recente viene revocata e la nuova è valida». Vale da M0 (l'elenco delle sessioni
arriva in M1 con SL-25). L'evento di sicurezza è `session.evicted` (SR-020).
"""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from support.accounts import AlfaWorld, count, security_events, sessions
from support.browser_sim import Browser
from support.fake_oidc import FakeOidc, Identity
from support.owner import Owner
from support.ratelimit import insert_session, live_sessions, set_last_used

pytestmark = pytest.mark.integration

CAP = 20


def _session_ids(owner: Owner, account: UUID) -> set[UUID]:
    return {row[0] for row in sessions(owner, account)}


def _login_many(client: TestClient, oidc: FakeOidc, identity: Identity, n: int) -> list[Browser]:
    out = []
    for _ in range(n):
        browser = Browser(client)
        assert browser.login(oidc, identity).status_code == 302
        out.append(browser)
    return out


def test_ac_047_4_the_21st_login_revokes_the_least_recently_used_session(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    browsers = _login_many(auth_client, oidc, alfa.admin, CAP)
    assert len(sessions(owner, alfa.admin_account)) == CAP
    # La meno usata NON è la più vecchia per creazione: la #7 non è usata da 10 giorni, la #0
    # (la più vecchia) è stata usata di recente. Contano gli usi (AC-047.4), non la nascita.
    ordered = [row[0] for row in sessions(owner, alfa.admin_account)]
    for index, session in enumerate(ordered):
        set_last_used(owner, session, days_ago=1 + index * 0.1)
    set_last_used(owner, ordered[7], days_ago=10)
    set_last_used(owner, ordered[0], days_ago=0.01)

    newest = Browser(auth_client)
    assert newest.login(oidc, alfa.admin).status_code == 302

    remaining = _session_ids(owner, alfa.admin_account)
    assert len(remaining) == CAP, "mai più di 20 sessioni"
    assert ordered[7] not in remaining, "la meno usata è revocata"
    assert ordered[0] in remaining
    assert newest.session().json()["authenticated"] is True, "la nuova sessione è valida"
    by_session = {ordered[i]: browsers[i] for i in range(CAP)}
    assert by_session[ordered[7]].session().json()["authenticated"] is False
    for kept in (ordered[0], ordered[1], ordered[19]):
        assert by_session[kept].session().json()["authenticated"] is True


def test_the_eviction_is_logged_as_session_evicted_with_the_revoked_session(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    ids = [insert_session(owner, alfa.admin_account, used_days_ago=1 + i) for i in range(CAP)]
    oldest = ids[-1]  # l'ultimo inserito è anche il meno usato (20 giorni fa)
    assert not security_events(owner, "session.%")
    Browser(auth_client).login(oidc, alfa.admin)
    (event,) = security_events(owner, "session.evicted")
    assert event["outcome"] == "success"
    assert event["actor_account_id"] == alfa.admin_account
    assert event["target_type"] == "session"
    assert event["target_id"] == oldest
    assert oldest not in _session_ids(owner, alfa.admin_account)
    # Il login resta tracciato come sempre.
    assert [e["event_type"] for e in security_events(owner, "auth.login")] == ["auth.login"]


def test_the_cap_is_per_account_other_accounts_keep_their_sessions(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    mine = [insert_session(owner, alfa.admin_account, used_days_ago=1 + i) for i in range(CAP)]
    theirs = [insert_session(owner, alfa.member_account, used_days_ago=25) for _ in range(3)]
    Browser(auth_client).login(oidc, alfa.admin)
    assert _session_ids(owner, alfa.member_account) == set(theirs), "Mario non è toccato"
    assert mine[-1] not in _session_ids(owner, alfa.admin_account)


def test_below_the_cap_no_session_is_revoked_and_no_event_is_written(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    ids = {insert_session(owner, alfa.admin_account) for _ in range(CAP - 1)}
    Browser(auth_client).login(oidc, alfa.admin)
    assert len(_session_ids(owner, alfa.admin_account)) == CAP
    assert ids <= _session_ids(owner, alfa.admin_account)
    assert security_events(owner, "session.evicted") == []


def test_expired_sessions_do_not_count_towards_the_cap(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """«20 sessioni ATTIVE»: quelle scadute (31 giorni di inattività) non fanno posto a nessuno."""
    active = {insert_session(owner, alfa.admin_account, used_days_ago=2) for _ in range(CAP - 1)}
    for _ in range(6):
        insert_session(owner, alfa.admin_account, used_days_ago=31, created_days_ago=40)
    Browser(auth_client).login(oidc, alfa.admin)
    assert active <= set(live_sessions(owner, alfa.admin_account)), "nessuna sessione viva revocata"
    assert len(live_sessions(owner, alfa.admin_account)) == CAP
    assert security_events(owner, "session.evicted") == []


def test_logging_in_again_from_a_browser_that_has_a_session_does_not_evict_another(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """THR-006: il login rigenera la sessione del browser (la vecchia sparisce): a quota piena
    la sostituzione non deve costare la sessione di un altro dispositivo."""
    browsers = _login_many(auth_client, oidc, alfa.admin, CAP)
    before = _session_ids(owner, alfa.admin_account)
    assert len(before) == CAP
    assert browsers[5].login(oidc, alfa.admin).status_code == 302
    after = _session_ids(owner, alfa.admin_account)
    assert len(after) == CAP
    assert len(before - after) == 1, "è sparita solo la sessione sostituita"
    assert security_events(owner, "session.evicted") == []


def test_ten_extra_logins_keep_the_account_at_20_sessions(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """THR-013: login ripetuti non gonfiano la tabella `session`."""
    for _ in range(CAP):
        insert_session(owner, alfa.admin_account)
    for _ in range(10):
        assert Browser(auth_client).login(oidc, alfa.admin).status_code == 302
    assert count(owner, "session") == CAP
    assert len(security_events(owner, "session.evicted")) == 10


def test_the_evicted_session_is_gone_from_the_database_or_marked_revoked(
    auth_client: TestClient, oidc: FakeOidc, alfa: AlfaWorld, owner: Owner
) -> None:
    """Qualunque sia la forma della revoca, il cookie della sessione cacciata non vale più."""
    first = Browser(auth_client)
    first.login(oidc, alfa.admin)
    (mine,) = sessions(owner, alfa.admin_account)
    set_last_used(owner, mine[0], days_ago=29)  # la meno usata, ma ancora valida
    for _ in range(CAP - 1):
        insert_session(owner, alfa.admin_account, used_days_ago=1)
    Browser(auth_client).login(oidc, alfa.admin)
    assert first.session().json()["authenticated"] is False
