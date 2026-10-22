"""SEC-SL00b-006: i logger della libreria standard passano dalla stessa redazione."""

import json
import logging
from typing import Any

import pytest

from menu.platform.logging import configure_logging

CANARY = "CANARY-STDLIB-PARAM"


def test_stdlib_logger_message_and_exception_text_are_not_emitted(
    capfd: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    capfd.readouterr()
    log = logging.getLogger("sqlalchemy.engine")
    try:
        raise ValueError(f"[parameters: ('{CANARY}',)]")
    except ValueError:
        log.exception("INSERT ... %s", CANARY)
    log.error("cookie=%s\nFORGED", CANARY)
    out = capfd.readouterr().out
    assert CANARY not in out
    assert "FORGED" not in out
    records = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    assert records
    assert records[0]["event"] == "stdlib.sqlalchemy.engine"
    assert records[0]["severity"] == "ERROR"
    assert records[0]["exception"] == "ValueError"
    assert set(records[0]) <= {"event", "severity", "timestamp", "exception"}


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    configure_logging()
    marked = [h for h in logging.getLogger().handlers if getattr(h, "_menu_redacting_handler", 0)]
    assert len(marked) == 1


class _Exploding:
    def __str__(self) -> str:
        raise RuntimeError(CANARY)


def test_bad_format_arguments_leak_nothing_on_stdout_or_stderr(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """CR-SL01-001: un errore di formattazione non stampa messaggio e argomenti."""
    configure_logging()
    capfd.readouterr()
    log = logging.getLogger("uvicorn.error")
    log.error("bad format %s %s", CANARY)
    log.error("exploding %s", _Exploding())
    captured = capfd.readouterr()
    assert CANARY not in captured.out
    assert CANARY not in captured.err
    assert captured.out.count('"event"') == 2


def test_exc_info_true_without_active_exception_logs_no_exception_field(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """CR-SL01-002: niente "NoneType"."""
    configure_logging()
    capfd.readouterr()
    logging.getLogger("uvicorn.error").error("x", exc_info=True)
    record = json.loads(capfd.readouterr().out.splitlines()[0])
    assert "exception" not in record
    assert record["severity"] == "ERROR"


@pytest.mark.parametrize("level", [logging.NOTSET, logging.ERROR, logging.CRITICAL])
def test_root_level_is_pulled_down_to_warning(level: int) -> None:
    """CR-SL01-003: né INFO né livelli più alti di WARNING nascondono i warning."""
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, "_menu_redacting_handler", 0)]:
        root.removeHandler(handler)
    root.setLevel(level)
    configure_logging()
    assert root.level == logging.WARNING


def test_info_is_suppressed_and_warning_and_critical_map_to_severity(
    capfd: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    logging.getLogger().setLevel(logging.WARNING)
    capfd.readouterr()
    log = logging.getLogger("some.library")
    log.info("hidden")
    log.warning("w")
    log.critical("c")
    records = [json.loads(ln) for ln in capfd.readouterr().out.splitlines() if ln.startswith("{")]
    assert [r["severity"] for r in records] == ["WARNING", "CRITICAL"]


def test_handler_writes_to_the_current_stdout(
    capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    configure_logging()
    handler: Any = next(
        h for h in logging.getLogger().handlers if getattr(h, "_menu_redacting_handler", 0)
    )
    handler.stream = io.StringIO()  # the setter must ignore it
    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    assert handler.stream is buffer
    logging.getLogger("some.library").warning("w")
    assert '"severity": "WARNING"' in buffer.getvalue()
