"""Process logs reach Cloud Logging with a severity.

Neither the API nor the worker configured Python logging, so a ``LOGGER.warning``
fell to the standard library's last-resort handler: a bare message on stderr that
Cloud Logging recorded at DEFAULT severity, out of reach of ``severity>=WARNING``
filters and alerts. Cloud Run reads one JSON object per stderr line as a
structured entry and takes its ``severity`` and ``message`` fields.
"""

import io
import json
import logging
import sys
from unittest.mock import Mock

import pytest
from fastapi import FastAPI

PROBE_LOGGER = "specimen_digitization.application.production"


@pytest.fixture(autouse=True)
def restore_logging_state():
    """Entry points and uvicorn mutate process-wide logging; give it back."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    uvicorn = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).propagate,
        )
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    }
    root.setLevel(logging.WARNING)
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    for name, (kept, propagate) in uvicorn.items():
        logging.getLogger(name).handlers[:] = kept
        logging.getLogger(name).propagate = propagate


def stderr_lines(capsys):
    return [line for line in capsys.readouterr().err.splitlines() if line]


def probe(message, *args, level=logging.WARNING):
    logging.getLogger(PROBE_LOGGER).log(level, message, *args)


def json_line_about(lines, text):
    (line,) = [line for line in lines if text in line]
    assert line.startswith("{"), line
    return json.loads(line)


def make_record(level, message, *args, exc_info=None, name="specimen_digitization.x"):
    return logging.LogRecord(name, level, __file__, 1, message, args, exc_info)


@pytest.mark.parametrize(
    ("level", "severity"),
    [
        (logging.DEBUG, "DEBUG"),
        (logging.INFO, "INFO"),
        (25, "INFO"),
        (logging.WARNING, "WARNING"),
        (35, "WARNING"),
        (logging.ERROR, "ERROR"),
        (45, "ERROR"),
        (logging.CRITICAL, "CRITICAL"),
    ],
)
def test_formatter_maps_the_level_to_a_cloud_logging_severity(level, severity):
    from specimen_digitization.process_logging import CloudLoggingFormatter

    entry = json.loads(CloudLoggingFormatter().format(make_record(level, "m")))

    assert entry["severity"] == severity


def test_formatter_emits_one_json_line_with_message_and_logger():
    from specimen_digitization.process_logging import CloudLoggingFormatter

    line = CloudLoggingFormatter().format(
        make_record(logging.WARNING, "run=%s\nstep=%s", "r1", "parse")
    )

    assert "\n" not in line
    assert json.loads(line) == {
        "severity": "WARNING",
        "message": "run=r1\nstep=parse",
        "logger": "specimen_digitization.x",
    }


def test_formatter_keeps_a_traceback_in_the_same_entry():
    from specimen_digitization.process_logging import CloudLoggingFormatter

    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record(logging.ERROR, "failed", exc_info=sys.exc_info())
    line = CloudLoggingFormatter().format(record)

    assert "\n" not in line
    message = json.loads(line)["message"]
    assert message.startswith("failed\nTraceback")
    assert "ValueError: boom" in message


@pytest.mark.parametrize(
    ("value", "kept"),
    [
        ("model_malformed_response", True),
        ("provider_circuit:open", True),
        ("classification_review_required:label-a.b-1", True),
        ("Label reads: J. Smith", False),
        ("code\nwith newline", False),
        ("", False),
        ("x" * 161, False),
        (None, False),
        (42, False),
    ],
    ids=[
        "plain_code",
        "colon_code",
        "dotted_code",
        "free_text",
        "newline",
        "empty",
        "overlong",
        "none",
        "number",
    ],
)
def test_log_code_passes_code_shaped_text_and_nothing_else(value, kept):
    from specimen_digitization.process_logging import log_code

    assert log_code(value) == (value if kept else "unrecognized")


def test_configure_writes_warnings_as_json_with_severity(capsys):
    from specimen_digitization.process_logging import configure_process_logging

    configure_process_logging()
    probe("Projection for specimen %s stopped", "s1")
    probe("not shown", level=logging.INFO)

    lines = stderr_lines(capsys)
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "severity": "WARNING",
        "message": "Projection for specimen s1 stopped",
        "logger": PROBE_LOGGER,
    }


def test_configure_is_idempotent(capsys):
    from specimen_digitization.process_logging import configure_process_logging

    before = len(logging.getLogger().handlers)
    configure_process_logging()
    configure_process_logging()

    assert len(logging.getLogger().handlers) == before + 1
    probe("once")
    assert len(stderr_lines(capsys)) == 1


def test_handler_follows_the_current_stderr(capsys, monkeypatch):
    from specimen_digitization.process_logging import configure_process_logging

    configure_process_logging()
    replaced = io.StringIO()
    monkeypatch.setattr(sys, "stderr", replaced)
    probe("later")

    assert json.loads(replaced.getvalue())["message"] == "later"


def test_uvicorn_logging_setup_does_not_remove_the_handler(capsys):
    import uvicorn

    from specimen_digitization.process_logging import configure_process_logging

    configure_process_logging()
    # The same construction the API's serve() performs; it applies uvicorn's own
    # logging config but touches only the uvicorn loggers.
    uvicorn.Config(FastAPI(), host="127.0.0.1", port=0, access_log=False)
    probe("after uvicorn")

    assert (
        json_line_about(stderr_lines(capsys), "after uvicorn")["severity"] == "WARNING"
    )


def test_api_entry_point_configures_process_logging(monkeypatch, capsys):
    from specimen_digitization import observability
    from specimen_digitization.application import cli, runtime_server

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SPECIMEN_SYNTHETIC_TOKEN", "local-fixture-only")
    monkeypatch.setattr(observability, "configure_observability", Mock())
    monkeypatch.setattr(cli, "local_app", lambda *args, **kwargs: FastAPI())
    monkeypatch.setattr(runtime_server, "serve", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["specimen-api", "--mode", "synthetic"])

    cli.main()
    probe("from the api process")

    entry = json_line_about(stderr_lines(capsys), "from the api process")
    assert entry["severity"] == "WARNING"


def test_worker_entry_point_configures_process_logging(monkeypatch, capsys):
    from specimen_digitization.application import worker

    # An argument error exits before any production setup runs.
    monkeypatch.setattr(
        sys,
        "argv",
        ["specimen-worker", "--mode", "production", "--drain", "--max-seconds", "600"],
    )
    with pytest.raises(SystemExit) as caught:
        worker.main()
    assert caught.value.code == 2
    capsys.readouterr()
    probe("from the worker process")

    entry = json_line_about(stderr_lines(capsys), "from the worker process")
    assert entry["severity"] == "WARNING"
