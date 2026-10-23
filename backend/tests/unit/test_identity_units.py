"""Logica di `identity` che non richiede il database (SL-03a): token, allow-list, etichette, OIDC.

Complementa i test di accettazione: qui i casi limite delle funzioni pure e il comportamento del
client OIDC contro il provider finto servito da `httpx.MockTransport` (nessuna rete).
"""

import time
from typing import Any

import httpx
import pytest

from menu.identity.accounts import clean_display_name, valid_email
from menu.identity.labels import device_label
from menu.identity.login import sanitize_return_to
from menu.identity.oidc import OidcClient, OidcError
from menu.identity.tokens import (
    constant_time_equal,
    csrf_token_for,
    digest,
    new_code_verifier,
    new_secret,
    well_formed,
)
from support.fake_oidc import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, FakeOidc, TokenOptions

NONCE = "nonce-for-the-unit-tests-0123456789"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/piano", "/piano"),
        ("/piano/", "/piano/"),
        ("/piano/2026-10-19/cena", "/piano/2026-10-19/cena"),
        ("/piatti?q=zuppa&p=2", "/piatti?q=zuppa&p=2"),
        ("/pianoX", None),
        ("/piano/../altro", None),
        ("/piano//evil", None),
        ("/piano?x=%0d", None),
        ("/piano\n", None),
        ("/piano" + "a" * 200, None),
        (None, None),
        ("", None),
    ],
)
def test_return_to_allow_list(value: str | None, expected: str | None) -> None:
    assert sanitize_return_to(value) == expected


@pytest.mark.parametrize(
    ("agent", "label"),
    [
        (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36",
            "Chrome · Android",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
            "Firefox · Linux",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit Safari/604.1",
            "Safari · iOS",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/130 Safari/537 Edg/130",
            "Edge · Windows",
        ),
        ("curl/8.5.0", None),
        ("", None),
        (None, None),
    ],
)
def test_device_label_never_keeps_the_user_agent(agent: str | None, label: str | None) -> None:
    result = device_label(agent)
    assert result == label
    assert result is None or "Mozilla" not in result


def test_device_label_is_bounded_for_hostile_input() -> None:
    result = device_label("Chrome/1 Android " + "x" * 100_000)
    assert result == "Chrome · Android"


@pytest.mark.parametrize(
    ("name", "email", "expected"),
    [
        ("Alice Alfa", "a@example.test", "Alice Alfa"),
        ("  Alice  ", "a@example.test", "Alice"),
        ("N" * 100, "a@example.test", "N" * 60),
        ("Zoë 🍝", "a@example.test", "Zoë 🍝"),
        ("‮\u0000Bob\n", "a@example.test", "Bob"),
        ("   ", "mario.rossi@example.test", "mario.rossi"),
        (None, "mario@example.test", "mario"),
        (42, "mario@example.test", "mario"),
        ("", "@x", "Utente"),
    ],
)
def test_display_name_always_satisfies_the_column_check(
    name: object, email: str, expected: str
) -> None:
    cleaned = clean_display_name(name, email)
    assert cleaned == expected
    assert 1 <= len(cleaned) <= 60
    assert cleaned.strip() == cleaned


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("a@b.test", True),
        ("  a@b.test ", True),
        ("a@b@c.test", False),
        ("a b@c.test", False),
        ("a@b\n.test", False),
        ("@b.test", False),
        ("x" * 250 + "@b.test", False),
        (None, False),
        (12, False),
    ],
)
def test_email_matches_the_account_check(value: object, valid: bool) -> None:
    assert (valid_email(value) is not None) is valid


def test_secrets_are_long_unique_and_well_formed() -> None:
    values = {new_secret() for _ in range(50)}
    assert len(values) == 50
    assert all(len(v) == 43 and well_formed(v) for v in values)
    verifier = new_code_verifier()
    assert 43 <= len(verifier) <= 128
    assert not well_formed("short")
    assert not well_formed("a b" * 20)
    assert not well_formed(None)


def test_csrf_token_is_stable_per_session_and_distinct_from_the_session_token() -> None:
    token = new_secret()
    first = csrf_token_for(token)
    assert first == csrf_token_for(token)
    assert first != token
    assert first != csrf_token_for(new_secret())
    assert len(digest(first)) == 32
    assert constant_time_equal(first, first)
    assert not constant_time_equal(first, "x")
    assert not constant_time_equal("è", "e")  # confronto sui byte: nessuna eccezione sul non-ASCII


def _client(oidc: FakeOidc) -> OidcClient:
    return OidcClient(
        issuer=oidc.issuer,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        http=httpx.Client(transport=oidc.transport()),
    )


def _token(oidc: FakeOidc, options: TokenOptions | None = None, **claims: Any) -> str:
    now = int(time.time())
    base: dict[str, Any] = {
        "iss": oidc.issuer,
        "aud": CLIENT_ID,
        "azp": CLIENT_ID,
        "sub": "sub-unit",
        "email": "unit@example.test",
        "email_verified": True,
        "nonce": NONCE,
        "iat": now,
        "exp": now + 600,
        "name": "Unit Test",
    }
    base.update(claims)
    return oidc.encode(base, options)


@pytest.fixture
def oidc() -> FakeOidc:
    return FakeOidc()


def test_a_valid_token_yields_the_identity_and_never_prints_it(oidc: FakeOidc) -> None:
    who = _client(oidc).verify_id_token(_token(oidc), digest(NONCE))
    assert (who.subject, who.email, who.display_name) == (
        "sub-unit",
        "unit@example.test",
        "Unit Test",
    )
    assert "sub-unit" not in repr(who)
    assert "unit@example.test" not in repr(who)


def test_a_wrong_nonce_audience_list_or_azp_is_refused(oidc: FakeOidc) -> None:
    client = _client(oidc)
    refused = [
        _token(oidc, nonce="other"),
        _token(oidc, aud=["other.example.test"]),
        _token(oidc, aud=[CLIENT_ID, "other.example.test"], azp="other.example.test"),
        _token(oidc, aud=[CLIENT_ID, "other.example.test"], azp=None),
    ]
    for token in refused:
        with pytest.raises(OidcError):
            client.verify_id_token(token, digest(NONCE))
    ok = _token(oidc, aud=[CLIENT_ID, "other.example.test"])
    assert client.verify_id_token(ok, digest(NONCE)).subject == "sub-unit"


def test_a_token_without_kid_or_garbage_is_refused(oidc: FakeOidc) -> None:
    from support.fake_oidc import OMIT

    client = _client(oidc)
    for token in (_token(oidc, TokenOptions(kid=OMIT)), "x.y.z", "", "a.b", "....."):
        with pytest.raises(OidcError):
            client.verify_id_token(token, digest(NONCE))


def test_unknown_kid_refreshes_the_keys_at_most_once_per_interval(oidc: FakeOidc) -> None:
    client = _client(oidc)
    client.verify_id_token(_token(oidc), digest(NONCE))
    assert oidc.calls("/jwks") == 1
    for attempt in range(5):
        with pytest.raises(OidcError):
            client.verify_id_token(_token(oidc, TokenOptions(kid=f"nope-{attempt}")), digest(NONCE))
    assert oidc.calls("/jwks") == 2


def test_discovery_with_a_different_issuer_is_refused(oidc: FakeOidc) -> None:
    other = FakeOidc(issuer="https://other.example.test")
    client = OidcClient(
        issuer=oidc.issuer,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        http=httpx.Client(transport=other.transport()),
    )
    with pytest.raises(OidcError):
        client.authorization_url(state="s" * 43, nonce="n" * 43, code_verifier="v" * 64)


def test_authorization_url_requires_a_configured_client(oidc: FakeOidc) -> None:
    client = OidcClient(
        issuer=oidc.issuer,
        client_id=None,
        client_secret=None,
        redirect_uri=REDIRECT_URI,
        http=httpx.Client(transport=oidc.transport()),
    )
    with pytest.raises(OidcError):
        client.authorization_url(state="s" * 43, nonce="n" * 43, code_verifier="v" * 64)
