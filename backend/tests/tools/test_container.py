"""Immagine container e compose (plan SL-00b; THR-092, SR-076, SR-075): controlli statici, hadolint
e (marker `container`) build reale dell'immagine con verifica dell'utente non root.
"""

import re
import shutil
import subprocess
import uuid

import pytest

from support.paths import REPO

DOCKERFILE = REPO / "Dockerfile"
COMPOSE = REPO / "compose.yaml"
DOCKERIGNORE = REPO / ".dockerignore"
DIGEST = r"@sha256:[0-9a-f]{64}"


def _dockerfile() -> str:
    assert DOCKERFILE.is_file(), "Dockerfile assente (SL-00b)"
    return DOCKERFILE.read_text(encoding="utf-8")


def _instructions() -> list[tuple[str, str]]:
    joined = re.sub(r"\\\n", " ", _dockerfile())
    out = []
    for line in joined.splitlines():
        m = re.match(r"\s*([A-Za-z]+)\s+(.*)", line)
        if m and not line.lstrip().startswith("#"):
            out.append((m.group(1).upper(), m.group(2).strip()))
    return out


def test_dockerfile_is_multi_stage() -> None:
    assert len([i for i, _ in _instructions() if i == "FROM"]) >= 2


def test_every_base_image_is_pinned_by_digest() -> None:
    stages: set[str] = set()
    for instr, arg in _instructions():
        if instr != "FROM":
            continue
        image = arg.split()[0]
        if image not in stages:
            assert re.search(DIGEST + r"$", image), f"base non fissata per digest: {image}"
        m = re.search(r"(?i)\bas\s+(\S+)", arg)
        if m:
            stages.add(m.group(1))


def test_final_stage_uses_the_slim_python_base_and_a_non_root_user() -> None:
    froms = [a for i, a in _instructions() if i == "FROM"]
    assert froms[-1].startswith("python:3.14-slim")
    users = [a for i, a in _instructions() if i == "USER"]
    assert users, "nessuna istruzione USER"
    assert users[-1].split(":")[0] not in {"root", "0"}


def test_dockerfile_has_no_secrets_nor_remote_add_nor_reload() -> None:
    for instr, arg in _instructions():
        if instr in {"ENV", "ARG"}:
            assert not re.search(r"(?i)(password|secret|token|api_?key|pepper)", arg), arg
        assert instr != "ADD" or not arg.startswith(("http://", "https://"))
        assert not (instr == "COPY" and re.search(r"\.env\b", arg)), arg
    assert "--reload" not in _dockerfile()


def test_cmd_runs_the_server_with_the_access_log_off_by_code() -> None:
    """CR-SL00a-012b: avvio con `python -m menu serve` (il log d'accesso di uvicorn è spento)."""
    cmds = [a for i, a in _instructions() if i in {"CMD", "ENTRYPOINT"}]
    assert cmds, "né CMD né ENTRYPOINT"
    assert any("menu" in c and "serve" in c for c in cmds), cmds
    assert all(c.lstrip().startswith("[") for c in cmds), "forma exec (JSON array)"


def test_dockerignore_keeps_secrets_git_tests_and_docs_out_of_the_context() -> None:
    assert DOCKERIGNORE.is_file()
    lines = {ln.strip() for ln in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()}
    for needed in (".git", "**/.env", "**/.env.*", "!.env.example"):
        assert needed in lines, f".dockerignore senza {needed}"
    assert any(x in lines for x in ("backend/tests", "**/tests", "backend/tests/"))


def test_compose_runs_postgres_17_by_digest_on_a_configurable_local_port() -> None:
    assert COMPOSE.is_file(), "compose.yaml assente (SL-00b)"
    text = COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"image:\s*postgres:17" + DIGEST, text)
    assert re.search(r"127\.0\.0\.1:\$\{MENU_PG_HOST_PORT:-5432\}:5432", text), (
        "porta host configurabile e legata a localhost (5432 può essere occupata)"
    )
    assert "ssl=on" in text or "ssl: on" in text, "serve TLS: l'app impone verify-full"
    assert not re.search(r"POSTGRES_PASSWORD:\s*[^$\s]", text), "password letterale nel compose"


def compose_port_violations(text: str) -> list[str]:
    """Porte pubblicate fuori da localhost, `privileged`, rete host, socket Docker."""
    bad = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if re.match(r"\s*ports:\s*$", line):
            indent = len(line) - len(line.lstrip())
            for item in lines[idx + 1 :]:
                if item.strip() and len(item) - len(item.lstrip()) <= indent:
                    break
                spec = item.strip().lstrip("-").strip().strip("\"'")
                if spec and not spec.startswith(("127.0.0.1:", "[::1]:")):
                    bad.append(f"porta non legata a localhost: {spec}")
    if re.search(r"(?m)^\s*privileged:\s*true", text):
        bad.append("privileged: true")
    if re.search(r"(?m)^\s*network_mode:\s*[\"']?host", text):
        bad.append("network_mode: host")
    if "/var/run/docker.sock" in text:
        bad.append("socket Docker montato")
    return bad


def test_compose_publishes_only_on_localhost_and_is_not_privileged() -> None:
    """CR-SL00b-009 (opzione A): compose.yaml è controllato dai test, non da trivy."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*ports:", text), "il compose deve pubblicare la porta del database"
    assert compose_port_violations(text) == []


PORT = '"127.0.0.1:${MENU_PG_HOST_PORT:-5432}:5432"'


@pytest.mark.parametrize(
    ("old", "new", "needle"),
    [
        (PORT, '"5432:5432"', "porta non legata"),
        (PORT, '"0.0.0.0:5432:5432"', "porta non legata"),
        (PORT, '"${MENU_PG_HOST_PORT:-5432}:5432"', "porta non legata"),
        ("shm_size: 256mb", "shm_size: 256mb\n    privileged: true", "privileged"),
        ("shm_size: 256mb", "shm_size: 256mb\n    network_mode: host", "network_mode"),
        (
            "shm_size: 256mb",
            "shm_size: 256mb\n    volumes_extra: /var/run/docker.sock",
            "socket Docker",
        ),
    ],
    ids=["bare-port", "all-interfaces", "no-host-ip", "privileged", "host-network", "docker-sock"],
)
def test_compose_checks_go_red_on_mutated_files(old: str, new: str, needle: str) -> None:
    """Il controllo sa fallire: mutazioni sintetiche del compose reale."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert compose_port_violations(text) == []
    assert old in text
    violations = compose_port_violations(text.replace(old, new, 1))
    assert any(needle in v for v in violations), violations


def test_ci_backend_job_has_a_pinned_postgres_service_and_a_container_job() -> None:
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"image:\s*postgres:17" + DIGEST, ci)
    assert re.search(r"(?m)^  container:", ci)
    for tool in ("hadolint", "trivy"):
        assert tool in ci


@pytest.mark.skipif(shutil.which("hadolint") is None, reason="hadolint non installato (UNVERIFIED)")
def test_hadolint_passes_on_the_dockerfile() -> None:
    _dockerfile()
    proc = subprocess.run(  # noqa: S603
        ["hadolint", str(DOCKERFILE)],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.fixture(scope="module")
def image() -> str:
    if shutil.which("docker") is None:
        pytest.fail("docker non disponibile: il livello container non è verificabile")
    _dockerfile()
    tag = f"menu-design-test:{uuid.uuid4().hex[:8]}"
    build = subprocess.run(  # noqa: S603
        ["docker", "build", "-t", tag, "-f", str(DOCKERFILE), str(REPO)],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert build.returncode == 0, build.stderr[-3000:]
    return tag


@pytest.mark.container
def test_image_runs_as_non_root(image: str) -> None:
    out = subprocess.run(  # noqa: S603
        ["docker", "run", "--rm", "--entrypoint", "id", image, "-u"],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() != "0"


@pytest.mark.container
def test_image_contains_no_tests_env_files_or_git(image: str) -> None:
    out = subprocess.run(  # noqa: S603
        ["docker", "run", "--rm", "--entrypoint", "sh", image, "-c",  # noqa: S607
         "find / -xdev \\( -name '.env' -o -name '.env.*' -o -name '.git' -o -name tests "
         "-path '*menu*' \\) -not -path '/proc/*' 2>/dev/null | head"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )  # fmt: skip
    assert out.stdout.strip() == "", out.stdout


@pytest.mark.container
def test_container_refuses_to_start_without_app_env(image: str) -> None:
    """Fail closed anche nel container: senza APP_ENV il processo esce con errore."""
    out = subprocess.run(  # noqa: S603
        ["docker", "run", "--rm", image],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert out.returncode != 0
    assert "app_env" in (out.stdout + out.stderr).lower()
