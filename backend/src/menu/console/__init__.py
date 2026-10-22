"""Comandi del job `menu-console` (strato 11, ADR-0011, piano §4.4): solo funzioni `console_*`.

Il job usa `DATABASE_URL_CONSOLE` (ruolo `menu_console`: nessun privilegio sulle tabelle, solo
EXECUTE sulle funzioni SECURITY DEFINER che scrivono anche l'evento di sicurezza). L'argomento
`--email-sha256` è validato prima di toccare il database e non viene mai ripetuto: i log dei
job conservano l'output. Errori: messaggio generico e codice di uscita diverso da 0.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy import text

from menu import tenancy
from menu.platform.config import check_database_url

EXIT_FAILED = 1
EXIT_USAGE = 2
SECURITY_LOG_LIMIT = 500
NAME_MAX = 60
_HASH = re.compile(r"[0-9a-f]{64}")
_REF = re.compile(r"[A-Z]{2,5}-[0-9]{8}-[0-9]{1,3}")

_BOOTSTRAP = text("select app.console_bootstrap_family(:name, :email_sha256)")
_AUDIT_NOTE = text("select app.console_audit_note(:ref)")
_SECURITY_EVENTS = text("select * from app.console_security_events(:since, :limit)")


class _UsageError(Exception):
    """Messaggio fisso: mai il valore ricevuto."""


class _Parser(argparse.ArgumentParser):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(allow_abbrev=False, **kwargs)  # type: ignore[arg-type]

    def error(self, message: str) -> NoReturn:
        raise _UsageError("argomenti non validi")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="menu console")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    family = commands.add_parser("family").add_subparsers(
        dest="sub", required=True, parser_class=_Parser
    )
    bootstrap = family.add_parser("bootstrap")
    bootstrap.add_argument("--name", required=True)
    bootstrap.add_argument("--email-sha256", required=True)
    commands.add_parser("audit").add_subparsers(
        dest="sub", required=True, parser_class=_Parser
    ).add_parser("note").add_argument("--ref", required=True)
    commands.add_parser("security-log").add_argument("--since", required=True)
    return parser


def _forbidden_char(char: str) -> bool:
    """Controllo, formato, separatori di riga (DEL, NEL, U+2028/9): niente falsi record nei log."""
    return unicodedata.category(char).startswith("C") or char in "\u2028\u2029"


def _bootstrap(args: argparse.Namespace) -> str:
    name: str = args.name
    if not name.strip() or len(name) > NAME_MAX or any(_forbidden_char(c) for c in name):
        raise _UsageError("nome della famiglia non valido")
    if not _HASH.fullmatch(args.email_sha256):
        raise _UsageError("--email-sha256 non valido (64 caratteri esadecimali minuscoli)")
    digest = bytes.fromhex(args.email_sha256)
    with tenancy.console_tx(uuid4()) as tx:
        result = tx.execute(_BOOTSTRAP, {"name": name, "email_sha256": digest})
        family_id: UUID = result.scalar_one()
    return f"{family_id}\n"


def _audit_note(args: argparse.Namespace) -> str:
    if not _REF.fullmatch(args.ref):
        raise _UsageError("--ref non rispetta il formato AAA-AAAAMMGG-N")
    with tenancy.console_tx(uuid4()) as tx:
        tx.execute(_AUDIT_NOTE, {"ref": args.ref})
    return "ok\n"


def _security_log(args: argparse.Namespace) -> str:
    try:
        since = datetime.fromisoformat(args.since)
    except ValueError:
        raise _UsageError("--since non è una data ISO 8601 valida") from None
    if since.tzinfo is None:
        raise _UsageError("--since richiede il fuso orario (es. Z)")
    with tenancy.console_tx(uuid4()) as tx:
        rows = tx.execute(_SECURITY_EVENTS, {"since": since, "limit": SECURITY_LOG_LIMIT})
        return "".join(json.dumps(dict(r), default=str) + "\n" for r in rows.mappings())


def run(argv: Sequence[str], environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    try:
        args = _parser().parse_args(argv)
        url = env.get("DATABASE_URL_CONSOLE", "")
        try:
            check_database_url(url)
        except ValueError:
            raise _UsageError("DATABASE_URL_CONSOLE mancante o senza sslmode=verify-full") from None
        tenancy.init(url)
        try:
            if args.command == "family":
                output = _bootstrap(args)
            elif args.command == "audit":
                output = _audit_note(args)
            else:
                output = _security_log(args)
        finally:
            tenancy.dispose()
    except _UsageError as error:
        sys.stderr.write(f"errore: {error}\n")
        return EXIT_USAGE
    except Exception as error:
        sys.stderr.write(f"errore: comando non riuscito ({type(error).__name__})\n")
        return EXIT_FAILED
    sys.stdout.write(output)
    return 0
