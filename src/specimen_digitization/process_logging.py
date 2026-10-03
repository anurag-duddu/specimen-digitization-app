"""Process logging that Cloud Logging can filter by severity, and a guard for log fields.

Neither the API nor the worker configured Python logging. A ``LOGGER.warning`` then
fell to the standard library's last-resort handler, which prints the bare message on
stderr; Cloud Logging recorded that at DEFAULT severity, so ``severity>=WARNING``
filters and alerts never saw it. Cloud Run reads one JSON object per stderr line as a
structured entry and takes its ``severity`` and ``message`` fields, so this module
installs a single root handler that writes exactly that and nothing else changes: the
root level stays at WARNING, so the same records are emitted as before.
"""

from __future__ import annotations

import json
import logging
import re
import sys

_HANDLER_NAME = "specimen-process-logging"
_CODE = re.compile(r"[A-Za-z0-9_:.\-]{1,160}")


def log_code(value: object) -> str:
    """Return ``value`` only when it has the shape of a fixed code.

    Blocker and failure codes in this repository are short identifiers. Anything
    else (free text, a multi-line message, a non-string) could carry label or
    provider text, so it is replaced rather than logged.
    """
    if isinstance(value, str) and _CODE.fullmatch(value):
        return value
    return "unrecognized"


def _severity(level: int) -> str:
    if level >= logging.CRITICAL:
        return "CRITICAL"
    if level >= logging.ERROR:
        return "ERROR"
    if level >= logging.WARNING:
        return "WARNING"
    if level >= logging.INFO:
        return "INFO"
    return "DEBUG"


class CloudLoggingFormatter(logging.Formatter):
    """One JSON object per record, on one line, with Cloud Logging's field names."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            message = f"{message}\n{self.formatStack(record.stack_info)}"
        return json.dumps(
            {
                "severity": _severity(record.levelno),
                "message": message,
                "logger": record.name,
            },
            default=str,
        )


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever ``sys.stderr`` is at emit time, as the last-resort handler does."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)

    @property
    def stream(self):
        return sys.stderr


def configure_process_logging() -> None:
    """Install the Cloud Logging handler on the root logger, once per process."""
    root = logging.getLogger()
    if any(handler.get_name() == _HANDLER_NAME for handler in root.handlers):
        return
    handler = _StderrHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(CloudLoggingFormatter())
    root.addHandler(handler)
