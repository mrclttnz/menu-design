"""CR-SL00a-012b: il server reale non scrive query string o valori sensibili su stdout/stderr.

Avvia `python -m menu serve` (uvicorn con log d'accesso spento) sul database di test.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from support.paths import BACKEND, SRC

pytestmark = pytest.mark.integration

CANARY = "CANARY-QUERY-STRING-4e8"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_server_logs_requests_without_query_strings(app_url: str) -> None:
    port = _free_port()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "APP_ENV": "test",
        "TRUSTED_PROXY_HOPS": "0",
        "DATABASE_URL_APP": app_url,
        "PYTHONPATH": str(SRC.parent),
    }
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-I", "-m", "menu", "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        status = None
        while time.monotonic() < deadline and status is None:
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/healthz?code={CANARY}", timeout=2
                ) as resp:
                    status = resp.status
            except OSError:
                time.sleep(0.3)
        assert status == 200, "il server non ha risposto 200 su /healthz"
    finally:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    assert CANARY not in out, "la query string è finita nel log"
    assert '"event": "http.request"' in out, "manca il log strutturato della richiesta"
