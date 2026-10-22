"""Punto d'ingresso di `python -m menu seed --dataset X` (strato 12 nella pratica, A-22).

La guardia gira prima di qualsiasi connessione; i test usano la libreria dei dataset, mai
questo modulo (08 §14.1).
"""

import os
import sys
from collections.abc import Mapping

from menu.seeding.guard import SeedNotAllowed, assert_seed_allowed

EXIT_REFUSED = 2
EXIT_UNAVAILABLE = 1


def run(dataset: str, environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    try:
        assert_seed_allowed(
            app_env=env.get("APP_ENV"),
            database_url=env.get("DATABASE_URL_OWNER"),
            seed_target=env.get("SEED_TARGET"),
            allowed_hosts=env.get("SEED_ALLOWED_DB_HOSTS"),
        )
    except SeedNotAllowed as error:
        sys.stderr.write(f"seed refused: {error}\n")
        return EXIT_REFUSED
    sys.stderr.write(f"seed: la libreria dei dataset non esiste ancora ({dataset})\n")
    return EXIT_UNAVAILABLE
