"""Caricamento della matrice dei permessi dei test e dello schema OpenAPI (08 §6.1, §7.1)."""

from pathlib import Path
from typing import Any

import yaml

HTTP_METHODS = ("get", "put", "post", "delete", "patch")
PATH = Path(__file__).resolve().parents[1] / "security" / "authz_matrix.yaml"


def _load() -> dict[str, Any]:
    loaded = yaml.safe_load(PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


_DOC = _load()
MATRIX: dict[str, dict[str, Any]] = _DOC["operations"]
FUTURE: dict[str, dict[str, Any]] = _DOC["future"]


def operations_of(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method, path, op)
        for path, item in schema.get("paths", {}).items()
        for method, op in item.items()
        if method in HTTP_METHODS
    ]
