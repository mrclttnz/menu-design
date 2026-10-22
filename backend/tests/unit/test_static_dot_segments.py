"""Regressione THR-074: nessun segmento che inizia con un punto arriva al fallback SPA."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from support.assets import build_dist


@pytest.fixture
def client(app_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from menu.app import create_app

    monkeypatch.setenv("WEB_DIST_DIR", str(build_dist(tmp_path)))
    with TestClient(
        create_app(), base_url="https://testserver", raise_server_exceptions=False
    ) as c:
        yield c


@pytest.mark.parametrize(
    "path", ["/.git/config", "/.env/x", "/a/.hidden/b", "/.well-known/x", "/piano/.git/"]
)
def test_dot_prefixed_segments_are_not_spa_routes(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code in {400, 404}
    assert '<div id="root">' not in r.text


def test_dotless_spa_route_still_falls_back(client: TestClient) -> None:
    assert client.get("/piano/2026-10-19").status_code == 200
