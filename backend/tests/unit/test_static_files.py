"""SL-01: FastAPI serve la SPA compilata sulla stessa origine (piano §7.1 SL-01, §5.2).

Verifica: allow-list dei file, fallback SPA, Cache-Control di SR-046 (`index.html` e `sw.js`
`no-cache`, asset con hash `immutable`), header di sicurezza e CSP con Trusted Types (SR-023),
nessuna risorsa di terzi (SR-031), nessuna fuga di file fuori dalla cartella (THR-074, THR-090).

Contratto assunto (variabile d'ambiente): `WEB_DIST_DIR` = cartella della build (`web/dist`).
Non impostata: nessun file statico (solo API). Impostata ma senza `index.html`: avvio rifiutato.
I test non dipendono da una build reale: usano una cartella di prova creata in `tmp_path`.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from menu.platform.http.middleware import SECURITY_HEADERS
from support.assets import ASSET_CSS, ASSET_JS, build_dist

BASE_URL = "https://testserver"
INDEX_MARK = '<div id="root"></div>'


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return build_dist(tmp_path)


@pytest.fixture
def static_client(
    app_env: None, dist: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from menu.app import create_app

    monkeypatch.setenv("WEB_DIST_DIR", str(dist))
    with TestClient(create_app(), base_url=BASE_URL, raise_server_exceptions=False) as client:
        yield client


def _tokens(response_headers_value: str | None) -> set[str]:
    assert response_headers_value is not None, "Cache-Control assente"
    return {t.strip().lower() for t in response_headers_value.split(",") if t.strip()}


def _csp(value: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for part in value.split(";"):
        words = part.split()
        if words:
            out[words[0]] = words[1:]
    return out


# --- servire la SPA ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_index_html_is_served_with_no_cache_sr_046(static_client: TestClient, path: str) -> None:
    """SR-046: `index.html` si rivalida sempre (`no-cache`), mai `immutable` né `max-age`."""
    r = static_client.get(path)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert INDEX_MARK in r.text
    tokens = _tokens(r.headers.get("cache-control"))
    assert "no-cache" in tokens
    assert not {t for t in tokens if t.startswith("max-age=") and t != "max-age=0"}
    assert "immutable" not in tokens
    assert r.headers.get("etag") or r.headers.get("last-modified"), "serve un validatore"


def test_no_cache_means_revalidation_returns_304_sr_046(static_client: TestClient) -> None:
    first = static_client.get("/")
    assert first.status_code == 200
    validator = (
        {"If-None-Match": first.headers["etag"]}
        if "etag" in first.headers
        else {"If-Modified-Since": first.headers["last-modified"]}
    )
    again = static_client.get("/", headers=validator)
    assert again.status_code == 304
    assert "no-cache" in _tokens(again.headers.get("cache-control"))
    assert again.headers["x-content-type-options"] == "nosniff"


def test_service_worker_file_is_no_cache_and_javascript_sr_046(static_client: TestClient) -> None:
    r = static_client.get("/sw.js")
    assert r.status_code == 200
    assert re.match(r"(text|application)/javascript", r.headers["content-type"])
    tokens = _tokens(r.headers.get("cache-control"))
    assert "no-cache" in tokens
    assert "immutable" not in tokens
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(("path", "ctype"), [(ASSET_JS, "javascript"), (ASSET_CSS, "text/css")])
def test_hashed_assets_are_immutable_for_a_year_sr_046(
    static_client: TestClient, path: str, ctype: str
) -> None:
    r = static_client.get(path)
    assert r.status_code == 200
    assert ctype in r.headers["content-type"]
    tokens = _tokens(r.headers.get("cache-control"))
    assert {"public", "immutable", "max-age=31536000"} <= tokens
    assert "no-store" not in tokens, "l'envelope non deve sovrascrivere la cache degli asset"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_asset_without_a_content_hash_is_not_immutable_sr_046(static_client: TestClient) -> None:
    """`immutable` solo con l'hash nel nome: altrimenti un file aggiornato non arriva mai."""
    r = static_client.get("/assets/plain.js")
    assert r.status_code == 200
    assert "immutable" not in _tokens(r.headers.get("cache-control"))


def test_head_request_on_an_asset_has_headers_and_no_body(static_client: TestClient) -> None:
    r = static_client.head(ASSET_JS)
    assert r.status_code == 200
    assert "immutable" in _tokens(r.headers.get("cache-control"))
    assert r.content == b""


def test_text_assets_are_compressed_for_nfr_001(static_client: TestClient) -> None:
    """NFR-001 (NEEDS_DECISION nel report): il budget di 150 KB è *gzip*; il server deve
    quindi consegnare gzip, altrimenti il budget misura un valore che l'utente non scarica."""
    r = static_client.get(ASSET_JS, headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    assert "accept-encoding" in r.headers.get("vary", "").lower()
    raw = static_client.get(ASSET_JS, headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in raw.headers
    assert r.content == raw.content, "il client decodifica gzip: il contenuto deve coincidere"


# --- fallback SPA -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/accedi",
        "/piano",
        "/piano/2026-10-19/cena",
        "/piano/2026-10-19/altro-2/scegli",
        "/altro/famiglia",
        "/invito",
        "/questa-rotta-non-esiste",
    ],
)
def test_spa_routes_fall_back_to_index_html(static_client: TestClient, path: str) -> None:
    r = static_client.get(path)
    assert r.status_code == 200
    assert INDEX_MARK in r.text
    assert "no-cache" in _tokens(r.headers.get("cache-control"))


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/missing",
        "/api/v1/",
        "/api",
        "/api/",
        "/api/v1/session",  # esisterà in SL-03a: qui l'API non c'è ancora e non va in index.html
    ],
)
def test_unknown_api_paths_never_fall_back_to_html(static_client: TestClient, path: str) -> None:
    """Un client API riceve un errore problem+json, mai la pagina HTML (THR-110)."""
    r = static_client.get(path)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "not_found"
    assert INDEX_MARK not in r.text


@pytest.mark.parametrize(
    "path",
    [
        "/assets/missing-Zz9Yy8Xx.js",
        "/assets/missing.css",
        "/missing.js",
        "/missing.css",
        "/missing.map",
        "/robots-missing.txt",
        "/favicon.ico",  # assente nella cartella di prova
    ],
)
def test_missing_files_with_an_extension_are_404_not_index(
    static_client: TestClient, path: str
) -> None:
    r = static_client.get(path)
    assert r.status_code == 404
    assert INDEX_MARK not in r.text


def test_missing_service_worker_is_404_never_html(
    app_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se `sw.js` non c'è (PWA arriva in M2) il browser non deve ricevere HTML come script."""
    from menu.app import create_app

    only_index = build_dist(tmp_path / "noswsite", with_sw=False)
    monkeypatch.setenv("WEB_DIST_DIR", str(only_index))
    with TestClient(create_app(), base_url=BASE_URL, raise_server_exceptions=False) as client:
        r = client.get("/sw.js")
    assert r.status_code == 404
    assert INDEX_MARK not in r.text


def test_healthz_still_works_next_to_the_spa(static_client: TestClient) -> None:
    r = static_client.get("/healthz")
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["status"] in {"ok", "unavailable"}
    assert r.headers["cache-control"] == "no-store"


# --- allow-list e path traversal (THR-074, SR-009) --------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/notes.txt",  # file nella cartella ma non in allow-list
        "/.env",
        "/.hidden/secret.txt",
        "/assets/.env",
        f"{ASSET_JS}.map",  # source map: mai servite
        "/assets/index-Ab12Cd34.css.map",
        "/assets/",  # nessun elenco di cartella
        "/assets",
        "/assets/subdir/",
        "/assets/link-Qq1Ww2Ee.js",  # symlink verso un file fuori dalla cartella
        "/assets/%2e%2e/notes.txt",
        "/assets/%2E%2E/notes.txt",
        "/assets/..%2fnotes.txt",
        "/assets/%2e%2e%2f%2e%2e%2foutside.js",
        "/assets/%2e%2e%2f%2e%2e%2f%2e%2e%2foutside.txt",
        "/%2e%2e/outside.txt",
        "/..%2foutside.txt",
        "/assets/..%5cnotes.txt",
        "/assets/index-Ab12Cd34.js%00.png",
        "/assets//etc/passwd",
    ],
)
def test_only_allow_listed_files_are_served_and_nothing_escapes(
    static_client: TestClient, path: str
) -> None:
    r = static_client.get(path)
    body = r.text
    for canary in ("CANARY-STATIC-NOTES", "CANARY-STATIC-DOTENV", "CANARY-OUTSIDE", "root:x:"):
        assert canary not in body, f"fuga di contenuto da {path}"
    assert "sourceMappingURL" not in body
    assert r.status_code in {400, 404}, f"{path} -> {r.status_code}"


def test_raw_dot_dot_segments_cannot_escape(static_client: TestClient) -> None:
    """Richiesta con `..` nel percorso grezzo (il client non lo normalizza)."""
    r = static_client.get("/assets/x/../../notes.txt")
    assert "CANARY-STATIC-NOTES" not in r.text
    r2 = static_client.request("GET", "/assets/../../outside.js")
    assert "CANARY-OUTSIDE" not in r2.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/", "/index.html", ASSET_JS, "/accedi", "/sw.js"])
def test_static_paths_do_not_accept_writes(
    static_client: TestClient, method: str, path: str
) -> None:
    r = static_client.request(method, path, json={"a": 1})
    assert r.status_code in {404, 405}
    assert r.headers["content-type"].startswith("application/problem+json")


# --- header di sicurezza e CSP (SR-023, SR-031) -----------------------------------------------


@pytest.mark.parametrize(
    "path", ["/", "/index.html", "/accedi", "/sw.js", ASSET_JS, ASSET_CSS, "/assets/missing.js"]
)
def test_every_static_response_carries_the_security_headers(
    static_client: TestClient, path: str
) -> None:
    r = static_client.get(path)
    for name, value in SECURITY_HEADERS.items():
        assert r.headers.get(name) == value, f"{name} su {path}"


def test_csp_blocks_inline_script_eval_and_third_parties_sr_023_sr_031(
    static_client: TestClient,
) -> None:
    csp = _csp(static_client.get("/").headers["content-security-policy"])
    assert csp["default-src"] == ["'self'"]
    assert csp["script-src"] == ["'self'"], "niente 'unsafe-inline', 'unsafe-eval', host esterni"
    assert csp["connect-src"] == ["'self'"], "SR-031: nessuna connessione verso terzi"
    assert csp["object-src"] == ["'none'"]
    assert csp["base-uri"] == ["'none'"]
    assert csp["form-action"] == ["'self'"]
    assert csp["frame-ancestors"] == ["'none'"]
    assert csp["require-trusted-types-for"] == ["'script'"], "Trusted Types (THR-070)"
    assert csp["trusted-types"] == ["'none'"], "nessuna policy Trusted Types (SEC-SL01-001)"
    assert csp["img-src"] == ["'self'"], "nessun data: in img-src (SEC-SL01-001)"
    assert csp["style-src"] == ["'self'"], (
        "revisione style-src (SL-00a): resta 'self' senza 'unsafe-inline'; la SPA non usa "
        "attributi style nell'HTML né tag <style> (verifica nel browser: e2e/csp.spec.ts)"
    )
    allowed = {"'self'", "'none'", "'script'"}
    for name, values in csp.items():
        assert set(values) <= allowed, f"{name} ammette {set(values) - allowed}"
    if "trusted-types" in csp:
        assert "*" not in csp["trusted-types"]
        assert "'allow-duplicates'" not in csp["trusted-types"]


def test_index_html_has_no_inline_script_no_inline_style_no_external_resource(
    dist: Path,
) -> None:
    """La pagina di prova rispetta la regola che la build vera deve rispettare (SR-031);
    il controllo sulla build reale è in `web/tests/e2e/third-party.spec.ts`."""
    html = (dist / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert not re.search(r"\bstyle\s*=", html)
    assert not re.search(r"(src|href)=[\"']?(https?:)?//", html)


# --- configurazione ---------------------------------------------------------------------------


def test_without_web_dist_dir_the_app_serves_only_the_api(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from menu.app import create_app

    monkeypatch.delenv("WEB_DIST_DIR", raising=False)
    with TestClient(create_app(), base_url=BASE_URL, raise_server_exceptions=False) as client:
        r = client.get("/")
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/problem+json")
        assert client.get("/healthz").status_code in {200, 503}


@pytest.mark.parametrize("missing", ["directory", "index"])
def test_misconfigured_web_dist_dir_refuses_to_start(
    app_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """Fail closed (piano §5.2): un servizio senza SPA non deve sembrare sano."""
    from menu.app import create_app

    target = tmp_path / "nowhere"
    if missing == "index":
        target.mkdir()
        (target / "other.html").write_text("x", encoding="utf-8")
    monkeypatch.setenv("WEB_DIST_DIR", str(target))
    with pytest.raises(ValueError):  # noqa: PT011 - ValueError copre ValidationError di pydantic
        create_app()


def test_the_error_for_a_bad_web_dist_dir_does_not_leak_the_database_url(
    app_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from menu.app import create_app

    monkeypatch.setenv("WEB_DIST_DIR", str(tmp_path / "nowhere"))
    with pytest.raises(ValueError) as info:  # noqa: PT011
        create_app()
    assert "dummy-unit-tests" not in str(info.value)
