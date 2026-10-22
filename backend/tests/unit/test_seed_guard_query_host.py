"""SEC-SL00b-001 (THR-133): l'URL non può sostituire l'host con parametri di libpq."""

import pytest

from menu.seeding.guard import SeedNotAllowed, assert_seed_allowed

PW = "CANARY-QUERYHOST-PW"


@pytest.mark.parametrize(
    "query",
    [
        "host=db.example.test",
        "sslmode=verify-full&host=db.example.test",
        "hostaddr=203.0.113.9",
        "service=prod",
        "HOST=db.example.test",
        "host=",
    ],
)
def test_guard_refuses_urls_that_override_the_host_in_the_query(query: str) -> None:
    url = f"postgresql+psycopg://menu_owner:{PW}@localhost:5432/menu?{query}"
    with pytest.raises(SeedNotAllowed) as info:
        assert_seed_allowed(
            app_env="dev", database_url=url, seed_target="local", allowed_hosts="localhost"
        )
    assert PW not in str(info.value)
    assert PW not in repr(info.value)


def test_guard_still_allows_a_plain_url_with_ssl_parameters() -> None:
    url = (
        f"postgresql+psycopg://menu_owner:{PW}@localhost:5432/menu"
        "?sslmode=verify-full&sslrootcert=/ca.crt"
    )
    assert_seed_allowed(
        app_env="dev", database_url=url, seed_target="local", allowed_hosts="localhost"
    )
