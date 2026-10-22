"""CR-SL00a-007: il limite di dimensione non deve fallire aperto senza `Content-Length`.

Test a livello ASGI: nessun header di lunghezza né `Transfer-Encoding` (come con HTTP/2),
più messaggi `http.request` per oltre 64 KB → `413` e handler mai eseguito.
"""

import json
from typing import Any

import pytest

from menu.app import create_app
from support.probe import build_probe_router


async def _call(app: Any, headers: list[tuple[bytes, bytes]], chunks: list[bytes]) -> int:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "2",
        "method": "POST",
        "scheme": "https",
        "path": "/_probe/echo",
        "raw_path": b"/_probe/echo",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
    }
    queue = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]
    status: list[int] = []

    async def receive() -> dict[str, Any]:
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            status.append(message["status"])

    await app(scope, receive, send)
    return status[0]


@pytest.mark.anyio
async def test_oversized_streamed_body_without_content_length_is_413(
    app_env: None, probe_calls: list[str]
) -> None:
    app = create_app(extra_routers=[build_probe_router(probe_calls)])
    chunk = b"x" * 16_384
    status = await _call(app, [(b"content-type", b"application/json")], [chunk] * 6)
    assert status == 413
    assert probe_calls == []


@pytest.mark.anyio
async def test_small_streamed_body_without_content_length_is_still_accepted(
    app_env: None, probe_calls: list[str]
) -> None:
    app = create_app(extra_routers=[build_probe_router(probe_calls)])
    body = json.dumps({"a": 1}).encode()
    status = await _call(app, [(b"content-type", b"application/json")], [body])
    assert status == 200
    assert probe_calls == ["echo_post"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
