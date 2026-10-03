"""Process logging that Cloud Logging can filter by severity, and a guard for log fields.

Neither the API nor the worker configured Python logging. A ``LOGGER.warning`` then
fell to the standard library's last-resort handler, which prints the bare message on
stderr; Cloud Logging recorded that at DEFAULT severity, so ``severity>=WARNING``
filters and alerts never saw it. Cloud Run reads one JSON object per stderr line as a
structured entry and takes its ``severity`` and ``message`` fields, so this module
installs a single root handler that writes exactly that. The root level stays at
WARNING, so the same records are emitted as before, in a different shape. One library
logger is adjusted so a record is still written once (see ``_LIBRARY_LOGGERS``).
"""

from __future__ import annotations

import json
import logging
import re
import sys

HANDLER_NAME = "specimen-process-logging"
# huggingface_hub (a production dependency, imported by the API and worker modules)
# attaches its own plain stderr handler to its logger, which also propagates to the
# root. Left alone, each of its warnings would be written twice: its bare text line
# and the root handler's JSON line. Dropping that one handler lets the record reach
# the root handler once. If such a library is first imported after this call, its
# handler is attached afterwards and the duplicate returns for that library.
_LIBRARY_LOGGERS = ("huggingface_hub",)
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
    if any(handler.get_name() == HANDLER_NAME for handler in root.handlers):
        return
    handler = _StderrHandler()
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(CloudLoggingFormatter())
    root.addHandler(handler)
    for name in _LIBRARY_LOGGERS:
        library = logging.getLogger(name)
        for own in list(library.handlers):
            if type(own) is logging.StreamHandler and library.propagate:
                library.removeHandler(own)
