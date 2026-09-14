"""Fast importable synthetic subprocess fixtures with no service clients."""

from pathlib import Path
import sys
import time
from types import SimpleNamespace


def child_deadline_and_flush(payload):
    from specimen_digitization.application.bounded_effect import current_effect_deadline

    deadline = current_effect_deadline()
    Path(payload["deadline"]).write_text(str(deadline))

    def flush():
        Path(payload["flush"]).write_text("once")
        if payload.get("stall"):
            time.sleep(30)
        # Model configuration has already loaded its local ledger module. This
        # fixture loads it explicitly without installing a native transport.
        from specimen_digitization import bounded_telemetry  # noqa: F401

        if payload.get("raise"):
            raise RuntimeError("PRIVATE-CANARY")
        return {"configured": True, "complete": payload["complete"]}

    sys.modules["specimen_digitization.observability"] = SimpleNamespace(
        flush_bounded_observability=flush,
    )
    if payload.get("record_failure"):
        from specimen_digitization.bounded_telemetry import Ledger

        def unavailable(*args, **kwargs):
            raise RuntimeError("synthetic local receipt failure")

        Ledger.record_completion = unavailable
    return b"known model output"


def generic_child_without_tracing(payload):
    """Generic helpers must not inspect a writer credential or drain telemetry."""
    import os

    getenv = os.getenv

    def guarded_getenv(name, *args):
        if name == "LOGFIRE_TOKEN":
            Path(payload["unexpected"]).write_text("credential lookup")
            raise AssertionError("generic helper must not read a writer token")
        return getenv(name, *args)

    os.getenv = guarded_getenv
    if payload.get("loaded"):
        def forbidden_flush():
            Path(payload["unexpected"]).write_text("flush")
            raise AssertionError("generic helper must not flush")

        sys.modules["specimen_digitization.observability"] = SimpleNamespace(
            flush_bounded_observability=forbidden_flush,
        )
    return b"known generic response"
