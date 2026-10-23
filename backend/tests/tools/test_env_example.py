"""CR-SL00b-004: `.env.example` documenta la configurazione che l'app legge davvero."""

import re

import pytest

from support.paths import REPO

REQUIRED = (
    "DATABASE_URL_APP",
    "DATABASE_URL_OWNER",
    "SEED_TARGET",
    "SEED_ALLOWED_DB_HOSTS",
    # SL-03a: accesso con Google (segnaposto; `OIDC_ISSUER` predefinito = Google, ASM-073)
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "OIDC_ISSUER",
    "APP_BASE_URL",
)
OBSOLETE = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_APP_USER", "DB_APP_PASSWORD")


def env_example_problems(text: str) -> list[str]:
    names = set(re.findall(r"(?m)^#?\s*([A-Z][A-Z0-9_]+)=", text))
    problems = [f"manca {n}" for n in REQUIRED if n not in names]
    problems += [f"variabile obsoleta {n}" for n in OBSOLETE if n in names]
    if "verify-full" not in text:
        problems.append("nessun cenno a sslmode=verify-full")
    for line in text.splitlines():
        key, _, value = line.partition("=")
        sensitive = re.search(r"(?i)password|secret|pepper|database_url", key)
        if sensitive and not line.startswith("#") and value.strip() not in {"", "CHANGE_ME"}:
            problems.append(f"valore non segnaposto: {key}")
    return problems


def test_env_example_matches_the_configuration_the_app_reads() -> None:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert env_example_problems(text) == []


@pytest.mark.parametrize(
    ("old", "new", "needle"),
    [
        ("DATABASE_URL_APP=CHANGE_ME", "DB_HOST=localhost", "manca DATABASE_URL_APP"),
        ("DATABASE_URL_OWNER=CHANGE_ME", "", "manca DATABASE_URL_OWNER"),
        ("DATABASE_URL_APP=CHANGE_ME", "DATABASE_URL_APP=CHANGE_ME\nDB_APP_PASSWORD=x", "obsoleta"),
        ("DATABASE_URL_APP=CHANGE_ME", "DATABASE_URL_APP=postgresql://u:real@h/db", "segnaposto"),
        ("# SEED_TARGET=local", "", "manca SEED_TARGET"),
    ],
)
def test_env_example_check_goes_red_on_mutations(old: str, new: str, needle: str) -> None:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert old in text
    problems = env_example_problems(text.replace(old, new, 1))
    assert any(needle in p for p in problems), problems
