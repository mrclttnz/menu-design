"""Script locale del Gestore (strato 11, ADR-0011, piano §4.4): lancia il job `menu-console`.

Solo libreria standard e `menu.common.email_sha256`. L'email si chiede solo con un prompt senza
eco, non è mai un'opzione né compare nei messaggi: al job arriva l'hash esadecimale (SR-012).
Gli errori di validazione terminano con codice diverso da 0 prima di avviare qualunque comando.
`gcloud` divide `--args` sulle virgole: un nome di famiglia che ne contiene una è rifiutato.
"""

import argparse
import getpass
import re
import subprocess  # nosec B404
import sys
import unicodedata
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, NoReturn

from menu.common import email_sha256

JOB = "menu-console"
REGION = "europe-west3"
NAME_MAX = 60
EMAIL_MAX = 254
EXIT_USAGE = 2
EXIT_JOB_FAILED = 1
_REF = re.compile(r"[A-Z]{2,5}-[0-9]{8}-[0-9]{1,3}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
_SINCE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})")

# `subprocess` solo con argomenti in lista, senza shell (security-standard §3).
Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Prompt = Callable[[str], str]


class _UsageError(Exception):
    """Messaggio fisso e generico: mai il valore ricevuto."""


class _Parser(argparse.ArgumentParser):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(allow_abbrev=False, **kwargs)

    def error(self, message: str) -> NoReturn:
        # Il testo di argparse cita i valori (un `--email` digitato): non lo si mostra.
        raise _UsageError("argomenti non validi (vedere --help)")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="console")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    family = commands.add_parser("family").add_subparsers(
        dest="sub", required=True, parser_class=_Parser
    )
    family.add_parser("bootstrap").add_argument("--name", required=True)
    commands.add_parser("audit").add_subparsers(
        dest="sub", required=True, parser_class=_Parser
    ).add_parser("note").add_argument("--ref", required=True)
    commands.add_parser("security-log").add_argument("--since", required=True)
    return parser


def _valid_name(name: str) -> str:
    if not name.strip() or len(name) > NAME_MAX:
        raise _UsageError(f"il nome deve avere da 1 a {NAME_MAX} caratteri")
    if "," in name:
        raise _UsageError("il nome non può contenere virgole (gcloud le usa per separare --args)")
    if any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in name):
        raise _UsageError("il nome non può contenere caratteri di controllo")
    return name


def _valid_since(since: str) -> str:
    if not _SINCE.fullmatch(since):
        raise _UsageError("--since richiede data e ora ISO 8601 con fuso, es. 2026-10-01T00:00:00Z")
    try:
        datetime.fromisoformat(since)
    except ValueError:
        raise _UsageError("--since non è una data valida") from None
    return since


def _job_args(args: argparse.Namespace, prompt: Prompt) -> list[str]:
    if args.command == "family":
        name = _valid_name(args.name)
        typed = prompt("Email del Gestore (non viene mostrata): ").strip()
        if len(typed) > EMAIL_MAX or not _EMAIL.fullmatch(typed):
            raise _UsageError("l'email non è valida")
        return ["family", "bootstrap", "--name", name, "--email-sha256", email_sha256(typed).hex()]
    if args.command == "audit":
        if not _REF.fullmatch(args.ref):
            raise _UsageError("--ref non rispetta il formato AAA-AAAAMMGG-N")
        return ["audit", "note", "--ref", args.ref]
    return ["security-log", "--since", _valid_since(args.since)]


def main(
    argv: Sequence[str] | None = None,
    *,
    prompt: Prompt | None = None,
    runner: Runner = subprocess.run,
) -> int:
    ask: Prompt = prompt if prompt is not None else (lambda text: getpass.getpass(text))
    try:
        parsed = _parser().parse_args(argv)
        job_args = _job_args(parsed, ask)
    except _UsageError as error:
        sys.stderr.write(f"errore: {error}\n")
        return EXIT_USAGE
    command = [
        "gcloud", "run", "jobs", "execute", JOB,
        f"--region={REGION}", "--wait", f"--args={','.join(job_args)}",
    ]  # fmt: skip
    try:
        done: Any = runner(command, capture_output=True, text=True, check=False)
    except OSError:
        sys.stderr.write("errore: impossibile eseguire gcloud (installato e nel PATH?)\n")
        return EXIT_JOB_FAILED
    if done.returncode != 0:
        # Lo stderr di gcloud (autenticazione, job non trovato, regione) non contiene l'email.
        sys.stderr.write((done.stderr or "").strip()[-2000:] + "\n")
        sys.stderr.write(f"errore: il job {JOB} è fallito (vedere i log di Cloud Run)\n")
        return EXIT_JOB_FAILED
    # `gcloud ... --wait` riporta solo lo stato dell'esecuzione: l'output del job (ID, eventi) è
    # nei log di Cloud Run. La lettura automatica è rinviata a SL-10b (piano §4.4).
    sys.stdout.write(
        f"Esecuzione di {JOB} completata. L'esito va letto dai log del job Cloud Run "
        f"(job {JOB}, regione {REGION}).\n"
    )
    return 0
