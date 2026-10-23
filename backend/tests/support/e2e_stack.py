"""Stack per gli e2e con accesso (SL-03a; 08 §2, §4.2): database di prova, provider OIDC finto, app.

Lo avvia Playwright (`web/playwright.config.ts`, `webServer`): crea un database dal template
`upgrade head` sul cluster di test (stesse variabili `MENU_TEST_PG_*` di `make test-db`; se manca
la password dell'amministratore la legge da `db/dev-certs/admin-password`, come il Makefile),
avvia il provider OIDC finto su `--stub-port` e l'app (`python -m menu serve`) su `--port` con
`APP_ENV=test` e `OIDC_ISSUER` = lo stub. Quando l'app termina (o arriva SIGTERM) tutto si ferma
e il database si cancella.

Lo stub espone la pagina di consenso (identità dal cookie `stub_identity`, vedi
`fake_oidc_server.py`) e `POST /__seed` per preparare i dati di un test senza toccare il
database dal browser:
  {"kind": "bootstrap", "email": ..., "familyName": ...}
  {"kind": "member", "sub": ..., "email": ..., "role": ..., "displayName": ..., "familyName": ...}
Mai su staging né in produzione: lo stub non esiste lì (08 §4.1b).
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS))

from support import pg  # noqa: E402
from support.accounts import make_bootstrap, make_family, make_member  # noqa: E402
from support.fake_oidc import CLIENT_ID, CLIENT_SECRET  # noqa: E402
from support.fake_oidc_server import StubServer  # noqa: E402
from support.owner import Owner  # noqa: E402

REPO = TESTS.parents[1]


def _default_cluster_env() -> None:
    os.environ.setdefault("MENU_TEST_PG_HOST", "localhost")
    port = os.environ.get("MENU_TEST_PG_PORT") or os.environ.get("MENU_PG_HOST_PORT") or "5432"
    os.environ["MENU_TEST_PG_PORT"] = port
    os.environ.setdefault("MENU_TEST_PG_CA", str(REPO / "db" / "dev-certs" / "ca.crt"))
    secret = REPO / "db" / "dev-certs" / "admin-password"
    if not os.environ.get("MENU_TEST_PG_ADMIN_PASSWORD") and secret.is_file():
        os.environ["MENU_TEST_PG_ADMIN_PASSWORD"] = secret.read_text(encoding="utf-8").strip()


def _drop_stale_databases() -> None:
    """Playwright può fermare lo stack senza lasciargli il tempo di pulire: via i `menu_e2e_<pid>`
    il cui processo non esiste più."""
    with pg.admin_connect() as admin:
        names = [
            r[0]
            for r in admin.execute(
                "select datname from pg_database where datname like 'menu\\_e2e\\_%'"
            ).fetchall()
        ]
    for name in names:
        pid = name.rsplit("_", 1)[-1]
        alive = pid.isdigit() and Path(f"/proc/{pid}").exists()
        if not alive:
            pg.drop_db(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--stub-port", type=int, required=True)
    parser.add_argument("--dist", required=True)
    args = parser.parse_args()

    _default_cluster_env()
    try:
        pg.admin_connect().close()
    except Exception as error:
        sys.stderr.write(
            f"e2e: PostgreSQL di test non raggiungibile ({type(error).__name__}): `make dev`.\n"
        )
        return 3
    _drop_stale_databases()
    _, head = pg.ensure_templates()
    dbname = f"menu_e2e_{os.getpid()}"
    with pg.admin_connect() as admin:
        pg.create_db(admin, dbname, template=head)
    owner = Owner(dbname)

    def seed(payload: dict[str, Any]) -> None:
        family = make_family(owner, payload.get("familyName", "Famiglia Alfa"))
        if payload["kind"] == "bootstrap":
            make_bootstrap(owner, family, payload["email"])
        elif payload["kind"] == "member":
            make_member(
                owner,
                family,
                sub=payload["sub"],
                email=payload["email"],
                role=payload.get("role", "member"),
                display_name=payload.get("displayName", "Mario Membro"),
            )
        else:
            raise ValueError("kind di semina sconosciuto")

    base = f"http://127.0.0.1:{args.port}"
    stub = StubServer(port=args.stub_port, interactive=True, seed=seed)
    stub.fresh(redirect_uri=f"{base}/api/v1/auth/google/callback")
    stub.start()

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "APP_ENV": "test",
        "TRUSTED_PROXY_HOPS": "0",
        "DATABASE_URL_APP": pg.cluster().role_url("menu_app", dbname, sqlalchemy=True),
        "WEB_DIST_DIR": args.dist,
        "GOOGLE_CLIENT_ID": CLIENT_ID,
        "GOOGLE_CLIENT_SECRET": CLIENT_SECRET,
        "OIDC_ISSUER": stub.issuer,
        "APP_BASE_URL": base,
    }
    argv = [sys.executable, "-m", "menu", "serve", "--host", "127.0.0.1", "--port", str(args.port)]
    # nosemgrep: dangerous-subprocess-use-tainted-env-args -- fixed argv, local env
    child = subprocess.Popen(argv, env=env, cwd=REPO / "backend")  # noqa: S603

    def stop(*_: object) -> None:
        child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while child.poll() is None:
            time.sleep(0.2)
    finally:
        if child.poll() is None:
            child.kill()
        stub.stop()
        pg.drop_db(dbname)
    return child.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
