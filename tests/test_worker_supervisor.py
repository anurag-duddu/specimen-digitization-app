"""Only synthetic processes and local files; no production clients or model calls."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from specimen_digitization.application.bounded_effect import run_isolated
from specimen_digitization.application.worker_deadline import current_deadline


def retained_window_then_hang(payload):
    current_deadline().tighten_until(time.time() + 0.3, time.time())
    Path(payload["started"]).write_text("started")
    time.sleep(10)
    Path(payload["late"]).write_text("late mutation")
    return b"late success"


def leave_descendant(payload):
    if payload.get("worker_pid"):
        Path(payload["worker_pid"]).write_text(str(os.getpid()))
    child = subprocess.Popen([
        sys.executable, "-c",
        "import signal,time,pathlib,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(2); "
        "pathlib.Path(sys.argv[2]).write_text('late mutation')",
        payload["ready"], payload["late"],
    ])
    Path(payload["pid"]).write_text(str(child.pid))
    while not Path(payload["ready"]).exists():
        time.sleep(0.01)
    if payload["hang"]:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(10)
    return b"parent exited"


def stalled_materialization(payload):
    from contextlib import contextmanager
    from specimen_digitization.application import worker

    @contextmanager
    def stalled(args):
        Path(payload["started"]).write_text("materialization started")
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(10)
        Path(payload["late"]).write_text("materialization finished")
        yield args

    worker.materialized_worker_args = stalled
    worker._run = lambda args: print("must not reach native setup")
    return worker._production_operation({"mode": "production"})


def test_retained_deadline_stops_blocking_parent_before_new_cli_window(tmp_path):
    result = run_isolated(retained_window_then_hang,
                          {"started": str(tmp_path / "started"), "late": str(tmp_path / "late")},
                          5, 100, process_group=True)
    assert (tmp_path / "started").exists()
    assert not (tmp_path / "late").exists()
    assert result.status == "deadline_exceeded" and result.value is None
    assert result.elapsed_seconds < 2
    assert result.cleanup_complete


@pytest.mark.parametrize("hang", [False, True])
def test_owned_group_kills_descendant_even_when_leader_has_exited(tmp_path, hang):
    result = run_isolated(leave_descendant,
                          {"ready": str(tmp_path / "ready"), "late": str(tmp_path / "late"),
                           "pid": str(tmp_path / "pid"), "hang": hang},
                          0.6, 100, process_group=True)
    assert (tmp_path / "ready").exists()
    assert result.status == ("deadline_exceeded" if hang else "completed")
    assert result.cleanup_complete
    pid = int((tmp_path / "pid").read_text())
    # Allow the OS to reap an orphan killed with the owned group.
    end = time.monotonic() + 1
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        pytest.fail("descendant survived process-group cleanup")
    assert not (tmp_path / "late").exists()
    assert result.elapsed_seconds < 4


def test_startup_and_materialization_share_supervisor_original_clock(tmp_path):
    result = run_isolated(stalled_materialization,
                          {"started": str(tmp_path / "started"), "late": str(tmp_path / "late")},
                          2, 1000, process_group=True)
    assert (tmp_path / "started").exists()
    assert not (tmp_path / "late").exists()
    assert result.status == "deadline_exceeded" and result.value is None
    assert result.cleanup_complete
    assert result.elapsed_seconds < 5


def test_cli_supervisor_timeout_is_sanitized_unknown_and_nonzero(monkeypatch, capsys):
    from argparse import Namespace
    from specimen_digitization.application import worker, bounded_effect

    calls = []

    def timeout(function, payload, seconds, maximum, **kwargs):
        calls.append((seconds, kwargs))
        return bounded_effect.IsolatedResult("deadline_exceeded", None, 1501, 1, 0,
                                             "sensitive synthetic detail", cleanup_complete=True)

    monkeypatch.setattr(bounded_effect, "run_isolated", timeout)
    with pytest.raises(SystemExit) as exc:
        worker._supervise(Namespace(max_seconds=1500))
    assert exc.value.code == 2
    report = json.loads(capsys.readouterr().out)
    assert report == {"status": "incomplete", "authorized": 10,
                      "reason": "pilot_execution_outcome_unknown", "cleanup_complete": True}
    assert calls == [(1500, {"process_group": True})]


def signal_supervisor(directory):
    root = Path(directory)
    result = run_isolated(leave_descendant,
                          {"ready": str(root / "ready"), "late": str(root / "late"),
                           "pid": str(root / "pid"), "worker_pid": str(root / "worker_pid"), "hang": True},
                          10, 100, process_group=True)
    (root / "report").write_text(json.dumps({"status": result.status, "clean": result.cleanup_complete}))


def test_supervisor_term_cleans_owned_process_group(tmp_path):
    outer = subprocess.Popen([sys.executable, "-c",
                              "import sys; sys.path.insert(0, sys.argv[2]); "
                              "from test_worker_supervisor import signal_supervisor; signal_supervisor(sys.argv[1])",
                              str(tmp_path), str(Path(__file__).resolve().parent)])
    try:
        end = time.monotonic() + 3
        while not (tmp_path / "ready").exists() and time.monotonic() < end:
            time.sleep(0.01)
        assert (tmp_path / "ready").exists()
        outer.terminate()
        outer.wait(timeout=4)
        assert (tmp_path / "report").exists(), "Supervisor must finish owned cleanup on TERM"
        assert json.loads((tmp_path / "report").read_text()) == {"status": "deadline_exceeded", "clean": True}
        assert not (tmp_path / "late").exists()
    finally:
        # The preserved RED must not leave the deliberately stubborn fixture alive.
        if (tmp_path / "worker_pid").exists():
            try:
                os.killpg(int((tmp_path / "worker_pid").read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if outer.poll() is None:
            outer.kill()
            outer.wait(timeout=2)


def test_production_operation_preserves_review_required_exit_without_replay(monkeypatch):
    from contextlib import contextmanager
    from specimen_digitization.application import worker
    from specimen_digitization.application.worker_deadline import WorkerDeadline

    original = WorkerDeadline(time.monotonic() + 10)
    calls = []

    @contextmanager
    def materialize(args):
        assert current_deadline() is original
        calls.append("materialize")
        yield args

    def finish(args):
        assert current_deadline() is original
        calls.append("run")
        print(json.dumps({"status": "evidence_review_required", "authorized": 10}))
        raise SystemExit(2)

    monkeypatch.setattr(worker, "materialized_worker_args", materialize)
    monkeypatch.setattr(worker, "_run", finish)
    with original.scope():
        report = json.loads(worker._production_operation({"mode": "production"}))
    assert report["exit_code"] == 2
    assert json.loads(report["output"]) == {"status": "evidence_review_required", "authorized": 10}
    assert calls == ["materialize", "run"]
