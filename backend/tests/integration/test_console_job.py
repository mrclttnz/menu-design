"""Job della console `python -m menu console <comando>` sul database di test (ADR-0011).
SL-02. US-002: AC-002.1 (famiglia creata, evento nel registro), AC-002.2 (errori: nulla creato),
AC-002.3 (output solo ID e nome). SR-012, SR-020, SR-021, SR-040. THR-053, THR-051.

Contratto assunto (nel report di slice; da confermare con il backend-developer):
- il job legge `DATABASE_URL_CONSOLE` (ruolo `menu_console`, verify-full) e NON ha bisogno di
  `DATABASE_URL_APP`; `APP_ENV=test`;
- comandi (argv del job = elenco di `--args` del client): `family bootstrap --name N
  --email-sha256 HEX64`, `audit note --ref R`, `security-log --since ISO`;
- `--email-sha256` accetta solo `^[0-9a-f]{64}$`; un valore non valido (un'email, esadecimale
  maiuscolo, lunghezza errata) fa fallire il job SENZA ripeterlo in stdout/stderr (i log dei job
  Cloud Run conservano l'output: nessun dato personale);
- esito: codice di uscita 0 e stdout con ID e nome della famiglia; errore: codice != 0.
"""

import os
import re
import subprocess
import sys
from collections.abc import Callable
from uuid import UUID

import pytest

from menu.common import email_sha256
from support import pg
from support.owner import Owner
from support.paths import BACKEND

pytestmark = pytest.mark.integration

Job = Callable[..., subprocess.CompletedProcess[str]]

EMAIL = "Canary.Gestore+uno@Example.test"
HEX64 = re.compile(r"[0-9a-f]{64}")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def job(worker_db: str) -> Job:
    url = pg.cluster().role_url("menu_console", worker_db, sqlalchemy=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "APP_ENV": "test",
        "DATABASE_URL_CONSOLE": url,
    }

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-I", "-m", "menu", "console", *args],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    return run


def _no_secrets(out: str, worker_db: str) -> None:
    low = out.lower()
    assert "canary.gestore" not in low
    assert "example.test" not in low
    assert pg.TEST_ROLE_PASSWORD not in out, "la password del database non compare mai"
    assert "postgresql://" not in low
    assert not HEX64.search(low), "nemmeno l'hash dell'email nell'output"


def test_ac_002_1_and_2_3_bootstrap_job_creates_the_family_and_prints_only_the_family_id(
    job: Job, owner: Owner, worker_db: str
) -> None:
    done = job(
        "family",
        "bootstrap",
        "--name",
        "Famiglia Alfa",
        "--email-sha256",
        email_sha256(EMAIL).hex(),
    )
    assert done.returncode == 0, done.stderr
    ids = UUID_RE.findall(done.stdout)
    assert len(ids) == 1, done.stdout
    assert re.fullmatch(r"[0-9a-f-]{36}\n", done.stdout), "solo l'ID (ADR-0011, piano §4.4)"
    _no_secrets(done.stdout + done.stderr, worker_db)

    family = UUID(ids[0])
    assert owner.scalar("select name from app.family where id = %s", (family,)) == "Famiglia Alfa"
    stored = owner.scalar(
        "select email_sha256 from app.family_bootstrap where family_id = %s", (family,)
    )
    assert bytes(stored) == email_sha256(EMAIL)
    event = owner.rows(
        "select event_type, outcome, actor_kind, family_id from app.security_event "
        "where event_type = 'console.family_bootstrap'"
    )
    assert event == [("console.family_bootstrap", "success", "platform_operator", family)]


@pytest.mark.parametrize(
    "bad_hash",
    [
        pytest.param(email_sha256(EMAIL).hex().upper(), id="maiuscolo"),
        pytest.param(email_sha256(EMAIL).hex()[:-1], id="63-caratteri"),
        pytest.param(email_sha256(EMAIL).hex() + "0", id="65-caratteri"),
        pytest.param(EMAIL, id="email-in-chiaro"),
        pytest.param("", id="vuoto"),
    ],
)
def test_ac_002_2_invalid_hash_fails_creates_nothing_and_does_not_echo_the_value(
    job: Job, owner: Owner, worker_db: str, bad_hash: str
) -> None:
    done = job("family", "bootstrap", "--name", "Famiglia Alfa", "--email-sha256", bad_hash)
    assert done.returncode != 0
    assert owner.scalar("select count(*) from app.family") == 0
    assert owner.scalar("select count(*) from app.family_bootstrap") == 0
    _no_secrets(done.stdout + done.stderr, worker_db)


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["family", "bootstrap", "--email-sha256", "00" * 32], id="senza-nome"),
        pytest.param(["family", "bootstrap", "--name", "Famiglia Alfa"], id="senza-hash"),
        pytest.param(
            ["family", "bootstrap", "--name", "N" * 61, "--email-sha256", "00" * 32],
            id="nome-troppo-lungo",
        ),
        pytest.param(
            ["family", "bootstrap", "--name", "", "--email-sha256", "00" * 32], id="nome-vuoto"
        ),
        pytest.param(
            ["family", "bootstrap", "--name", "A", "--email", EMAIL], id="opzione-email-ignota"
        ),
    ],
)
def test_ac_002_2_bad_arguments_fail_and_create_nothing(
    job: Job, owner: Owner, worker_db: str, args: list[str]
) -> None:
    done = job(*args)
    assert done.returncode != 0
    assert owner.scalar("select count(*) from app.family") == 0
    assert owner.scalar("select count(*) from app.course") == 0
    assert pg.TEST_ROLE_PASSWORD not in done.stdout + done.stderr


def test_audit_note_job_records_the_event(job: Job, owner: Owner) -> None:
    done = job("audit", "note", "--ref", "AUD-20261022-1")
    assert done.returncode == 0, done.stderr
    assert owner.rows(
        "select outcome, actor_kind from app.security_event where event_type = 'console.audit_note'"
    ) == [("success", "platform_operator")]


def test_audit_note_job_rejects_a_malformed_ref(job: Job, owner: Owner) -> None:
    done = job("audit", "note", "--ref", "mario.rossi@example.test")
    assert done.returncode != 0
    assert "mario.rossi" not in (done.stdout + done.stderr).lower()
    assert owner.scalar("select count(*) from app.security_event") == 0


def test_security_log_job_lists_events_without_personal_data(
    job: Job, owner: Owner, worker_db: str
) -> None:
    job(
        "family",
        "bootstrap",
        "--name",
        "Famiglia Alfa",
        "--email-sha256",
        email_sha256(EMAIL).hex(),
    )
    done = job("security-log", "--since", "2000-01-01T00:00:00Z")
    assert done.returncode == 0, done.stderr
    assert "console.family_bootstrap" in done.stdout
    _no_secrets(done.stdout + done.stderr, worker_db)


def test_job_cannot_run_with_the_application_role(worker_db: str, owner: Owner) -> None:
    """Minimo privilegio (SR-040): con le credenziali di `menu_app` il job non crea nulla,
    perché `menu_app` non può eseguire le funzioni `console_*`."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "APP_ENV": "test",
        "DATABASE_URL_CONSOLE": pg.cluster().role_url("menu_app", worker_db, sqlalchemy=True),
    }
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-m", "menu", "console", "family", "bootstrap",
         "--name", "Famiglia Alfa", "--email-sha256", "00" * 32],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip
    assert done.returncode != 0
    assert owner.scalar("select count(*) from app.family") == 0
