"""SR-060 / THR-102: 64 KB, profondita' JSON 10; Content-Type JSON sulle scritture (415)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

MAX_BYTES = 64 * 1024
JSON = {"Content-Type": "application/json"}


def json_of_size(n: int) -> bytes:
    prefix, suffix = b'{"pad":"', b'"}'
    return prefix + b"a" * (n - len(prefix) - len(suffix)) + suffix


def nested_objects(depth: int) -> bytes:
    """`depth` contenitori annidati, il piu' esterno conta 1."""
    return b'{"a":' * (depth - 1) + b"{}" + b"}" * (depth - 1)


def nested_arrays(depth: int) -> bytes:
    return b"[" * depth + b"]" * depth


def test_body_at_limit_is_accepted(probe_client: TestClient) -> None:
    body = json_of_size(MAX_BYTES)
    assert len(body) == MAX_BYTES
    assert probe_client.post("/_probe/echo", content=body, headers=JSON).status_code == 200


@pytest.mark.parametrize("size", [MAX_BYTES + 1, 65 * 1024, 1024 * 1024])
def test_oversized_body_is_413(probe_client: TestClient, size: int) -> None:
    resp = probe_client.post("/_probe/echo", content=json_of_size(size), headers=JSON)
    assert resp.status_code == 413
    body = resp.json()
    assert body["code"] == "payload_too_large"
    assert body["params"] == {"maxBytes": MAX_BYTES}
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_oversized_chunked_body_without_content_length_is_413(probe_client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"pad":"'
        for _ in range(70):
            yield b"a" * 1024
        yield b'"}'

    resp = probe_client.post("/_probe/echo", content=chunks(), headers=JSON)
    assert resp.status_code == 413
    assert resp.json()["code"] == "payload_too_large"


def test_oversized_body_never_reaches_handler(
    probe_client: TestClient, probe_calls: list[str]
) -> None:
    probe_client.post("/_probe/echo", content=json_of_size(MAX_BYTES + 1), headers=JSON)
    assert probe_calls == []


@pytest.mark.parametrize("builder", [nested_objects, nested_arrays])
def test_depth_10_is_accepted(probe_client: TestClient, builder: Callable[[int], Any]) -> None:
    assert probe_client.post("/_probe/echo", content=builder(10), headers=JSON).status_code == 200


@pytest.mark.parametrize("builder", [nested_objects, nested_arrays])
@pytest.mark.parametrize("depth", [11, 25, 5000, 30000])
def test_deep_json_is_422_validation_never_500(
    probe_client: TestClient,
    builder: Callable[[int], Any],
    depth: int,
) -> None:
    resp = probe_client.post("/_probe/echo", content=builder(depth), headers=JSON)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/html",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/jsonx",
        "application/vnd.api+json",
        "application/xml",
    ],
)
def test_unsafe_method_without_json_content_type_is_415(
    probe_client: TestClient, method: str, content_type: str
) -> None:
    resp = probe_client.request(
        method, "/_probe/echo", content=b'{"a": 1}', headers={"Content-Type": content_type}
    )
    assert resp.status_code == 415
    assert resp.json()["code"] == "unsupported_media_type"


def test_unsafe_method_without_content_type_is_415(
    probe_client: TestClient, probe_calls: list[str]
) -> None:
    resp = probe_client.post("/_probe/echo", content=b'{"a": 1}')
    assert resp.status_code == 415
    assert probe_calls == []


@pytest.mark.parametrize(
    "content_type", ["application/json", "application/json; charset=utf-8", "APPLICATION/JSON"]
)
def test_json_content_type_variants_are_accepted(
    probe_client: TestClient, content_type: str
) -> None:
    resp = probe_client.post(
        "/_probe/echo", content=b'{"a": 1}', headers={"Content-Type": content_type}
    )
    assert resp.status_code == 200


def test_safe_method_is_not_subject_to_content_type_rule(probe_client: TestClient) -> None:
    resp = probe_client.get("/_probe/read", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 200


def _hidden_nesting(depth: int) -> str:
    """U+2200 contiene il byte 0x22 (`"`) in UTF-16LE: sfalsava la scansione dei byte."""
    return '["\u2200",' + "[" * depth + "]" * depth + ',"\u2200"]'


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"])
@pytest.mark.parametrize("depth", [11, 5000])
def test_non_utf8_hidden_deep_json_is_422_and_never_reaches_handler(
    probe_client: TestClient, probe_calls: list[str], encoding: str, depth: int
) -> None:
    body = _hidden_nesting(depth).encode(encoding)
    resp = probe_client.post("/_probe/echo", content=body, headers=JSON)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation"
    assert probe_calls == []


def test_utf16_with_bom_is_rejected(probe_client: TestClient, probe_calls: list[str]) -> None:
    resp = probe_client.post("/_probe/echo", content='{"a":1}'.encode("utf-16"), headers=JSON)
    assert resp.status_code == 422
    assert probe_calls == []


def test_oversized_utf16_deep_body_is_422_not_handler(
    probe_client: TestClient, probe_calls: list[str]
) -> None:
    body = _hidden_nesting(40000).encode("utf-16-le")
    assert len(body) > MAX_BYTES
    resp = probe_client.post("/_probe/echo", content=body, headers=JSON)
    assert resp.status_code == 422
    assert probe_calls == []


@pytest.mark.parametrize("charset", ["utf-16", "utf-32", "latin-1", "UTF-16LE"])
def test_non_utf8_charset_is_415(
    probe_client: TestClient, probe_calls: list[str], charset: str
) -> None:
    resp = probe_client.post(
        "/_probe/echo",
        content=b'{"a":1}',
        headers={"Content-Type": f"application/json; charset={charset}"},
    )
    assert resp.status_code == 415
    assert resp.json()["code"] == "unsupported_media_type"
    assert probe_calls == []


def test_quoted_utf8_charset_is_accepted(probe_client: TestClient) -> None:
    resp = probe_client.post(
        "/_probe/echo",
        content=b'{"a":1}',
        headers={"Content-Type": 'application/json; charset="UTF-8"'},
    )
    assert resp.status_code == 200
