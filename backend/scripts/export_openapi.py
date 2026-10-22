"""Scrive (o con `--check` verifica) `openapi.json` alla radice del repository.

L'app non viene avviata: serve solo lo schema, quindi `APP_ENV` ha un valore fisso di prova.
"""

import json
import os
import sys
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["TRUSTED_PROXY_HOPS"] = "0"
os.environ.setdefault(
    "DATABASE_URL_APP",
    "postgresql+psycopg://menu_app:schema-only@localhost:1/menu"
    "?sslmode=verify-full&sslrootcert=/nonexistent/ca.crt",
)

from menu.app import create_app

TARGET = Path(__file__).resolve().parents[2] / "openapi.json"


def render() -> str:
    return json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    content = render()
    if "--check" in argv:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != content:
            sys.stderr.write("openapi.json non aggiornato: eseguire `make openapi`\n")
            return 1
        return 0
    TARGET.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
