"""CR-SL00b-002: il 503 di /healthz è dichiarato nel contratto (piano §4.3)."""

from typing import Any


def test_healthz_documents_the_503_as_plain_json_health(generated_schema: dict[str, Any]) -> None:
    response = generated_schema["paths"]["/healthz"]["get"]["responses"]["503"]
    content = response["content"]
    assert "application/json" in content
    assert content["application/json"]["schema"] == {"$ref": "#/components/schemas/Health"}
