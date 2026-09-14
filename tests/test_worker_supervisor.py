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
        "pathlib.Path(sys.argv[1]).write_text(str(time.monotonic()+2)); time.sleep(2); "
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
    time.sleep(max(0, float((tmp_path / "ready").read_text()) + 0.05 - time.monotonic()))
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
    if sys.platform == "linux":
        import ctypes

        # This nested fixture represents the production PID1 supervisor. Keep
        # orphan adoption inside this child, never in the pytest process.
        assert ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
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
        with pytest.raises(ProcessLookupError):
            os.kill(int((tmp_path / "pid").read_text()), 0)
        with pytest.raises(ProcessLookupError):
            os.killpg(int((tmp_path / "worker_pid").read_text()), 0)
        time.sleep(max(0, float((tmp_path / "ready").read_text()) + 0.05 - time.monotonic()))
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


def adopted_group_cleanup_probe(directory):
    """Adoption is confined to this test child, never the pytest process."""
    import ctypes

    assert ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
    root = Path(directory)
    unrelated = subprocess.Popen([sys.executable, "-c", "raise SystemExit(23)"],
                                 start_new_session=True)
    # Observe without reaping: owned-group cleanup must leave this other status.
    os.waitid(os.P_PID, unrelated.pid, os.WEXITED | os.WNOWAIT)
    cases = []
    for hang in (False, True):
        case = root / str(hang)
        case.mkdir()
        result = run_isolated(leave_descendant,
                              {"ready": str(case / "ready"), "late": str(case / "late"),
                               "pid": str(case / "pid"), "hang": hang},
                              0.6, 100, process_group=True)
        pid = int((case / "pid").read_text())
        try:
            os.kill(pid, 0)
            absent = False
        except ProcessLookupError:
            absent = True
        time.sleep(max(0, float((case / "ready").read_text()) + 0.05 - time.monotonic()))
        cases.append({"hang": hang, "status": result.status,
                      "cleanup_complete": result.cleanup_complete,
                      "descendant_absent": absent, "late": (case / "late").exists(),
                      "elapsed": result.elapsed_seconds})
    pid, status = os.waitpid(unrelated.pid, os.WNOHANG)
    assert pid == unrelated.pid
    unrelated.returncode = os.waitstatus_to_exitcode(status)
    print(json.dumps({"cases": cases, "unrelated_exit": unrelated.returncode}))


@pytest.mark.skipif(sys.platform != "linux", reason="Linux adopted-child reaping")
def test_adopted_group_reaping_preserves_unrelated_child_status(tmp_path):
    result = subprocess.run([
        sys.executable, "-c", "import sys; sys.path.insert(0,sys.argv[2]); "
        "from test_worker_supervisor import adopted_group_cleanup_probe; "
        "adopted_group_cleanup_probe(sys.argv[1])", str(tmp_path),
        str(Path(__file__).resolve().parent),
    ], capture_output=True, text=True, timeout=8, check=True)
    report = json.loads(result.stdout)
    assert report["unrelated_exit"] == 23
    for case in report["cases"]:
        assert case["status"] == ("deadline_exceeded" if case["hang"] else "completed")
        assert case["cleanup_complete"] and case["descendant_absent"]
        assert not case["late"]
        assert case["elapsed"] < 2.7


def test_cleanup_observed_after_its_original_bound_is_incomplete(monkeypatch):
    from types import SimpleNamespace
    from specimen_digitization.application import bounded_effect

    clock = [0.0]
    def signal_group(pid, signum):
        if signum == 0:
            clock[0] = 2.001
            raise ProcessLookupError

    def no_adopted_child(*args):
        raise ChildProcessError

    monkeypatch.setattr(bounded_effect, "os", SimpleNamespace(
        killpg=signal_group, waitpid=no_adopted_child, WNOHANG=os.WNOHANG))
    monkeypatch.setattr(bounded_effect, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    process = SimpleNamespace(pid=424242, returncode=-9, wait=lambda timeout: None)
    assert not bounded_effect._cleanup(process, process_group=True)
    assert process.returncode == -9


def test_cleanup_clock_crossing_never_requests_negative_sleep(monkeypatch):
    from types import SimpleNamespace
    from specimen_digitization.application import bounded_effect

    samples = iter([0.0, 0.0, 0.0, 1.999, 2.001])
    sleeps = []

    def sleep(seconds):
        assert seconds >= 0
        sleeps.append(seconds)

    def no_adopted_child(*args):
        raise ChildProcessError

    monkeypatch.setattr(bounded_effect, "os", SimpleNamespace(
        killpg=lambda *args: None, waitpid=no_adopted_child, WNOHANG=os.WNOHANG))
    monkeypatch.setattr(bounded_effect, "time", SimpleNamespace(
        monotonic=lambda: next(samples, 2.001), sleep=sleep))
    process = SimpleNamespace(pid=424242, returncode=-9, wait=lambda timeout: None)
    assert not bounded_effect._cleanup(process, process_group=True)
    assert sum(sleeps) < 0.002


@pytest.mark.parametrize("deny_kill", [False, True])
def test_cleanup_permission_uncertainty_does_not_restart_its_bound(monkeypatch, deny_kill):
    from types import SimpleNamespace
    from specimen_digitization.application import bounded_effect

    clock, signals, probes = [0.0], [], []
    def signal_group(pid, signum):
        if signum == signal.SIGKILL:
            signals.append(signum)
            if deny_kill:
                raise PermissionError
        else:
            probes.append(signum)
            if len(probes) == 1:
                raise PermissionError
            raise ProcessLookupError

    def no_adopted_child(*args):
        raise ChildProcessError

    monkeypatch.setattr(bounded_effect, "os", SimpleNamespace(
        killpg=signal_group, waitpid=no_adopted_child, WNOHANG=os.WNOHANG))
    monkeypatch.setattr(bounded_effect, "time", SimpleNamespace(
        monotonic=lambda: clock[0], sleep=lambda delay: clock.__setitem__(0, clock[0]+delay)))
    process = SimpleNamespace(pid=424242, returncode=-9, wait=lambda timeout: None)
    assert bounded_effect._cleanup(process, process_group=True) is (not deny_kill)
    assert signals == [signal.SIGKILL]
    assert probes == ([] if deny_kill else [0, 0])
    assert clock[0] < 2
