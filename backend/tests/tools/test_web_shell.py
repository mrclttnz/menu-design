"""SL-01: progetto `web/`, Makefile, CI e catena di fornitura del frontend (test di configurazione).

Traccia: SR-076 (cooldown npm, script di installazione bloccati, pnpm audit, osv-scanner sul
lockfile), THR-090, SR-031 (nessuno strumento di terzi), NFR-011 (i18n bloccante in CI),
NFR-001 (budget), piano §5.4, §5.6, §6.1, §6.2.

Nota su pnpm (verificato con pnpm 12.14): `minimumReleaseAge` e `onlyBuiltDependencies` NON
sono letti da `.npmrc`: vivono in `web/pnpm-workspace.yaml`. Il piano (§1, §5.6) parla di `.npmrc`:
da correggere. Qui si prova l'impostazione efficace, non il nome del file.
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from support.paths import REPO

WEB = REPO / "web"
MAKEFILE = REPO / "Makefile"
CI_YML = REPO / ".github" / "workflows" / "ci.yml"

SCRIPTS = (
    "build",
    "typecheck",
    "lint",
    "format:check",
    "test",
    "test:e2e",
    "i18n:check",
    "i18n:compile",
    "api:generate",
    "api:check",
    "budget",
)
RUNTIME_REQUIRED = {
    "react",
    "react-dom",
    "@tanstack/react-query",
    "react-aria-components",
    "@lingui/core",
    "@lingui/react",
}
DEV_REQUIRED = {
    "vite",
    "typescript",
    "vitest",
    "@vitest/coverage-v8",
    "happy-dom",
    "@testing-library/react",
    "@testing-library/user-event",
    "@playwright/test",
    "@axe-core/playwright",
    "@lingui/cli",
    "@lingui/format-po",  # Lingui 6: il formato .po è un pacchetto a parte
    "eslint",
    "typescript-eslint",
    "eslint-plugin-lingui",
    "eslint-plugin-security",
    "eslint-plugin-react-hooks",
    "prettier",
    "openapi-typescript",
}
# SR-031: nessuna analitica o tracciamento di terzi, in nessun gruppo di dipendenze.
TRACKING_PACKAGES = re.compile(
    r"(analytics|gtag|gtm|mixpanel|segment|amplitude|posthog|hotjar|fullstory|plausible|"
    r"matomo|heap|logrocket|sentry|bugsnag|datadog|newrelic|clarity|smartlook|rollbar)",
    re.IGNORECASE,
)


def _script_text(name: str) -> str:
    """Testo del comando di uno script npm; se delega a `node scripts/x.mjs` include il file."""
    command: str = _package()["scripts"][name]
    match = re.search(r"node\s+(scripts/[\w.-]+\.mjs)", command)
    if match:
        command += "\n" + (WEB / match.group(1)).read_text(encoding="utf-8")
    return command


def _package() -> dict[str, Any]:
    path = WEB / "package.json"
    assert path.is_file(), "web/package.json assente (SL-01)"
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _make_dry(target: str) -> str:
    proc = subprocess.run(  # noqa: S603
        ["make", "-n", "--no-print-directory", "-C", str(REPO), target],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _job(name: str) -> str:
    text = CI_YML.read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", text)
    assert match, f"job `{name}` assente in ci.yml (piano §6.2)"
    return match.group(1)


def _workspace_setting(key: str) -> str | None:
    path = WEB / "pnpm-workspace.yaml"
    assert path.is_file(), "web/pnpm-workspace.yaml assente: qui vivono le impostazioni di pnpm"
    match = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*)$", path.read_text(encoding="utf-8"))
    return None if match is None else match.group(1).strip()


def _workspace_list(key: str) -> list[str]:
    text = (WEB / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^{re.escape(key)}:[ \t]*\n((?:[ \t]+-[^\n]*\n?)*)", text)
    if match is None:
        inline = _workspace_setting(key)
        if inline and inline.startswith("["):
            return [x.strip().strip("'\"") for x in inline.strip("[]").split(",") if x.strip()]
        return []
    return [ln.strip()[1:].strip().strip("'\"") for ln in match.group(1).splitlines() if ln.strip()]


# --- struttura del progetto -------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "vite.config.ts",
        "tsconfig.json",
        "eslint.config.js",
        "lingui.config.ts",
        "index.html",
        "src/main.tsx",
        "src/app/routes.tsx",
        "src/app/providers.tsx",
        "src/api/errors.ts",
        "src/api/client.ts",
        "src/api/schema.gen.ts",
        "src/i18n/index.ts",
        "src/i18n/format.ts",
        "src/lib/pasto-id.ts",
        "src/styles/tokens.css",
        "src/locales/it/messages.po",
        "src/components/EmptyState.tsx",
        "src/components/ErrorState.tsx",
        "src/components/Skeleton.tsx",
        "src/components/Toast.tsx",
        "src/components/Dialog.tsx",
        "scripts/check-budget.mjs",
    ],
)
def test_web_project_has_the_planned_files(relative: str) -> None:
    assert (WEB / relative).is_file(), f"web/{relative} assente (piano §1, SL-01)"


def test_package_json_pins_the_package_manager_and_blocks_publishing() -> None:
    pkg = _package()
    assert pkg.get("private") is True
    assert pkg.get("type") == "module"
    assert re.fullmatch(r"pnpm@\d+\.\d+\.\d+", pkg.get("packageManager", "")), (
        "packageManager deve fissare la versione esatta di pnpm (corepack, riproducibilità)"
    )
    assert str(pkg.get("engines", {}).get("node", "")).lstrip(">=^~ ").startswith("24")


def test_package_json_has_the_agreed_script_names() -> None:
    scripts = _package().get("scripts", {})
    missing = [s for s in SCRIPTS if s not in scripts]
    assert not missing, f"script mancanti: {missing}"


def test_scripts_run_the_blocking_i18n_checks_nfr_011() -> None:
    scripts = _package()["scripts"]
    check = _script_text("i18n:check")
    assert "lingui" in check
    assert "extract" in check
    assert "process.exit(1)" in check or "git diff --exit-code" in check or "--clean" in check, (
        "`lingui extract` non basta: deve fallire se il catalogo committato cambia"
    )
    assert "lingui compile" in scripts["i18n:compile"]
    assert "--strict" in scripts["i18n:compile"]


def test_scripts_enforce_lint_format_types_and_unit_tests() -> None:
    scripts = _package()["scripts"]
    assert "eslint" in scripts["lint"]
    assert "--max-warnings" in scripts["lint"], "gli avvisi bloccano"
    assert re.search(r"--max-warnings[= ]0\b", scripts["lint"])
    assert "prettier" in scripts["format:check"]
    assert "--check" in scripts["format:check"]
    assert "tsc" in scripts["typecheck"]
    assert "--noEmit" in scripts["typecheck"]
    assert "vitest" in scripts["test"]
    assert "playwright test" in scripts["test:e2e"]


def test_api_client_is_generated_from_the_committed_openapi_contract() -> None:
    scripts = _package()["scripts"]
    assert "openapi-typescript" in scripts["api:generate"]
    assert "../openapi.json" in scripts["api:generate"], "la sorgente è il contratto committato"
    assert "schema.gen.ts" in scripts["api:generate"]
    check = _script_text("api:check")
    assert "openapi-typescript" in check
    assert "schema.gen.ts" in check
    assert "process.exit(1)" in check or "git diff --exit-code" in check


def test_generated_schema_is_marked_generated_and_covers_the_contract() -> None:
    text = (WEB / "src" / "api" / "schema.gen.ts").read_text(encoding="utf-8")
    assert "auto-generated" in text.lower() or "do not make direct changes" in text.lower()
    contract = json.loads((REPO / "openapi.json").read_text(encoding="utf-8"))
    schemas = contract["components"]["schemas"]
    for name in ("ErrorCode", "ValidationCode"):
        for value in schemas[name]["enum"]:
            assert f'"{value}"' in text, f"{name}.{value} manca nel client generato"
    for path in contract["paths"]:
        assert f'"{path}"' in text, f"percorso {path} manca nel client generato"


def test_dependencies_include_the_planned_stack_and_react_19() -> None:
    pkg = _package()
    runtime = set(pkg.get("dependencies", {}))
    dev = set(pkg.get("devDependencies", {}))
    assert runtime >= RUNTIME_REQUIRED, sorted(RUNTIME_REQUIRED - runtime)
    assert dev >= DEV_REQUIRED, sorted(DEV_REQUIRED - dev)
    assert {"react-router", "react-router-dom"} & runtime
    assert pkg["dependencies"]["react"].lstrip("^~").startswith("19.")
    assert pkg["dependencies"]["react-dom"].lstrip("^~").startswith("19.")


def test_no_tracking_or_third_party_service_packages_sr_031() -> None:
    pkg = _package()
    names = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
    names |= set(pkg.get("optionalDependencies", {}))
    offenders = sorted(n for n in names if TRACKING_PACKAGES.search(n))
    assert offenders == [], offenders


def test_dependencies_come_only_from_the_registry_thr_090() -> None:
    """Niente git, URL, file o link: il lockfile con gli hash è l'unica fonte (SR-076)."""
    pkg = _package()
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, spec in pkg.get(group, {}).items():
            assert not re.match(r"(git|github|http|https|file|link|portal|workspace):", spec), (
                f"{group}.{name} = {spec}"
            )
            assert not re.match(r"[\w.-]+/[\w.-]+(#.*)?$", spec), f"{name}: scorciatoia GitHub"
            assert spec not in {"*", "latest", "next", ""}, f"{group}.{name} = {spec!r}"
    assert "overrides" not in pkg, "override da motivare"
    assert "resolutions" not in pkg, "override da motivare"


def test_install_scripts_are_blocked_except_esbuild_sr_076() -> None:
    allowed = _workspace_list("onlyBuiltDependencies")
    assert set(allowed) <= {"esbuild"}, f"script d'installazione ammessi oltre esbuild: {allowed}"
    assert _workspace_setting("dangerouslyAllowAllBuilds") in {None, "false"}
    pkg_scripts = _package().get("scripts", {})
    for hook in ("preinstall", "install", "postinstall", "prepare"):
        assert hook not in pkg_scripts, f"hook `{hook}` nel progetto"


def test_release_cooldown_is_at_least_seven_days_and_has_no_exceptions_sr_076() -> None:
    raw = _workspace_setting("minimumReleaseAge")
    assert raw is not None, "minimumReleaseAge non impostato in pnpm-workspace.yaml (SR-076)"
    assert int(raw) >= 10080, "pnpm usa i minuti: 7 giorni = 10080"
    assert _workspace_list("minimumReleaseAgeExclude") == [], "nessuna eccezione al cooldown"


def test_npmrc_if_present_does_not_weaken_the_supply_chain() -> None:
    npmrc = WEB / ".npmrc"
    if not npmrc.exists():
        return
    text = npmrc.read_text(encoding="utf-8")
    for bad in (r"ignore-scripts\s*=\s*false", r"strict-ssl\s*=\s*false", r"_authToken"):
        assert not re.search(bad, text), bad
    registries = re.findall(r"(?m)^\s*(?:@[\w-]+:)?registry\s*=\s*(\S+)", text)
    assert all(r.startswith("https://registry.npmjs.org") for r in registries), registries


def test_lockfile_is_committed_and_node_modules_and_build_are_ignored() -> None:
    assert (WEB / "pnpm-lock.yaml").stat().st_size > 0
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "node_modules/" in ignored
    assert any(x in ignored for x in ("web/dist/", "dist/"))
    for artefact in ("test-results", "playwright-report"):
        assert any(re.fullmatch(rf"(web/|\*\*/)?{artefact}/?", ln) for ln in ignored), artefact


def test_vitest_coverage_thresholds_match_the_test_strategy() -> None:
    """08 §16.1: frontend riga >= 80%, branch >= 70%; `src/lib` e `errors.ts` >= 95%."""
    configs = [WEB / "vite.config.ts", WEB / "vitest.config.ts"]
    text = "\n".join(c.read_text(encoding="utf-8") for c in configs if c.is_file())
    assert re.search(r"lines:\s*80\b", text)
    assert re.search(r"branches:\s*70\b", text)
    assert re.search(r"src/lib/\*\*", text)
    assert re.search(r"src/api/errors\.ts", text)
    assert len(re.findall(r"\b95\b", text)) >= 2


def test_typescript_is_strict_and_also_checks_the_tests() -> None:
    """Piano §5.4: `strict` e `noUncheckedIndexedAccess`; anche i test di web/ si tipizzano."""
    text = (WEB / "tsconfig.json").read_text(encoding="utf-8")
    assert re.search(r'"strict"\s*:\s*true', text)
    assert re.search(r'"noUncheckedIndexedAccess"\s*:\s*true', text)
    assert re.search(r'"tests"|tests/', text), "tsconfig deve includere web/tests"


def test_prettier_uses_print_width_100() -> None:
    """Piano §5.4 (Prettier predefinito con `printWidth: 100`). I test di SL-01 sono già
    formattati così: `pnpm run format:check` deve passare sul codice del tester."""
    candidates = [
        *WEB.glob(".prettierrc*"),
        *WEB.glob("prettier.config.*"),
    ]
    sources = [c.read_text(encoding="utf-8") for c in candidates]
    sources.append(json.dumps(_package().get("prettier", {})))
    assert any(re.search(r"printWidth\W+100\b", text) for text in sources)


def test_lint_config_enforces_layers_storage_and_i18n_rules() -> None:
    """Le regole di §5.4 sono presenti; il comportamento è provato in
    `web/tests/unit/eslint-rules.test.ts` (fixture che devono fallire)."""
    text = (WEB / "eslint.config.js").read_text(encoding="utf-8")
    for needle in (
        "no-restricted-imports",
        "no-restricted-syntax",
        "lingui/no-unlocalized-strings",
        "react-hooks",
        "security",
        "strict",
    ):
        assert needle in text, needle


# --- Makefile (piano §6.1) --------------------------------------------------------------------


@pytest.mark.parametrize(
    "target", ["lint-web", "test-web", "scan-web", "web-build", "tier-web", "e2e"]
)
def test_sl_01_make_targets_are_no_longer_placeholders(target: str) -> None:
    out = _make_dry(target)
    assert "non è ancora disponibile" not in out, f"{target} è ancora un segnaposto"
    assert "pnpm" in out, f"{target} non invoca pnpm"


def test_installs_are_frozen_and_never_run_install_scripts_unreviewed() -> None:
    for target in ("lint-web", "test-web", "web-build", "e2e"):
        out = _make_dry(target)
        installs = re.findall(r"pnpm[^\n]*\binstall\b[^\n]*", out)
        assert installs, f"{target} non installa le dipendenze"
        assert all("--frozen-lockfile" in line for line in installs), installs


def test_lint_web_runs_lint_format_typecheck_and_both_i18n_checks() -> None:
    out = _make_dry("lint-web")
    for script in ("lint", "format:check", "typecheck", "i18n:check", "i18n:compile"):
        assert re.search(rf"\brun\s+(--silent\s+)?{re.escape(script)}\b", out), script


def test_test_web_runs_unit_tests_and_the_generated_client_freshness_check() -> None:
    out = _make_dry("test-web")
    assert re.search(r"\brun\s+(--silent\s+)?test\b", out)
    assert re.search(r"\brun\s+(--silent\s+)?api:check\b", out)


def test_web_build_builds_then_checks_the_bundle_budget_nfr_001() -> None:
    out = _make_dry("web-build")
    build = re.search(r"\brun\s+(--silent\s+)?build\b", out)
    budget = re.search(r"\brun\s+(--silent\s+)?budget\b", out)
    assert build
    assert budget
    assert build.start() < budget.start()


def test_e2e_builds_the_web_app_then_runs_playwright() -> None:
    out = _make_dry("e2e")
    build = re.search(r"\brun\s+(--silent\s+)?build\b", out)
    run = re.search(r"\brun\s+(--silent\s+)?test:e2e\b|playwright test", out)
    assert build
    assert run
    assert build.start() < run.start()


def test_tier_web_covers_lint_test_and_build_and_scan_covers_the_audit() -> None:
    mk = MAKEFILE.read_text(encoding="utf-8")
    tier = re.search(r"(?m)^tier-web:(.*)$", mk)
    assert tier, "target tier-web assente"
    for prerequisite in ("lint-web", "test-web", "web-build"):
        assert prerequisite in tier.group(1), prerequisite
    scan = re.search(r"(?m)^scan:(.*)$", mk)
    assert scan
    assert "scan-web" in scan.group(1)
    assert re.search(r"(?m)^lint:.*\blint-web\b", mk), "`make lint` deve includere lint-web"
    assert re.search(r"(?m)^test:.*\btest-web\b", mk), "`make test` deve includere test-web"


def test_scan_web_runs_pnpm_audit_on_high_and_fails_closed() -> None:
    out = _make_dry("scan-web")
    assert re.search(r"pnpm[^\n]*\baudit\b[^\n]*--audit-level[= ]high", out)
    assert "--prod" not in out, "audit anche delle devDependencies"
    assert "--production" not in out, "audit anche delle devDependencies"
    assert "--ignore-registry-errors" not in out, "fail open se il registro non risponde"
    assert "|| true" not in out
    assert "|| :" not in out
    body = MAKEFILE.read_text(encoding="utf-8").split("scan-web:", 1)[1].split("\n\n", 1)[0]
    assert not re.search(r"(?m)^\t-", body), "il prefisso `-` ignora gli errori"


def test_osv_scanner_also_reads_the_pnpm_lockfile() -> None:
    out = _make_dry("scan-deps")
    assert re.search(r"--lockfile[= ]web/pnpm-lock\.yaml", out), "piano §6.2 job deps"


def test_help_lists_e2e_as_active_not_as_placeholder() -> None:
    out = subprocess.run(  # noqa: S603
        ["make", "--no-print-directory", "-C", str(REPO), "help"],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    ).stdout
    lines = out.splitlines()
    idx = next(i for i, ln in enumerate(lines) if ln.lower().startswith("segnaposto"))
    active, placeholders = "\n".join(lines[:idx]), "\n".join(lines[idx:])
    assert re.search(r"\be2e\b", active)
    assert not re.search(r"\be2e\b", placeholders)


# --- CI (piano §6.2) --------------------------------------------------------------------------


def test_ci_has_blocking_web_and_e2e_jobs_with_the_makefile_targets() -> None:
    web, e2e = _job("web"), _job("e2e")
    assert "make tier-web" in web
    assert "make e2e" in e2e
    for job in (web, e2e):
        assert re.search(r"node-version:\s*[\"']?24", job), "Node 24 (piano §5.6)"
        assert "persist-credentials: false" in job
        assert re.search(r"timeout-minutes:\s*\d+", job)
        assert "secrets." not in job, "i job di test non usano segreti"
        assert "continue-on-error" not in job, "bloccanti (piano §6.2)"
        assert not re.search(r"\bnpm (install|ci)\b|\bnpx\b", job), "solo pnpm con lockfile"


def test_e2e_job_installs_chromium_explicitly_and_has_uv_for_the_server() -> None:
    e2e = _job("e2e")
    assert re.search(r"playwright install[^\n]*chromium", e2e), "download dei browser esplicito"
    assert "setup-uv" in e2e or "make sync" in e2e


def test_deps_job_runs_the_pnpm_audit() -> None:
    assert "make scan-web" in _job("deps")


def test_every_action_in_web_jobs_is_pinned_to_a_commit_sha() -> None:
    for name in ("web", "e2e"):
        for use in re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", _job(name)):
            assert re.search(r"@[0-9a-f]{40}$", use), f"{name}: azione non fissata a SHA: {use}"


def test_pnpm_is_installed_through_the_pinned_package_manager_not_latest() -> None:
    for name in ("web", "e2e"):
        job = _job(name)
        assert "corepack" in job or "pnpm/action-setup" in job
        assert not re.search(r"pnpm@(latest|next)|npm (i|install) -g pnpm", job)


# --- Dockerfile e .dockerignore (immagine unica, piano §1) -------------------------------------


def _dockerfile() -> str:
    return (REPO / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_builds_the_spa_in_a_pinned_node_stage() -> None:
    text = _dockerfile()
    assert re.search(r"(?m)^FROM node:24-slim@sha256:[0-9a-f]{64}\b", text), (
        "fase di build della SPA: node:24-slim fissata per digest (piano §5.6)"
    )
    assert "pnpm install --frozen-lockfile" in text
    assert re.search(r"pnpm (run )?build", text)


def test_final_image_has_the_build_output_but_no_node_toolchain_or_sources() -> None:
    text = _dockerfile()
    final = text.split("\nFROM ")[-1]
    assert final.startswith("python:3.14-slim")
    assert re.search(r"(?m)^COPY\b[^\n]*--from=\S+[^\n]*dist", final), "la build nell'immagine"
    assert not re.search(r"(?m)^COPY\b[^\n]*--from=[^\n]*node_modules", final)
    assert not re.search(r"(?m)^\s*(RUN|COPY).*\bweb/(src|tests)", final)
    assert re.search(r"(?m)^ENV[^\n]*WEB_DIST_DIR=", final), "il server sa dove sono i file"
    assert not re.search(r"(?m)^USER\s+(root|0)\b", final)


def test_dockerignore_lets_the_web_sources_in_but_keeps_modules_tests_and_outputs_out() -> None:
    lines = {
        ln.strip()
        for ln in (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    }
    assert "web" not in lines, "la build dell'immagine ha bisogno dei sorgenti di web/"
    assert {"**/node_modules", "web/node_modules"} & lines
    assert {"web/tests", "web/tests/**"} & lines
    assert {"web/dist", "**/dist"} & lines
    assert "web/coverage" in lines
    assert {"web/test-results", "web/playwright-report", "**/test-results"} & lines


# --- eccezione datata a pnpm audit / osv-scanner: braces (decisione utente 2026-10-22) -------
# Stesso stile della guardia sul cooldown di certifi (INFO-14, CR-SL00a-011): l'eccezione è
# ammessa SOLO per questo GHSA, SOLO fino a questa data, e non rende l'audit fail-open.

APPROVED_GHSA = "GHSA-vfj7-8cjw-p6xm"
APPROVED_UNTIL = "2026-11-21"
OSV_CONFIG = REPO / "osv-scanner.toml"
STATUS_MD = REPO / "docs" / "STATUS.md"


def _scan_web_recipe(mk: str) -> str:
    return mk.split("\nscan-web:", 1)[1].split("\n\n", 1)[0]


def _verdict_script(mk: str) -> str:
    return mk.split("define WEB_AUDIT_VERDICT\n", 1)[1].split("\nendef", 1)[0]


def audit_exception_violations(mk: str) -> list[str]:
    """Violazioni della regola «eccezione stretta e datata» nel Makefile (vuoto = conforme).

    `pnpm audit --ignore` non è ammesso (scrive l'esenzione in pnpm-workspace.yaml senza
    scadenza): l'esenzione sta solo nel filtro del report JSON, per ID e prima della data.
    """
    problems: list[str] = []
    ghsa = re.search(r"(?m)^WEB_AUDIT_EXCEPTION_GHSA\s*:=\s*(\S+)\s*$", mk)
    until = re.search(r"(?m)^WEB_AUDIT_EXCEPTION_UNTIL\s*:=\s*(\S+)\s*$", mk)
    if not ghsa or ghsa.group(1) != APPROVED_GHSA:
        problems.append("GHSA diverso da quello approvato")
    if not until or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", until.group(1)):
        problems.append("data mancante o non ISO")
    elif until.group(1) > APPROVED_UNTIL:
        problems.append("scadenza oltre quella approvata")
    recipe = _scan_web_recipe(mk)
    script = _verdict_script(mk)
    if re.search(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}", recipe + script):
        problems.append("id scritto nella ricetta o nel filtro: deve venire dalla variabile")
    if re.search(r"--ignore", recipe):
        problems.append("vietato: opzioni --ignore di pnpm audit")
    for forbidden in ("|| true", "|| :", "--ignore-registry-errors"):
        if forbidden in recipe:
            problems.append(f"vietato: {forbidden}")
    if re.search(r"(?m)^\t-", recipe):
        problems.append("prefisso `-` sulla ricetta")
    if "--audit-level high" not in recipe or "--json" not in recipe:
        problems.append("soglia high o report JSON rimossi")
    if not recipe.rstrip().endswith('node -e "$$WEB_AUDIT_VERDICT" < "$$f"'):
        problems.append("l'ultimo comando della ricetta deve essere il verdetto")
    if 'EXC_GHSA="$(WEB_AUDIT_EXCEPTION_GHSA)"' not in recipe:
        problems.append("il filtro non riceve l'ID dalla variabile")
    if 'EXC_UNTIL="$(WEB_AUDIT_EXCEPTION_UNTIL)"' not in recipe:
        problems.append("il filtro non riceve la scadenza dalla variabile")
    if "toISOString().slice(0, 10) < until" not in script:
        problems.append("l'eccezione non è condizionata alla data")
    if "a.github_advisory_id === id" not in script:
        problems.append("l'eccezione non è per ID esatto")
    if '["high", "critical"]' not in script:
        problems.append("gravità controllate diverse da high e critical")
    if "process.exit(1)" not in script or "process.exit(bad.length ? 1 : 0)" not in script:
        problems.append("il filtro non fallisce su report illeggibile o con problemi")
    return problems


def osv_config_violations(text: str) -> list[str]:
    import tomllib
    from datetime import UTC, datetime

    problems: list[str] = []
    config = tomllib.loads(text)
    if set(config) - {"IgnoredVulns"}:
        problems.append(f"sezioni non ammesse: {sorted(set(config) - {'IgnoredVulns'})}")
    entries = config.get("IgnoredVulns", [])
    if len(entries) != 1:
        return [*problems, f"voci di ignore: {len(entries)} invece di 1"]
    entry = entries[0]
    if entry.get("id") != APPROVED_GHSA:
        problems.append("id diverso da quello approvato")
    until = entry.get("ignoreUntil")
    limit = datetime(2026, 11, 21, tzinfo=UTC)
    if not isinstance(until, datetime) or until.tzinfo is None:
        problems.append("ignoreUntil mancante (eccezione senza scadenza)")
    elif until > limit:
        problems.append("ignoreUntil oltre la scadenza approvata")
    if entry.get("ignore") is True:
        problems.append("ignore permanente")
    return problems


def test_audit_exception_is_exactly_the_approved_one() -> None:
    assert audit_exception_violations(MAKEFILE.read_text(encoding="utf-8")) == []


_VERDICT_CALL = 'node -e "$$WEB_AUDIT_VERDICT" < "$$f"'


@pytest.mark.parametrize(
    ("old", "new", "needle"),
    [
        (f"WEB_AUDIT_EXCEPTION_GHSA  := {APPROVED_GHSA}", "WEB_AUDIT_EXCEPTION_GHSA  := GHSA-aaaa-bbbb-cccc", "GHSA diverso"),  # noqa: E501
        (f"WEB_AUDIT_EXCEPTION_UNTIL := {APPROVED_UNTIL}", "WEB_AUDIT_EXCEPTION_UNTIL := 2027-01-01", "oltre"),  # noqa: E501
        (f"WEB_AUDIT_EXCEPTION_UNTIL := {APPROVED_UNTIL}", "WEB_AUDIT_EXCEPTION_UNTIL := mai", "data"),  # noqa: E501
        ("--audit-level high --json", "--audit-level high --json --ignore GHSA-aaaa-bbbb-cccc", "vietato: opzioni"),  # noqa: E501
        ("--audit-level high --json", "--audit-level high --json --ignore-registry-errors", "vietato"),  # noqa: E501
        ("--audit-level high --json", "--audit-level critical --json", "soglia"),
        (_VERDICT_CALL, _VERDICT_CALL + " || true", "vietato"),
        ("\t$(PNPM) audit", "\t-$(PNPM) audit", "prefisso"),
        ("toISOString().slice(0, 10) < until", "true", "condizionata alla data"),
        ("a.github_advisory_id === id", "a.module_name === 'braces'", "per ID esatto"),
        ('["high", "critical"]', '["critical"]', "gravità"),
        ("id = process.env.EXC_GHSA", "id = 'GHSA-aaaa-bbbb-cccc'", "id scritto"),
    ],
    ids=["other-id", "later-date", "no-date", "pnpm-ignore", "registry-errors", "lower-level",
         "or-true", "dash-prefix", "unconditional", "by-package", "severity", "literal-id"],
)  # fmt: skip
def test_audit_exception_guard_rejects_other_variants(old: str, new: str, needle: str) -> None:
    """La guardia sa fallire (mutazioni sintetiche del Makefile reale)."""
    mk = MAKEFILE.read_text(encoding="utf-8")
    if old not in mk:  # la forma esatta della dichiarazione dell'ID nello script può variare
        pytest.fail(f"punto di mutazione non trovato nel Makefile: {old!r}")
    found = audit_exception_violations(mk.replace(old, new, 1))
    assert any(needle in p for p in found), found


def _advisory(ghsa: str, severity: str = "high") -> dict[str, object]:
    return {
        "github_advisory_id": ghsa,
        "severity": severity,
        "module_name": "pkg",
        "vulnerable_versions": "<=1",
    }


def _report(*advisories: dict[str, object]) -> str:
    return json.dumps({"advisories": {str(i): a for i, a in enumerate(advisories)}, "metadata": {}})


def _run_scan_web(tmp_path: Path, report: str, until: str | None = None, exit_code: int = 0) -> int:
    """Esegue la ricetta vera di `scan-web` con un `pnpm audit` finto che stampa `report`."""
    stub = tmp_path / "pnpm-stub.sh"
    (tmp_path / "report.json").write_text(report, encoding="utf-8")
    stub.write_text(
        f'#!/bin/sh\ncat "{tmp_path}/report.json"\nexit {exit_code}\n', encoding="utf-8"
    )
    stub.chmod(0o755)
    command = [
        "make",
        "--no-print-directory",
        "-C",
        str(REPO),
        "-o",
        "web-install",
        "scan-web",
        f"PNPM={stub}",
    ]
    if until is not None:
        command.append(f"WEB_AUDIT_EXCEPTION_UNTIL={until}")
    proc = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603
    return proc.returncode


def test_approved_advisory_alone_passes_before_the_expiry(tmp_path: Path) -> None:
    assert _run_scan_web(tmp_path, _report(_advisory(APPROVED_GHSA))) == 0


@pytest.mark.parametrize("until", ["2026-10-22", "2026-10-01", "2000-01-01"])
def test_approved_advisory_fails_on_or_after_the_expiry_date(tmp_path: Path, until: str) -> None:
    """`until` è l'ultimo giorno escluso: oggi (2026-10-22) o prima = scaduta."""
    assert _run_scan_web(tmp_path, _report(_advisory(APPROVED_GHSA)), until=until) != 0


def test_real_expiry_date_is_in_the_future_or_the_audit_goes_red(tmp_path: Path) -> None:
    import datetime as dt

    expired = dt.datetime.now(dt.UTC).date().isoformat() >= APPROVED_UNTIL
    code = _run_scan_web(tmp_path, _report(_advisory(APPROVED_GHSA)))
    assert (code != 0) == expired


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_any_other_advisory_fails_even_with_the_exception_active(
    tmp_path: Path, severity: str
) -> None:
    report = _report(_advisory(APPROVED_GHSA), _advisory("GHSA-aaaa-bbbb-cccc", severity))
    assert _run_scan_web(tmp_path, report, until="2999-01-01") != 0


def test_an_id_that_only_resembles_the_approved_one_is_not_accepted(tmp_path: Path) -> None:
    report = _report(_advisory(APPROVED_GHSA + "x"))
    assert _run_scan_web(tmp_path, report, until="2999-01-01") != 0


def test_moderate_advisories_do_not_fail_the_audit(tmp_path: Path) -> None:
    assert _run_scan_web(tmp_path, _report(_advisory("GHSA-aaaa-bbbb-cccc", "moderate"))) == 0


@pytest.mark.parametrize(
    "report", ["", "non json", "{}", '{"advisories": []}', '{"metadata": {}}', "null"],
    ids=["empty", "not-json", "empty-object", "advisories-list", "no-advisories", "null"],
)  # fmt: skip
def test_unreadable_or_incomplete_report_fails_closed(tmp_path: Path, report: str) -> None:
    assert _run_scan_web(tmp_path, report, until="2999-01-01") != 0


@pytest.mark.parametrize(
    "output",
    ['{"error": {"code": "ERR_PNPM_AUDIT_BAD_RESPONSE"}}', ""],
    ids=["error-json", "empty"],
)
def test_registry_failure_fails_closed(tmp_path: Path, output: str) -> None:
    """`pnpm audit` esce con errore (registro irraggiungibile): l'esito deve essere rosso."""
    assert _run_scan_web(tmp_path, output, until="2999-01-01", exit_code=1) != 0


def test_pnpm_workspace_has_no_audit_exemptions() -> None:
    """`pnpm audit --ignore` scrive qui l'esenzione, senza scadenza: non deve comparirci."""
    text = (WEB / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*(auditConfig|ignoreGhsas|ignoreCves)\b", text)


def test_osv_scanner_config_has_only_the_approved_dated_entry() -> None:
    assert OSV_CONFIG.is_file(), "osv-scanner.toml assente"
    assert osv_config_violations(OSV_CONFIG.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("old", "new", "needle"),
    [
        (f'id = "{APPROVED_GHSA}"', 'id = "GHSA-aaaa-bbbb-cccc"', "id diverso"),
        ("ignoreUntil = 2026-11-21T00:00:00Z", "ignoreUntil = 2027-06-01T00:00:00Z", "oltre"),
        ("ignoreUntil = 2026-11-21T00:00:00Z", "ignore = true", "ignore permanente"),
        ("ignoreUntil = 2026-11-21T00:00:00Z", "ignoreUntil = 2026-11-21", "scadenza"),
    ],
    ids=["other-id", "later-date", "permanent", "naive-date"],
)
def test_osv_config_guard_rejects_variants(old: str, new: str, needle: str) -> None:
    text = OSV_CONFIG.read_text(encoding="utf-8")
    assert old in text, old
    assert any(needle in p for p in osv_config_violations(text.replace(old, new, 1)))


def test_osv_config_guard_rejects_a_second_entry() -> None:
    text = OSV_CONFIG.read_text(encoding="utf-8")
    extra = '\n[[IgnoredVulns]]\nid = "GHSA-aaaa-bbbb-cccc"\nignoreUntil = 2026-11-01T00:00:00Z\n'
    assert any("voci di ignore" in p for p in osv_config_violations(text + extra))


def test_exception_is_listed_in_the_technical_debt_with_its_expiry() -> None:
    debt = (
        STATUS_MD.read_text(encoding="utf-8").split("## Technical debt", 1)[1].split("\n## ", 1)[0]
    )
    row = next((ln for ln in debt.splitlines() if APPROVED_GHSA in ln), None)
    assert row, "eccezione assente da Technical debt in docs/STATUS.md"
    assert APPROVED_UNTIL in row
