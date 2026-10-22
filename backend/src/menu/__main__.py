"""Comandi: `python -m menu serve|seed|console` (il worker arriva con la sua slice)."""

import argparse
import os
import sys
from collections.abc import Sequence

DEFAULT_PORT = 8000


def _serve(host: str, port: int) -> int:
    import uvicorn

    from menu.app import create_app

    uvicorn.run(
        create_app(),
        host=host,
        port=port,
        access_log=False,  # il log delle richieste è quello strutturato dell'app (SR-021)
        proxy_headers=False,  # l'IP del client lo decide `client_ip` (TRUSTED_PROXY_HOPS)
        server_header=False,
        log_config=None,  # i logger di uvicorn usano la redazione del logger radice (SEC-SL00b-006)
    )
    return 0


def _seed(dataset: str) -> int:
    from menu.seeding.command import run

    return run(dataset)


def _console(arguments: Sequence[str]) -> int:
    from menu.console import run

    return run(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["console"]:
        return _console(arguments[1:])
    parser = argparse.ArgumentParser(prog="menu")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="avvia il server HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    commands.add_parser("console", help="comandi del job menu-console (menu console --help)")
    seed = commands.add_parser("seed", help="carica un dataset sintetico (con guardia)")
    seed.add_argument("--dataset", required=True)
    args = parser.parse_args(argv)
    if args.command == "serve":
        return _serve(args.host, args.port)
    return _seed(args.dataset)


if __name__ == "__main__":
    sys.exit(main())
