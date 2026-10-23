"""SL-01, livello `container`: l'immagine unica serve la SPA compilata (piano §1, §6.2).

Costruisce l'immagine reale, la avvia in sola lettura con un database fittizio (il pool è
pigro: `/` e gli asset non toccano il database) e controlla la risposta HTTP vera:
build presente, `lang="it"`, header di sicurezza, cache di SR-046, nessun file di test.
"""

import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator

import pytest

from support.paths import REPO
from support.ratelimit import PEPPER_A

DUMMY_DB = (
    "postgresql+psycopg://menu_app:" + "dummy-container-test" + "@localhost:1/menu"
    "?sslmode=verify-full&sslrootcert=/nonexistent/ca.crt"
)


def _docker(*args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["docker", *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@pytest.fixture(scope="module")
def web_image() -> str:
    if shutil.which("docker") is None:
        pytest.fail("docker non disponibile: il livello container non è verificabile")
    tag = f"menu-design-web-test:{uuid.uuid4().hex[:8]}"
    build = _docker("build", "-t", tag, "-f", str(REPO / "Dockerfile"), str(REPO))
    assert build.returncode == 0, build.stderr[-3000:]
    return tag


@pytest.fixture(scope="module")
def base_url(web_image: str) -> Iterator[str]:
    run = _docker(
        "run", "-d", "--rm", "--read-only", "--tmpfs", "/tmp",  # noqa: S108
        "-p", "127.0.0.1::8000",
        "-e", "APP_ENV=test", "-e", f"DATABASE_URL_APP={DUMMY_DB}",
        "-e", "TRUSTED_PROXY_HOPS=0", "-e", f"SESSION_PEPPER={PEPPER_A}",  # SL-03b: senza default
        web_image,
    )  # fmt: skip
    assert run.returncode == 0, run.stderr
    cid = run.stdout.strip()
    try:
        port = _docker("port", cid, "8000/tcp").stdout.strip().rsplit(":", 1)[-1]
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(url + "/", timeout=2)  # noqa: S310
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                time.sleep(0.5)
        yield url
    finally:
        _docker("rm", "-f", cid)


def _get(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers or {})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()


@pytest.mark.container
def test_image_serves_the_spa_index_with_security_headers(base_url: str) -> None:
    status, headers, body = _get(base_url + "/")
    assert status == 200
    html = body.decode()
    assert '<html lang="it"' in html
    assert 'id="root"' in html
    assert "no-cache" in headers["cache-control"]
    assert "require-trusted-types-for 'script'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"


@pytest.mark.container
def test_image_serves_hashed_assets_immutable_and_gzip(base_url: str) -> None:
    _, _, body = _get(base_url + "/")
    scripts = re.findall(r'src="(/assets/[^"]+\.js)"', body.decode())
    assert scripts, "index.html non referenzia uno script in /assets/"
    status, headers, _ = _get(base_url + scripts[0], {"Accept-Encoding": "gzip"})
    assert status == 200
    assert "immutable" in headers["cache-control"]
    assert headers.get("content-encoding") == "gzip"


@pytest.mark.container
def test_image_spa_fallback_and_api_404_are_distinct(base_url: str) -> None:
    status, headers, body = _get(base_url + "/accedi")
    assert status == 200
    assert b'id="root"' in body
    status, headers, body = _get(base_url + "/api/v1/missing")
    assert status == 404
    assert headers["content-type"].startswith("application/problem+json")
    assert json.loads(body)["code"] == "not_found"


@pytest.mark.container
def test_image_does_not_ship_sources_sourcemaps_or_node(web_image: str) -> None:
    listing = _docker(
        "run", "--rm", "--entrypoint", "sh", web_image, "-c",
        "find / -xdev \\( -name '*.map' -o -name node_modules -o -name 'pnpm*' "
        "-o -name 'package.json' -path '*web*' \\) -not -path '/proc/*' "
        "-not -path '/usr/local/lib/python*' -not -path '/app/.venv/*' 2>/dev/null | head",
    )  # fmt: skip
    assert listing.stdout.strip() == "", listing.stdout
