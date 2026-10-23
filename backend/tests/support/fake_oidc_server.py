"""Il provider OIDC finto come vero server HTTP su 127.0.0.1 (thread), per pytest e per gli e2e.

L'app raggiunge l'emittente con una vera richiesta HTTP: nessun gancio di test nel codice di
produzione (08 §4.2; nei test `APP_ENV=test` l'emittente configurato è questo indirizzo, in
`production` e `staging` la configurazione accetta solo Google). `interactive=True` aggiunge
la pagina di consenso per il browser degli e2e: sceglie l'utente dal cookie `stub_identity`
(JSON in base64url con `sub`, `email`, ... oppure `{"deny": true}`), così i test in parallelo
non si pestano i piedi.
"""

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from support.fake_oidc import FakeOidc, Identity, b64u_decode, get_key

IDENTITY_COOKIE = "stub_identity"
Seed = Callable[[dict[str, Any]], None]


class StubServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self, *, port: int = 0, interactive: bool = False, seed: Seed | None = None
    ) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.interactive = interactive
        self.seed = seed
        self.oidc = FakeOidc(issuer=self.issuer)
        self._thread: threading.Thread | None = None

    @property
    def issuer(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def start(self) -> None:
        # Le chiavi RSA (Python puro) si generano in tempi molto variabili: se nascessero alla
        # prima richiesta HTTP potrebbero superare il timeout (5 s) dell'app e rendere il test
        # instabile. Si scaldano qui, prima di servire.
        for label in ("primary", "other", "rotated"):
            get_key(label)
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def fresh(self, *, redirect_uri: str) -> FakeOidc:
        """Stato nuovo per un test: chiavi pubblicate, scambi e override azzerati."""
        self.oidc = FakeOidc(issuer=self.issuer, redirect_uri=redirect_uri)
        return self.oidc


class _Handler(BaseHTTPRequestHandler):
    server: StubServer

    def log_message(self, format: str, *args: Any) -> None:
        return  # niente rumore nei test

    def _reply(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        if self.server.interactive and parts.path == "/o/oauth2/v2/auth":
            self._consent(parts.query)
            return
        status, headers, body = self.server.oidc.dispatch(
            "GET", f"{self.server.issuer}{self.path}", b"", self.headers.get("Authorization")
        )
        self._reply(status, headers, body)

    def do_POST(self) -> None:
        body = self._body()
        if self.server.seed is not None and self.path == "/__seed":
            try:
                self.server.seed(json.loads(body))
            except Exception as error:
                self._reply(500, {"content-type": "text/plain"}, f"{type(error).__name__}".encode())
                return
            self._reply(204, {}, b"")
            return
        status, headers, out = self.server.oidc.dispatch(
            "POST", f"{self.server.issuer}{self.path}", body, self.headers.get("Authorization")
        )
        self._reply(status, headers, out)

    def _identity(self) -> Identity | None:
        cookies = dict(
            part.strip().split("=", 1)
            for part in (self.headers.get("Cookie") or "").split(";")
            if "=" in part
        )
        raw = cookies.get(IDENTITY_COOKIE)
        if raw is None:
            return None
        data = json.loads(b64u_decode(raw))
        if data.get("deny"):
            return None
        return Identity(
            sub=data["sub"],
            email=data["email"],
            email_verified=data.get("email_verified", True),
            name=data.get("name", "Alice Alfa"),
            extra=data.get("extra", {}),
        )

    def _consent(self, query: str) -> None:
        params = {k: v[0] for k, v in parse_qs(query).items()}
        try:
            grant = self.server.oidc.authorize_http(params, self._identity())
        except AssertionError as error:  # richiesta di autorizzazione errata: il test lo vede
            self._reply(400, {"content-type": "text/plain"}, str(error).encode())
            return
        location = params["redirect_uri"] + "?" + grant.callback_path.split("?", 1)[1]
        self._reply(302, {"Location": location}, b"")
