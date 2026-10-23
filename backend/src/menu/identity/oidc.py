"""Client OIDC di Google: discovery, JWKS, scambio del codice e validazione del token ID.

SR-001, SR-033, THR-001, THR-002, THR-015; ADR-0004 (Authlib + joserfc, PKCE S256).

- Authlib costruisce l'URL di autorizzazione (PKCE S256, `state`, `nonce`) e scambia il codice
  sul token endpoint con il `client_secret` (mai verso il browser).
- joserfc verifica la firma con algoritmo fisso RS256 sulle chiavi dell'emittente; `iss`, `aud`,
  `azp`, `exp`, `nonce`, `sub`, `email` ed `email_verified is True` si controllano uno a uno.
  Il token si accetta solo se arriva dal token endpoint, mai dai parametri del browser.
- La discovery è pigra (nessuna richiesta all'avvio). Il JWKS sta in cache e si rilegge su un
  `kid` sconosciuto al più una volta ogni minuto: un aggressore con `kid` casuali non trasforma
  l'app in un generatore di richieste verso Google.
- Ogni errore diventa `OidcError` con un messaggio fisso: niente token, codici o claim nei log.
"""

import base64
import json
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from authlib.integrations.httpx_client import OAuth2Client
from joserfc import jwt
from joserfc.jwk import RSAKey

from menu.identity.accounts import SUBJECT_MAX, clean_display_name, valid_email
from menu.identity.models import GoogleIdentity
from menu.identity.tokens import constant_time_equal_bytes, digest

SCOPE = "openid email profile"
ALGORITHMS = ["RS256"]
CLIENT_AUTH_METHOD = "client_secret_post"  # RFC 6749 §2.3.1: il segreto nel corpo, solo lato server
HTTP_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
MAX_DOCUMENT_BYTES = 512 * 1024
DISCOVERY_TTL = 24 * 3600.0
JWKS_TTL = 3600.0
FORCED_REFRESH_MIN_INTERVAL = 60.0
LEEWAY_SECONDS = 60


class OidcError(Exception):
    """Errore dell'accesso con Google; il messaggio è fisso e senza dati."""


@dataclass(frozen=True)
class _Endpoints:
    authorization: str
    token: str
    jwks: str


def _b64url_json(segment: str) -> Any:
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


class OidcClient:
    def __init__(
        self,
        *,
        issuer: str,
        client_id: str | None,
        client_secret: str | None,
        redirect_uri: str,
        http: httpx.Client | None = None,
    ) -> None:
        self._issuer = issuer
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http or httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False)
        self._lock = threading.Lock()
        self._endpoints: _Endpoints | None = None
        self._endpoints_at = 0.0
        self._keys: dict[str, dict[str, Any]] | None = None
        self._keys_at = 0.0
        self._last_forced_refresh: float | None = None

    def close(self) -> None:
        self._http.close()

    # -- documenti remoti ------------------------------------------------------------------
    def _get_document(self, url: str) -> dict[str, Any]:
        if urlsplit(url).scheme != urlsplit(self._issuer).scheme:
            raise OidcError("endpoint con schema diverso dall'emittente")
        try:
            response = self._http.get(url, headers={"Accept": "application/json"})
            document = response.json() if response.status_code == 200 else None
            too_big = len(response.content) > MAX_DOCUMENT_BYTES
        except (httpx.HTTPError, ValueError) as error:
            raise OidcError("documento OIDC non raggiungibile") from error
        if too_big or not isinstance(document, dict):
            raise OidcError("documento OIDC non valido")
        return document

    def _discover(self) -> _Endpoints:
        with self._lock:
            now = time.monotonic()
            if self._endpoints is not None and now - self._endpoints_at < DISCOVERY_TTL:
                return self._endpoints
            document = self._get_document(f"{self._issuer}/.well-known/openid-configuration")
            if document.get("issuer") != self._issuer:
                raise OidcError("l'emittente della discovery non coincide")
            values = [
                document.get(k) for k in ("authorization_endpoint", "token_endpoint", "jwks_uri")
            ]
            if not all(isinstance(v, str) and v for v in values):
                raise OidcError("discovery incompleta")
            scheme = urlsplit(self._issuer).scheme
            if any(urlsplit(str(v)).scheme != scheme for v in values):
                raise OidcError("endpoint con schema diverso dall'emittente")
            self._endpoints = _Endpoints(*[str(v) for v in values])
            self._endpoints_at = now
            return self._endpoints

    def _load_keys(self, endpoints: _Endpoints, now: float) -> None:
        document = self._get_document(endpoints.jwks)
        listed = document.get("keys")
        if not isinstance(listed, list):
            raise OidcError("JWKS non valido")
        keys: dict[str, dict[str, Any]] = {}
        for jwk in listed:
            if (
                isinstance(jwk, dict)
                and jwk.get("kty") == "RSA"
                and isinstance(jwk.get("kid"), str)
            ):
                keys[jwk["kid"]] = jwk
        self._keys = keys
        self._keys_at = now

    def _key_for(self, kid: str) -> dict[str, Any]:
        endpoints = self._discover()
        with self._lock:
            now = time.monotonic()
            if self._keys is None or now - self._keys_at >= JWKS_TTL:
                self._load_keys(endpoints, now)
            found = (self._keys or {}).get(kid)
            if found is not None:
                return found
            last = self._last_forced_refresh
            if last is None or now - last >= FORCED_REFRESH_MIN_INTERVAL:
                self._last_forced_refresh = now
                self._load_keys(endpoints, now)
                found = (self._keys or {}).get(kid)
                if found is not None:
                    return found
        raise OidcError("chiave di firma sconosciuta")

    # -- flusso OAuth ----------------------------------------------------------------------
    def _oauth(self) -> OAuth2Client:
        if not self._client_id or not self._client_secret:
            raise OidcError("client OAuth non configurato")
        return OAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            redirect_uri=self._redirect_uri,
            scope=SCOPE,
            code_challenge_method="S256",
            token_endpoint_auth_method=CLIENT_AUTH_METHOD,
            timeout=HTTP_TIMEOUT,
            follow_redirects=False,
        )

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        endpoints = self._discover()
        with self._oauth() as client:
            url, _ = client.create_authorization_url(
                endpoints.authorization,
                state=state,
                nonce=nonce,
                code_verifier=code_verifier,
                prompt="select_account",
            )
        return str(url)

    def identity_from_code(
        self, *, code: str, code_verifier: str, nonce_hash: bytes
    ) -> GoogleIdentity:
        """Scambia il codice e verifica il token ID: `OidcError` per qualunque anomalia."""
        endpoints = self._discover()
        try:
            with self._oauth() as client:
                token = client.fetch_token(
                    endpoints.token,
                    code=code,
                    code_verifier=code_verifier,
                    grant_type="authorization_code",
                )
            id_token = token.get("id_token")
        except Exception as error:
            raise OidcError("scambio del codice non riuscito") from error
        if not isinstance(id_token, str) or not id_token:
            raise OidcError("token ID assente")
        return self.verify_id_token(id_token, nonce_hash)

    # -- token ID --------------------------------------------------------------------------
    def verify_id_token(self, token: str, nonce_hash: bytes) -> GoogleIdentity:
        try:
            header = _b64url_json(token.split(".")[0])
            kid = header["kid"]
            if header.get("alg") not in ALGORITHMS or not isinstance(kid, str):
                raise OidcError("intestazione del token non ammessa")
        except OidcError:
            raise
        except Exception as error:
            raise OidcError("token ID illeggibile") from error
        jwk = self._key_for(kid)
        try:
            decoded = jwt.decode(token, RSAKey.import_key(jwk), algorithms=ALGORITHMS)
            claims: dict[str, Any] = decoded.claims
            jwt.JWTClaimsRegistry(
                leeway=LEEWAY_SECONDS,
                exp={"essential": True},
                nbf={"essential": False},
            ).validate(claims)
        except Exception as error:
            raise OidcError("token ID non valido") from error
        return self._identity_from_claims(claims, nonce_hash)

    def _identity_from_claims(self, claims: dict[str, Any], nonce_hash: bytes) -> GoogleIdentity:
        audience = claims.get("aud")
        audiences = [audience] if isinstance(audience, str) else audience
        nonce = claims.get("nonce")
        subject = claims.get("sub")
        email = valid_email(claims.get("email"))
        checks = (
            claims.get("iss") == self._issuer,
            isinstance(audiences, list) and self._client_id in audiences,
            len(audiences or []) == 1 or claims.get("azp") == self._client_id,
            claims.get("azp", self._client_id) == self._client_id,
            isinstance(nonce, str)
            and nonce != ""
            and constant_time_equal_bytes(digest(nonce), nonce_hash),
            isinstance(subject, str) and 0 < len(subject) <= SUBJECT_MAX,
            email is not None,
            claims.get("email_verified") is True,
        )
        if not all(checks) or email is None or not isinstance(subject, str):
            raise OidcError("claim del token ID non valide")
        return GoogleIdentity(
            subject=subject, email=email, display_name=clean_display_name(claims.get("name"), email)
        )
