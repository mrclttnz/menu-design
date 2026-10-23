"""Il provider OIDC finto sa fare ciò per cui lo usano i test di SL-03a (08 §4.2, §16).

Un double che non sa produrre un token valido e uno manipolato farebbe passare i test di
sicurezza per il motivo sbagliato: qui se ne prova il comportamento, con un verificatore
indipendente scritto in Python puro.
"""

import base64
import hashlib
import json
import secrets
import threading
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from support.fake_oidc import (
    CLIENT_ID,
    CLIENT_SECRET,
    FAKE_ISSUER,
    OMIT,
    REDIRECT_URI,
    FakeOidc,
    Identity,
    TokenOptions,
    b64u,
    decode_jwt,
    get_key,
    verify_with_published_keys,
)

VERIFIER = "v" * 64
CHALLENGE = b64u(hashlib.sha256(VERIFIER.encode()).digest())
ALICE = Identity(sub="sub-alice", email="alice.alfa@example.test")


def _authorize_url(oidc: FakeOidc, **override: str) -> str:
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email profile",
        "state": "state-1",
        "nonce": "nonce-1",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    } | override
    return oidc.authorization_endpoint + "?" + urlencode(params)


def _exchange(oidc: FakeOidc, code: str, **override: str) -> httpx.Response:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code_verifier": VERIFIER,
    } | override
    with httpx.Client(transport=oidc.transport()) as client:
        return client.post(oidc.token_endpoint, data=form)


def _id_token(oidc: FakeOidc, **kwargs: object) -> str:
    grant = oidc.authorize(_authorize_url(oidc), ALICE, **kwargs)  # type: ignore[arg-type]
    assert grant.code is not None
    response = _exchange(oidc, grant.code)
    assert response.status_code == 200, response.text
    return str(response.json()["id_token"])


def test_discovery_and_jwks_describe_the_issuer() -> None:
    oidc = FakeOidc()
    with httpx.Client(transport=oidc.transport()) as client:
        doc = client.get(oidc.discovery_url).json()
        keys = client.get(doc["jwks_uri"]).json()["keys"]
    assert doc["issuer"] == FAKE_ISSUER
    assert doc["id_token_signing_alg_values_supported"] == ["RS256"]
    assert "S256" in doc["code_challenge_methods_supported"]
    assert [k["kid"] for k in keys] == [get_key("primary").kid]
    assert keys[0]["kty"] == "RSA"
    assert keys[0]["alg"] == "RS256"


def test_a_valid_token_verifies_against_the_published_keys_and_carries_the_claims() -> None:
    oidc = FakeOidc()
    token = _id_token(oidc)
    header, claims, _, _ = decode_jwt(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == get_key("primary").kid
    assert verify_with_published_keys(oidc, token)
    assert claims["iss"] == FAKE_ISSUER
    assert claims["aud"] == CLIENT_ID
    assert claims["sub"] == "sub-alice"
    assert claims["email_verified"] is True
    assert claims["nonce"] == "nonce-1"
    assert claims["exp"] > claims["iat"]


@pytest.mark.parametrize(
    ("override", "claim", "expected"),
    [
        ({"aud": "altro-client"}, "aud", "altro-client"),
        ({"iss": "https://evil.example"}, "iss", "https://evil.example"),
        ({"exp": 1}, "exp", 1),
        ({"nonce": "diverso"}, "nonce", "diverso"),
        ({"email_verified": False}, "email_verified", False),
        ({"email_verified": "true"}, "email_verified", "true"),
    ],
)
def test_one_claim_at_a_time_can_be_manipulated_and_the_signature_stays_valid(
    override: dict[str, object], claim: str, expected: object
) -> None:
    oidc = FakeOidc()
    token = _id_token(oidc, claims=override)
    assert decode_jwt(token)[1][claim] == expected
    assert verify_with_published_keys(oidc, token), "la firma resta valida: solo la claim cambia"


def test_a_claim_can_be_removed() -> None:
    oidc = FakeOidc()
    claims = decode_jwt(_id_token(oidc, claims={"nonce": OMIT, "sub": OMIT}))[1]
    assert "nonce" not in claims
    assert "sub" not in claims


def test_signature_variants_are_really_invalid() -> None:
    oidc = FakeOidc()
    cases = {
        "altra chiave, stesso kid": TokenOptions(key="other", kid=get_key("primary").kid),
        "alg none": TokenOptions(alg="none"),
        "HS256 con la chiave pubblica": TokenOptions(alg="HS256"),
        "RS384": TokenOptions(alg="RS384"),
        "kid sconosciuto": TokenOptions(kid="mai-pubblicato"),
        "chiave non pubblicata": TokenOptions(key="rotated"),
        "payload modificato dopo la firma": TokenOptions(
            edit_payload_after_signing={"email": "vittima@example.test"}
        ),
    }
    for name, options in cases.items():
        token = _id_token(oidc, options=options)
        assert not verify_with_published_keys(oidc, token), name
    assert decode_jwt(_id_token(oidc, options=TokenOptions(alg="none")))[2] == b""
    assert decode_jwt(_id_token(oidc, options=TokenOptions(kid=OMIT)))[0].get("kid") is None
    edited = decode_jwt(_id_token(oidc, options=cases["payload modificato dopo la firma"]))
    assert edited[1]["email"] == "vittima@example.test"


def test_a_rotated_key_verifies_once_published() -> None:
    oidc = FakeOidc()
    token = _id_token(oidc, options=TokenOptions(key="rotated"))
    assert not verify_with_published_keys(oidc, token)
    oidc.published.append("rotated")
    assert verify_with_published_keys(oidc, token)


def test_token_endpoint_enforces_pkce_client_authentication_and_one_shot_codes() -> None:
    oidc = FakeOidc()
    grant = oidc.authorize(_authorize_url(oidc), ALICE)
    assert grant.code is not None
    assert _exchange(oidc, grant.code, code_verifier="sbagliato" * 6).status_code == 400
    assert _exchange(oidc, grant.code).status_code == 400, "il codice è consumato anche se fallito"
    grant = oidc.authorize(_authorize_url(oidc), ALICE)
    assert grant.code is not None
    assert _exchange(oidc, grant.code, client_secret="wrong").status_code  # noqa: S106 == 401
    grant = oidc.authorize(_authorize_url(oidc), ALICE)
    assert grant.code is not None
    assert _exchange(oidc, grant.code, redirect_uri="https://evil.example/cb").status_code == 400
    grant = oidc.authorize(_authorize_url(oidc), ALICE)
    assert grant.code is not None
    assert _exchange(oidc, grant.code).status_code == 200
    assert _exchange(oidc, grant.code).status_code == 400, "un codice vale una volta"


def test_basic_client_authentication_is_accepted() -> None:
    oidc = FakeOidc()
    grant = oidc.authorize(_authorize_url(oidc), ALICE)
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    with httpx.Client(transport=oidc.transport()) as client:
        response = client.post(
            oidc.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": grant.code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": VERIFIER,
            },
            headers={"Authorization": f"Basic {basic}"},
        )
    assert response.status_code == 200


def test_authorize_rejects_a_malformed_request_loudly() -> None:
    """Una richiesta di autorizzazione sbagliata dell'app fa fallire il test con un messaggio."""
    oidc = FakeOidc()
    with pytest.raises(AssertionError, match="redirect_uri"):
        oidc.authorize(_authorize_url(oidc, redirect_uri="https://evil.example/cb"), ALICE)
    with pytest.raises(AssertionError, match="client_id"):
        oidc.authorize(_authorize_url(oidc, client_id="altro"), ALICE)
    with pytest.raises(AssertionError, match="authorize"):
        oidc.authorize("https://evil.example/auth?state=x", ALICE)


def test_deny_builds_an_access_denied_callback_and_authorize_builds_a_code_callback() -> None:
    oidc = FakeOidc()
    denied = oidc.deny(_authorize_url(oidc))
    query = parse_qs(urlsplit(denied.callback_path).query)
    assert query == {"state": ["state-1"], "error": ["access_denied"]}
    granted = oidc.authorize(_authorize_url(oidc), ALICE)
    query = parse_qs(urlsplit(granted.callback_path).query)
    assert query["state"] == ["state-1"]
    assert "code" in query
    assert "error" not in query


def test_token_endpoint_failures_and_missing_id_token_can_be_simulated() -> None:
    oidc = FakeOidc()
    oidc.token_override = (500, {"error": "server_error"})
    grant = oidc.authorize(_authorize_url(oidc), ALICE)
    assert grant.code is not None
    assert _exchange(oidc, grant.code).status_code == 500
    oidc.token_override = None
    oidc.omit_id_token = True
    grant = oidc.authorize(_authorize_url(oidc), ALICE)
    assert grant.code is not None
    assert "id_token" not in _exchange(oidc, grant.code).json()


def test_exchanges_are_recorded_for_assertions() -> None:
    oidc = FakeOidc()
    _id_token(oidc)
    assert oidc.calls("/token") == 1
    assert oidc.exchanges[-1].form["code_verifier"] == VERIFIER
    assert json.dumps(oidc.exchanges[-1].form).count(CLIENT_SECRET) == 1


def test_concurrent_first_use_of_a_key_label_yields_a_single_key() -> None:
    """Lo stub HTTP è multi-thread: JWKS e firma del token chiedono la chiave insieme. Se ne
    nascevano due, il token era firmato con un `kid` non pubblicato (e2e paralleli rotti)."""
    label = f"race-{secrets.token_hex(4)}"
    barrier = threading.Barrier(4)
    kids: list[str] = []

    def first_use() -> None:
        barrier.wait(timeout=10)
        kids.append(get_key(label).kid)

    threads = [threading.Thread(target=first_use) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert len(kids) == 4
    assert len(set(kids)) == 1
