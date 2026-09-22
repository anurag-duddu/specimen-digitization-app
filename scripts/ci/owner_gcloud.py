"""Counted, deadline-bound gcloud invocations for the owner's bounded setup helpers.

The owner-side helpers (`data_setup_window.py`, `worker_trace_setup.py`) reach
the cloud only through this module. Every invocation is counted against the
helper's planned request budget, refused once the helper's clock has run out,
and pinned to the release project. Nothing here retries, follows a redirect or
prints a credential; the helpers decide what each response means.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from release_admission import require, strict_json
from release_context import PROJECT

STAMP = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
REQUEST_TIMEOUT_SECONDS = 30.0


def stamp(unix: float) -> str:
    """RFC 3339 UTC instant with whole seconds, the form IAM conditions use."""
    return datetime.fromtimestamp(int(unix), timezone.utc).strftime(STAMP_FORMAT)


def parse_stamp(text: str) -> int:
    require(isinstance(text, str) and re.fullmatch(STAMP, text) is not None,
            "RFC 3339 UTC instant with a Z suffix required")
    return int(datetime.strptime(text, STAMP_FORMAT).replace(tzinfo=timezone.utc).timestamp())


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def durable_write(path: Path, payload, *, exclusive: bool = False) -> bytes:
    """Write owner-only JSON and fsync it; `exclusive` refuses an existing file."""
    raw = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise ValueError(f"{path} already exists; a recorded effect is never replayed") from None
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return raw


class Gcloud:
    """The single path to the cloud: counted, project-pinned, deadline-bound."""

    def __init__(self, deadline_unix: float, *, ceiling: int, runner=None, clock=time.time):
        require(isinstance(ceiling, int) and ceiling > 0, "request ceiling required")
        self.deadline = float(deadline_unix)
        self.ceiling = ceiling
        self.runner = runner or self._subprocess
        self.clock = clock
        self.calls: list[list[str]] = []

    @staticmethod
    def _subprocess(args: list[str], timeout: float) -> tuple[int, str, str]:
        completed = subprocess.run(["gcloud", *args], capture_output=True, text=True,
                                   timeout=timeout, check=False)
        return completed.returncode, completed.stdout, completed.stderr

    def __call__(self, *args: str) -> tuple[int, str, str]:
        remaining = self.deadline - self.clock()
        require(remaining > 0, "the helper's clock has run out; nothing further is sent")
        require(len(self.calls) < self.ceiling, "planned request count exhausted; nothing further is sent")
        self.calls.append(list(args))
        return self.runner([*args, f"--project={PROJECT}", "--quiet"],
                           min(REQUEST_TIMEOUT_SECONDS, remaining))

    def json(self, *args: str):
        code, out, err = self(*args)
        require(code == 0, f"gcloud {' '.join(args[:3])} failed: {err.strip()[:240]}")
        return strict_json(out)
