"""Script locale del Gestore `menu.console_client` (ADR-0011; plan §4.4). SL-02.

US-002: AC-002.1 (comando di bootstrap), AC-002.2 (errori: nulla viene eseguito), AC-002.3
(output senza segreti). SR-012, SR-021, SR-040. THR-053, I-03.

Contratto assunto (nel report di slice; da confermare con il backend-developer):
- `menu.console_client.main(argv, *, prompt=getpass.getpass, runner=subprocess.run) -> int`;
- `runner(args: list[str])` esegue `gcloud run jobs execute menu-console --region=europe-west3
  --wait --args=<comando>,...` e restituisce un `subprocess.CompletedProcess[str]` con l'esito;
- comandi: `family bootstrap --name N`, `audit note --ref R`, `security-log --since ISO`;
- l'email si chiede SOLO con `prompt` (di default `getpass.getpass`, mai `input`), non esiste
  un'opzione `--email`; al job arriva l'hash esadecimale minuscolo di 64 caratteri;
- gli errori restituiscono un codice diverso da 0 (o `SystemExit` non nullo) PRIMA di chiamare
  `runner`.
Nessun test lancia `gcloud` né apre la rete: `runner` è sempre un finto registratore.
"""

import getpass
import hashlib
import importlib
import re
import subprocess
import sys
from typing import Any

import pytest

from menu.common import email_sha256

FAMILY_ID = "0b4e1f0e-5c53-4f6a-9d0e-1d2c3b4a5f60"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
GOOD_REF = "AUD-20261022-1"

# (email digitata, SHA-256 atteso). Valori ricavati dalla definizione di ADR-0011
# (strip, lower, UTF-8, SHA-256) e fissati qui: se la normalizzazione cambia, il test fallisce.
ALICE = "a1d2bed7873afe14249af666691d6b35b1ff33c584d86628c8669791e1331bd2"
GOLDEN = [
    ("alice.alfa@example.test", ALICE),
    ("Alice.Alfa@Example.TEST", ALICE),
    ("  alice.alfa@example.test\n", ALICE),
    (
        "Zoë.Ünïcode@example.test",
        "c4a74782652496bd1dee4b34d33818e9ff6b2a62c551c3fcbf2557111de7deda",
    ),
    ("ÉLISA@EXAMPLE.TEST", "0037302e11846c01b5e1cbc4a23fe955a75f045dbd09a2e68fee8834984bd56a"),
]


class Recorder:
    """Finto `runner`: registra gli argomenti; gcloud riporta solo lo stato dell'esecuzione."""

    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "Execution [menu-console-abc12] has successfully completed.\n",
    ) -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""

    def __call__(self, args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, self.stderr)

    def tokens(self) -> list[str]:
        """Argomenti spezzati anche su `=` e `,` (formato `--args=cmd,a,b`)."""
        out: list[str] = []
        for call in self.calls:
            for arg in call:
                out += [t for t in re.split(r"[=,]", arg) if t]
        return out


def _run(argv: list[str], email: str | None, recorder: Recorder) -> int:
    main: Any = importlib.import_module("menu.console_client").main

    def prompt(_: str) -> str:
        if email is None:
            raise AssertionError("l'email non doveva essere richiesta")
        return email

    try:
        return int(main(argv, prompt=prompt, runner=recorder))
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1


# --- AC-002.1: argomenti del job ----


def test_ac_002_1_bootstrap_sends_only_name_and_email_hash() -> None:
    rec = Recorder()
    email = "Marco.Gestore@Example.test"
    code = _run(["family", "bootstrap", "--name", "Famiglia Alfa"], email, rec)
    assert code == 0
    assert len(rec.calls) == 1
    call = rec.calls[0]
    assert call[:5] == ["gcloud", "run", "jobs", "execute", "menu-console"]
    assert "--region=europe-west3" in call
    assert "--wait" in call
    assert sum(a.startswith("--args=") for a in call) == 1
    args = next(a for a in call if a.startswith("--args="))[len("--args=") :]
    assert args.split(",") == [
        "family",
        "bootstrap",
        "--name",
        "Famiglia Alfa",
        "--email-sha256",
        email_sha256(email).hex(),
    ], "argv del job (contratto con `python -m menu console`, vedi test di integrazione)"
    tokens = rec.tokens()
    hashes = [t for t in tokens if HEX64.match(t)]
    assert hashes == [email_sha256(email).hex()], "esattamente un hash esadecimale minuscolo"
    assert "Famiglia Alfa" in " ".join(call)
    blob = " ".join(call).lower()
    assert "marco.gestore" not in blob
    assert "example.test" not in blob
    assert "@" not in blob


def test_ac_002_3_client_output_points_to_the_job_logs_without_the_email(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """CR-SL02-002: l'esito del job è nei log di Cloud Run; lo stdout di gcloud non è l'esito."""
    caplog.set_level("DEBUG")
    rec = Recorder(stdout=f"Execution [x] done. {FAMILY_ID}\n")
    argv = ["family", "bootstrap", "--name", "Famiglia Alfa"]
    code = _run(argv, "marco.gestore@example.test", rec)
    assert code == 0
    seen = capsys.readouterr()
    assert "log" in seen.out.lower()
    assert FAMILY_ID not in seen.out, "lo stdout di gcloud non si spaccia per l'esito del job"
    everything = (seen.out + seen.err + caplog.text).lower()
    assert "marco.gestore" not in everything
    assert "example.test" not in everything


def test_email_is_read_with_getpass_and_never_with_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0011: prompt senza eco, così l'email non finisce nella cronologia della shell."""
    main: Any = importlib.import_module("menu.console_client").main

    asked: list[str] = []

    def fake_getpass(*_: object, **__: object) -> str:
        asked.append("getpass")
        return "a@example.test"

    monkeypatch.setattr(getpass, "getpass", fake_getpass)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("input() non va usato"))
    rec = Recorder()
    assert main(["family", "bootstrap", "--name", "Famiglia Alfa"], runner=rec) == 0
    assert asked == ["getpass"]
    assert len(rec.calls) == 1


@pytest.mark.parametrize(("typed", "digest"), GOLDEN)
def test_email_hash_in_job_args_is_the_adr_0011_normalized_sha256(typed: str, digest: str) -> None:
    """I-03: stessa normalizzazione (strip, lower, UTF-8) tra script e servizio."""
    rec = Recorder()
    assert _run(["family", "bootstrap", "--name", "Famiglia Alfa"], typed, rec) == 0
    assert [t for t in rec.tokens() if HEX64.match(t)] == [digest]
    assert email_sha256(typed).hex() == digest, "il servizio calcola lo stesso valore"
    assert hashlib.sha256(typed.strip().lower().encode("utf-8")).hexdigest() == digest


# --- AC-002.2: errori, nessuna esecuzione ----


def test_ac_002_2_missing_name_fails_without_running_anything() -> None:
    rec = Recorder()
    assert _run(["family", "bootstrap"], "a@example.test", rec) != 0
    assert rec.calls == []


@pytest.mark.parametrize(
    "typed",
    ["", "   ", "plainaddress", "@example.test", "a@", "a b@example.test", "a@@example.test",
     "CANARY-NOT-AN-EMAIL"],
)  # fmt: skip
def test_ac_002_2_invalid_email_fails_without_running_or_echoing(
    typed: str, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = Recorder()
    assert _run(["family", "bootstrap", "--name", "Famiglia Alfa"], typed, rec) != 0
    assert rec.calls == []
    seen = capsys.readouterr()
    assert "CANARY-NOT-AN-EMAIL" not in seen.out + seen.err, "il valore digitato non si ripete"


def test_there_is_no_email_option_on_the_command_line() -> None:
    """L'email solo al prompt: un `--email` è rifiutato e nulla viene eseguito."""
    rec = Recorder()
    argv = ["family", "bootstrap", "--name", "Famiglia Alfa", "--email", "a@example.test"]
    assert _run(argv, "a@example.test", rec) != 0
    assert rec.calls == []


def test_a_failing_job_makes_the_command_fail_and_shows_gcloud_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rec = Recorder(returncode=1, stdout="")
    rec.stderr = "ERROR: (gcloud.run.jobs.execute) You do not currently have an active account"
    assert _run(["family", "bootstrap", "--name", "Famiglia Alfa"], "a@example.test", rec) == 1
    seen = capsys.readouterr()
    assert "active account" in seen.err
    assert "a@example.test" not in seen.out + seen.err


def test_missing_gcloud_is_a_clean_error_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main: Any = importlib.import_module("menu.console_client").main

    def missing(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(args)

    code = main(
        ["family", "bootstrap", "--name", "Famiglia Alfa"],
        prompt=lambda _: "a@example.test",
        runner=missing,
    )
    seen = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in seen.err
    assert "gcloud" in seen.err
    assert email_sha256("a@example.test").hex() not in seen.out + seen.err


def test_abbreviated_options_are_rejected() -> None:
    rec = Recorder()
    assert _run(["family", "bootstrap", "--na", "Famiglia Alfa"], "a@example.test", rec) == 2
    assert rec.calls == []


@pytest.mark.parametrize("bad", ["Rossi\x7fX", "Rossi\x85X", "Rossi\u2028X", "Rossi\u2029X"])
def test_name_with_control_or_line_separator_characters_is_rejected(bad: str) -> None:
    rec = Recorder()
    assert _run(["family", "bootstrap", "--name", bad], "a@example.test", rec) == 2
    assert rec.calls == []


def test_the_operator_command_is_runnable_as_a_module() -> None:
    """CR-SL02-001: `python -m menu.console_client` esiste davvero (subprocess, senza gcloud)."""
    base = [sys.executable, "-I", "-m", "menu.console_client"]
    helped = subprocess.run([*base, "--help"], capture_output=True, text=True, check=False)  # noqa: S603
    assert helped.returncode == 0
    assert "usage" in helped.stdout.lower()
    bare = subprocess.run(base, capture_output=True, text=True, check=False)  # noqa: S603
    assert bare.returncode == 2
    assert "Traceback" not in bare.stderr


# --- altri comandi di SL-02 ----


def test_audit_note_sends_only_the_validated_request_ref() -> None:
    rec = Recorder(stdout="ok\n")
    assert _run(["audit", "note", "--ref", GOOD_REF], None, rec) == 0
    assert GOOD_REF in rec.tokens()
    assert len(rec.calls) == 1


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "aud-20261022-1",
        "AUD-2026102-1",
        "A-20261022-1",
        "mario@example.test",
        "AUD-20261022-1234",
    ],
)
def test_audit_note_rejects_a_malformed_request_ref_before_running(ref: str) -> None:
    """ADR-0011: `^[A-Z]{2,5}-[0-9]{8}-[0-9]{1,3}$` validato anche dallo script."""
    rec = Recorder()
    assert _run(["audit", "note", "--ref", ref], None, rec) != 0
    assert rec.calls == []


def test_security_log_never_prompts_for_an_email() -> None:
    rec = Recorder(stdout="[]\n")
    assert _run(["security-log", "--since", "2026-10-01T00:00:00Z"], None, rec) == 0
    assert "2026-10-01T00:00:00Z" in " ".join(rec.calls[0])
