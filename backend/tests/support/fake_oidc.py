"""Provider OIDC finto (ASM-073, 08 §4.2): discovery, JWKS, authorize e token, tutto sintetico.

Serve a due scopi con lo stesso codice:
- nei test pytest l'app lo raggiunge con `httpx.MockTransport` (`FakeOidc.transport()`), mai
  dalla rete; il "browser" che dà il consenso è il test (`FakeOidc.authorize`);
- negli e2e gira come processo separato (`support/e2e_stack.py`) e il browser reale passa da
  `FakeOidc.authorize_http`.

Le chiavi RSA si generano a ogni sessione di test (nessuna chiave statica nel repository, 08 §5.4).
Il token è firmato qui con Python puro (nessuna libreria JOSE): il verificatore sotto prova è
joserfc/Authlib e un emittente scritto con la stessa libreria potrebbe condividerne i difetti.
Ogni claim è modificabile una alla volta (`claims=`), come l'algoritmo (`alg=none`, `HS256` con la
chiave pubblica come segreto, `RS384`), la chiave di firma, il `kid` e il payload dopo la firma.
"""

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

FAKE_ISSUER = "https://oidc.example.test"
GOOGLE_ISSUER = "https://accounts.google.com"
CLIENT_ID = "menu-design-test-client.apps.example.test"
CLIENT_SECRET = "synthetic-oidc-client-secret-for-tests-only"  # noqa: S105
REDIRECT_URI = "https://testserver/api/v1/auth/google/callback"
SCOPE = "openid email profile"
_E = 65537
_SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


class _Omit:
    def __repr__(self) -> str:
        return "OMIT"


OMIT: Any = _Omit()  # valore di un claim che va tolto dal token


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- RSA in Python puro (solo per i test) ---------------------------------------------------

_SMALL_PRIMES = [p for p in range(3, 2000) if all(p % q for q in range(2, int(p**0.5) + 1))]


def _probably_prime(n: int, rounds: int = 16) -> bool:
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = 2 + secrets.randbelow(n - 3)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _random_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _probably_prime(candidate):
            return candidate


def _der(tag: int, body: bytes) -> bytes:
    n = len(body)
    if n < 0x80:
        length = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        length = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + length + body


def _der_int(value: int) -> bytes:
    raw = value.to_bytes((value.bit_length() + 8) // 8, "big")
    return _der(0x02, raw)


@dataclass(frozen=True)
class RsaKey:
    n: int
    d: int
    kid: str
    e: int = _E

    @staticmethod
    def generate(kid: str, bits: int = 2048) -> RsaKey:
        while True:
            p, q = _random_prime(bits // 2), _random_prime(bits // 2)
            phi = (p - 1) * (q - 1)
            if p != q and phi % _E != 0 and (p * q).bit_length() == bits:
                return RsaKey(n=p * q, d=pow(_E, -1, phi), kid=kid)

    @property
    def size(self) -> int:
        return (self.n.bit_length() + 7) // 8

    def jwk(self) -> dict[str, str]:
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": self.kid,
            "n": b64u(self.n.to_bytes(self.size, "big")),
            "e": b64u(self.e.to_bytes((self.e.bit_length() + 7) // 8, "big")),
        }

    def sign_rs256(self, signing_input: bytes) -> bytes:
        digest = _SHA256_DIGESTINFO + hashlib.sha256(signing_input).digest()
        padding = b"\xff" * (self.size - len(digest) - 3)
        encoded = int.from_bytes(b"\x00\x01" + padding + b"\x00" + digest, "big")
        return pow(encoded, self.d, self.n).to_bytes(self.size, "big")

    def verify_rs256(self, signing_input: bytes, signature: bytes) -> bool:
        if len(signature) != self.size:
            return False
        recovered = pow(int.from_bytes(signature, "big"), self.e, self.n).to_bytes(self.size, "big")
        digest = _SHA256_DIGESTINFO + hashlib.sha256(signing_input).digest()
        expected = b"\x00\x01" + b"\xff" * (self.size - len(digest) - 3) + b"\x00" + digest
        return hmac.compare_digest(recovered, expected)

    def public_pem(self) -> bytes:
        """SubjectPublicKeyInfo in PEM: segreto HMAC dell'attacco di confusione RS256 -> HS256."""
        rsa_public = _der(0x30, _der_int(self.n) + _der_int(self.e))
        algorithm = _der(0x30, bytes.fromhex("06092a864886f70d0101010500"))
        spki = _der(0x30, algorithm + _der(0x03, b"\x00" + rsa_public))
        body = base64.encodebytes(spki).decode("ascii").replace("\n", "")
        lines = [body[i : i + 64] for i in range(0, len(body), 64)]
        return (
            "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"
        ).encode()


_KEYS: dict[str, RsaKey] = {}
_KEYS_LOCK = threading.Lock()


def get_key(label: str) -> RsaKey:
    """Chiave RSA 2048 per etichetta (`primary`, `other`, `rotated`, ...), una per processo.

    Con il lock: lo stub HTTP è multi-thread e `functools.cache` non serializza le chiamate
    concorrenti, per cui due login paralleli generavano due chiavi `primary` diverse (JWKS con
    un `kid`, token firmato con un altro: `identity.token_rejected`).
    """
    with _KEYS_LOCK:
        key = _KEYS.get(label)
        if key is None:
            key = _KEYS[label] = RsaKey.generate(kid=f"test-{label}-{secrets.token_hex(4)}")
        return key


# --- identità, token e flusso -------------------------------------------------------------------


@dataclass
class Identity:
    """Ciò che Google dichiara dell'utente (tutti dati sintetici)."""

    sub: str
    email: str
    email_verified: Any = True
    name: str | None = "Alice Alfa"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenOptions:
    """Come costruire il token ID. Il default è un token valido."""

    alg: str = "RS256"  # RS256 | RS384 | HS256 | none
    key: str = "primary"  # etichetta della chiave di firma
    kid: Any = None  # None = `kid` della chiave; OMIT = nessun kid; stringa = quel kid
    edit_payload_after_signing: dict[str, Any] | None = None


@dataclass
class Authorization:
    """Una richiesta di autorizzazione accolta dal provider (il consenso dato dall'utente)."""

    params: dict[str, str]
    state: str
    code: str | None
    error: str | None = None

    @property
    def callback_path(self) -> str:
        query = {"state": self.state}
        if self.error:
            query["error"] = self.error
        elif self.code:
            query["code"] = self.code
        return "/api/v1/auth/google/callback?" + urlencode(query)


@dataclass
class _Grant:
    identity: Identity
    claims: Mapping[str, Any]
    options: TokenOptions
    nonce: str
    challenge: str
    redirect_uri: str
    used: bool = False


@dataclass
class Exchange:
    """Una chiamata server-a-server al provider, per le asserzioni."""

    method: str
    path: str
    form: dict[str, str]
    authorization: str | None


class FakeOidc:
    def __init__(
        self,
        issuer: str = FAKE_ISSUER,
        client_id: str = CLIENT_ID,
        client_secret: str = CLIENT_SECRET,
        redirect_uri: str = REDIRECT_URI,
    ) -> None:
        self.issuer = issuer
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.published = ["primary"]
        self.exchanges: list[Exchange] = []
        self.token_override: tuple[int, Any] | None = None
        self.omit_id_token = False
        self.issued: list[str] = []  # id_token e access_token emessi, per cercarli nei log
        self._grants: dict[str, _Grant] = {}

    # -- indirizzi -------------------------------------------------------------------------
    @property
    def discovery_url(self) -> str:
        return f"{self.issuer}/.well-known/openid-configuration"

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.issuer}/o/oauth2/v2/auth"

    @property
    def token_endpoint(self) -> str:
        return f"{self.issuer}/token"

    @property
    def jwks_uri(self) -> str:
        return f"{self.issuer}/jwks"

    def calls(self, path_suffix: str) -> int:
        return sum(1 for e in self.exchanges if e.path.endswith(path_suffix))

    # -- lato "browser": l'utente dà il consenso ---------------------------------------------
    def authorize(
        self,
        redirect_url: str,
        identity: Identity,
        *,
        claims: Mapping[str, Any] | None = None,
        options: TokenOptions | None = None,
    ) -> Authorization:
        params = self._check_authorization_request(redirect_url)
        code = b64u(secrets.token_bytes(24))
        self._grants[code] = _Grant(
            identity=identity,
            claims=dict(claims or {}),
            options=options or TokenOptions(),
            nonce=params.get("nonce", ""),
            challenge=params.get("code_challenge", ""),
            redirect_uri=params["redirect_uri"],
        )
        return Authorization(params=params, state=params["state"], code=code)

    def deny(self, redirect_url: str, error: str = "access_denied") -> Authorization:
        params = self._check_authorization_request(redirect_url)
        return Authorization(params=params, state=params["state"], code=None, error=error)

    def authorize_http(self, query: Mapping[str, str], identity: Identity | None) -> Authorization:
        """Per gli e2e: consenso (o rifiuto, se `identity` è None) a una richiesta del browser."""
        url = self.authorization_endpoint + "?" + urlencode(dict(query))
        return self.authorize(url, identity) if identity is not None else self.deny(url)

    def _check_authorization_request(self, redirect_url: str) -> dict[str, str]:
        parts = urlsplit(redirect_url)
        base = f"{parts.scheme}://{parts.netloc}{parts.path}"
        assert base == self.authorization_endpoint, f"redirectUrl non è l'authorize: {base}"
        raw = parse_qs(parts.query, keep_blank_values=True)
        assert all(len(v) == 1 for v in raw.values()), f"parametri ripetuti: {raw}"
        params = {k: v[0] for k, v in raw.items()}
        assert params.get("client_id") == self.client_id, "client_id diverso da quello registrato"
        assert params.get("redirect_uri") == self.redirect_uri, "redirect_uri non registrato"
        assert params.get("response_type") == "code"
        assert params.get("state"), "manca lo state"
        return params

    # -- lato server: discovery, JWKS, token -------------------------------------------------
    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            status, headers, body = self.dispatch(
                request.method,
                str(request.url),
                request.read(),
                request.headers.get("authorization"),
            )
            return httpx.Response(status, headers=headers, content=body)

        return httpx.MockTransport(handler)

    def dispatch(
        self, method: str, url: str, body: bytes = b"", authorization: str | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        parts = urlsplit(url)
        path = parts.path
        form = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}
        self.exchanges.append(Exchange(method, path, form, authorization))
        if method == "GET" and path == "/.well-known/openid-configuration":
            return self._json(200, self._discovery())
        if method == "GET" and path == "/jwks":
            return self._json(200, {"keys": [get_key(label).jwk() for label in self.published]})
        if method == "POST" and path == "/token":
            return self._token(form, authorization)
        return self._json(404, {"error": "not_found", "path": path})

    def _discovery(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "jwks_uri": self.jwks_uri,
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "scopes_supported": ["openid", "email", "profile"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        }

    @staticmethod
    def _json(status: int, body: Any) -> tuple[int, dict[str, str], bytes]:
        return status, {"content-type": "application/json"}, json.dumps(body).encode()

    def _authenticated(self, form: Mapping[str, str], authorization: str | None) -> bool:
        if authorization and authorization.lower().startswith("basic "):
            user, _, secret = (
                base64.b64decode(authorization[6:]).decode("utf-8", "replace").partition(":")
            )
            return user == self.client_id and secret == self.client_secret
        return form.get("client_id") == self.client_id and (
            form.get("client_secret") == self.client_secret
        )

    def _token(
        self, form: Mapping[str, str], authorization: str | None
    ) -> tuple[int, dict[str, str], bytes]:
        if self.token_override is not None:
            return self._json(*self.token_override)
        if not self._authenticated(form, authorization):
            return self._json(401, {"error": "invalid_client"})
        grant = self._grants.get(form.get("code", ""))
        if form.get("grant_type") != "authorization_code" or grant is None or grant.used:
            return self._json(400, {"error": "invalid_grant"})
        grant.used = True
        if form.get("redirect_uri") != grant.redirect_uri:
            return self._json(400, {"error": "invalid_grant", "error_description": "redirect"})
        verifier = form.get("code_verifier", "")
        challenge = b64u(hashlib.sha256(verifier.encode("ascii", "replace")).digest())
        if not grant.challenge or challenge != grant.challenge:
            return self._json(400, {"error": "invalid_grant", "error_description": "pkce"})
        access_token = b64u(secrets.token_bytes(24))
        self.issued.append(access_token)
        body: dict[str, Any] = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3599,
            "scope": SCOPE,
        }
        if not self.omit_id_token:
            body["id_token"] = self.make_id_token(grant)
            self.issued.append(body["id_token"])
        return self._json(200, body)

    # -- il token ID -------------------------------------------------------------------------
    def valid_claims(self, grant: _Grant) -> dict[str, Any]:
        now = int(time.time())
        ident = grant.identity
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.client_id,
            "azp": self.client_id,
            "sub": ident.sub,
            "email": ident.email,
            "email_verified": ident.email_verified,
            "iat": now,
            "exp": now + 3600,
            "nonce": grant.nonce,
        }
        if ident.name is not None:
            claims["name"] = ident.name
        claims.update(ident.extra)
        for name, value in grant.claims.items():
            if value is OMIT:
                claims.pop(name, None)
            else:
                claims[name] = value
        return claims

    def make_id_token(self, grant: _Grant) -> str:
        return self.encode(self.valid_claims(grant), grant.options)

    def encode(self, claims: Mapping[str, Any], options: TokenOptions | None = None) -> str:
        opts = options or TokenOptions()
        key = get_key(opts.key)
        header: dict[str, Any] = {"alg": opts.alg, "typ": "JWT"}
        if opts.kid is None:
            header["kid"] = key.kid
        elif opts.kid is not OMIT:
            header["kid"] = opts.kid
        signing_input = (
            b64u(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + b64u(json.dumps(dict(claims), separators=(",", ":")).encode())
        ).encode()
        if opts.alg == "none":
            signature = b""
        elif opts.alg == "HS256":
            signature = hmac.new(
                get_key("primary").public_pem(), signing_input, hashlib.sha256
            ).digest()
        elif opts.alg == "RS384":
            signature = _sign_rs384(key, signing_input)
        else:
            signature = key.sign_rs256(signing_input)
        payload_b64 = signing_input.decode().split(".")[1]
        if opts.edit_payload_after_signing:
            edited = {**dict(claims), **opts.edit_payload_after_signing}
            payload_b64 = b64u(json.dumps(edited, separators=(",", ":")).encode())
        return signing_input.decode().split(".")[0] + "." + payload_b64 + "." + b64u(signature)


def _sign_rs384(key: RsaKey, signing_input: bytes) -> bytes:
    prefix = bytes.fromhex("3041300d060960864801650304020205000430")
    digest = prefix + hashlib.sha384(signing_input).digest()
    padding = b"\xff" * (key.size - len(digest) - 3)
    encoded = int.from_bytes(b"\x00\x01" + padding + b"\x00" + digest, "big")
    return pow(encoded, key.d, key.n).to_bytes(key.size, "big")


# --- verifica indipendente (solo per provare il provider finto) -------------------------------


def decode_jwt(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    head, payload, signature = token.split(".")
    return (
        json.loads(b64u_decode(head)),
        json.loads(b64u_decode(payload)),
        b64u_decode(signature),
        f"{head}.{payload}".encode(),
    )


def verify_with_published_keys(oidc: FakeOidc, token: str) -> bool:
    header, _, signature, signing_input = decode_jwt(token)
    if header.get("alg") != "RS256":
        return False
    return any(
        get_key(label).kid == header.get("kid")
        and get_key(label).verify_rs256(signing_input, signature)
        for label in oidc.published
    )
