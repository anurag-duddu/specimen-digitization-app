"""Synthetic SDK continuation after the supervised worker's graceful TERM."""
from pathlib import Path
import signal
import time

from specimen_digitization.application.bounded_effect import run_isolated
from specimen_digitization.application.worker_deadline import current_deadline, deadline_call


def sdk_continuation(payload):
    import threading
    # The production _run installs this graceful-stop handler. A blocked SDK
    # does not inspect that event before its own subsequent transport action.
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *args: stop.set())
    Path(payload['started']).write_text('started')

    def sdk_call():
        time.sleep(max(0, current_deadline().remaining()) + 0.15)
        Path(payload['late']).write_text('next SDK dispatch after deadline')
        return b'late'

    return deadline_call(sdk_call)


def test_no_sdk_continuation_dispatch_during_termination_grace(tmp_path):
    result = run_isolated(sdk_continuation,
        {'started': str(tmp_path / 'started'), 'late': str(tmp_path / 'late')},
        2, 100, process_group=True)
    assert (tmp_path / 'started').exists()
    assert result.status == 'deadline_exceeded'
    assert result.cleanup_complete
    assert not (tmp_path / 'late').exists(), 'SDK continued dispatch after expiry during TERM grace'


def actual_production_handler_continuation(payload):
    """Real _run handler installation, with every native setup edge replaced."""
    from argparse import Namespace
    from datetime import datetime, timedelta, timezone
    import os
    from types import SimpleNamespace
    from specimen_digitization.application import worker
    from specimen_digitization import observability

    observability.configure_observability = lambda **kwargs: None
    worker.production_launch = lambda args: SimpleNamespace(
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60), timing=None)
    os.environ["SPECIMEN_WORKER_ACTOR_UID"] = "synthetic-deadline-fixture"

    def sdk_constructor():
        handler = signal.getsignal(signal.SIGTERM)
        Path(payload["started"]).write_text(handler.__qualname__)
        time.sleep(max(0, current_deadline().remaining()) + 0.15)
        Path(payload["late"]).write_text("SDK continued after production handler returned")
        raise RuntimeError("synthetic SDK failure")

    worker.SqlConnectRepository = sdk_constructor
    worker.GcsBlobs = lambda: (_ for _ in ()).throw(AssertionError("No native Storage"))
    worker._run(Namespace(mode="production", evidence_only=False, check_config=False))
    return b"unexpected success"


def test_actual_production_handler_cannot_allow_sdk_continuation(tmp_path):
    result = run_isolated(actual_production_handler_continuation,
                         {"started": str(tmp_path / "started"), "late": str(tmp_path / "late")},
                         2, 100, process_group=True)
    assert (tmp_path / "started").read_text() == "_run.<locals>.<lambda>"
    assert result.status == "deadline_exceeded" and result.cleanup_complete
    assert not (tmp_path / "late").exists()


def resistant_descendant_continuation(payload):
    import subprocess
    import sys

    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    child = subprocess.Popen([
        sys.executable, "-c",
        "import pathlib,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "pathlib.Path(sys.argv[1]).write_text('ready'); "
        "time.sleep(max(0,float(sys.argv[3])-time.monotonic())); "
        "pathlib.Path(sys.argv[2]).write_text('late descendant dispatch'); time.sleep(10)",
        payload["started"], payload["late"], str(current_deadline().deadline + 0.15),
    ])
    child.wait()
    return b"unexpected success"


def test_term_resistant_descendant_cannot_dispatch_during_cleanup(tmp_path):
    result = run_isolated(resistant_descendant_continuation,
                         {"started": str(tmp_path / "started"), "late": str(tmp_path / "late")},
                         0.6, 100, process_group=True)
    assert (tmp_path / "started").exists()
    assert result.status == "deadline_exceeded" and result.cleanup_complete
    assert not (tmp_path / "late").exists()


def newly_shortened_window_continuation(payload):
    deadline = current_deadline()
    origin = deadline.deadline - 5
    # Publish shortly after a supervisor poll; a much shorter retained window
    # must be enforced before the child can dispatch more useful work.
    phase = (int((time.monotonic() - origin) / 0.1) + 1) * 0.1 + 0.02
    time.sleep(max(0, origin + phase - time.monotonic()))
    deadline.tighten_until(time.time() + 0.01, time.time())

    def sdk_call():
        time.sleep(0.03)
        Path(payload["late"]).write_text("dispatch before supervisor learned retained cutoff")
        return b"late"

    return deadline_call(sdk_call)


def test_new_retained_cutoff_is_enforced_before_child_can_continue(tmp_path):
    result = run_isolated(newly_shortened_window_continuation,
                         {"late": str(tmp_path / "late")}, 5, 100, process_group=True)
    assert result.status == "deadline_exceeded" and result.cleanup_complete
    assert not (tmp_path / "late").exists()
