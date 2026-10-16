"""Fault probes for cleanup in the real HTTP process fixtures."""

import os
import select
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

import test_http_process_restart as restart
import test_upload_completion_http as upload
import process_fixture_support as support
from process_fixture_support import owned_process


class StartupFault(RuntimeError):
    """Unexpected readiness failure after the fixture has spawned its child."""


def _assert_reaped(process):
    assert process.returncode is not None, "owned child was not waited/reaped"
    with pytest.raises(ChildProcessError):
        os.waitpid(process.pid, os.WNOHANG)
    with pytest.raises(ProcessLookupError):
        os.killpg(process.pid, 0)


@pytest.fixture
def child_factory(monkeypatch):
    """Keep fault children independent and recover them even on a red run."""
    popen = subprocess.Popen
    children = []
    calls = []
    waits = []

    def spawn(*args, resistant=False, **kwargs):
        calls.append({"start_new_session": kwargs.get("start_new_session")})
        script = (
            "import signal, time; "
            + ("signal.signal(signal.SIGTERM, signal.SIG_IGN); " if resistant else "")
            + "print('ready', flush=True); time.sleep(60)"
        )
        process = popen(
            [sys.executable, "-u", "-c", script],
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        children.append(process)
        wait = process.wait
        waits.append(wait)
        assert select.select([process.stdout], [], [], 5)[0], "fault child not ready"
        assert process.stdout.readline() == b"ready\n"

        def bounded_wait(timeout=None):
            # Inject a short teardown budget; never permit an unbounded wait.
            assert timeout is not None, "fixture used an unbounded child wait"
            return wait(timeout=min(timeout, 0.1))

        monkeypatch.setattr(process, "wait", bounded_wait)
        return process

    try:
        yield spawn, children, calls
    finally:
        # This safety net is independent of the implementation under test.
        for process, wait in zip(children, waits):
            try:
                # Assertions have already checked reaping. Avoid signalling a
                # dead, unreaped child while recovering a deliberately bad helper.
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            finally:
                try:
                    wait(timeout=5)
                finally:
                    process.stdout.close()
                    process.stderr.close()


def _startup_fault(monkeypatch, tmp_path, fixture_kind, spawn):
    monkeypatch.setattr(subprocess, "Popen", spawn)

    def fail(*args, **kwargs):
        raise StartupFault("injected readiness failure")

    if fixture_kind == "upload":
        monkeypatch.setattr(upload.httpx, "Client", fail)
        fixture = upload.tcp_client.__wrapped__(tmp_path, SimpleNamespace())
        try:
            next(fixture)
        finally:
            fixture.close()
    else:
        # Direct invocation exercises startup ownership without needing SQL.
        monkeypatch.delenv("SPECIMEN_TEST_HTTP_PORT", raising=False)
        monkeypatch.setattr(restart.httpx, "get", fail)
        restart.test_sql_http_restart(tmp_path)


@pytest.mark.parametrize("fixture_kind", ["upload", "restart"])
def test_startup_exception_reaps_owned_child(
    monkeypatch, tmp_path, child_factory, fixture_kind
):
    spawn, children, calls = child_factory
    with pytest.raises(StartupFault, match="injected readiness failure"):
        _startup_fault(monkeypatch, tmp_path, fixture_kind, spawn)
    assert len(children) == 1, "fault did not reach child startup"
    _assert_reaped(children[0])
    assert calls[0].get("start_new_session") is True, "child group was not owned at spawn"


@pytest.mark.parametrize("fixture_kind", ["upload", "restart"])
def test_term_resistant_child_is_killed_and_waited(
    monkeypatch, tmp_path, child_factory, fixture_kind
):
    spawn, children, _ = child_factory

    def resistant(*args, **kwargs):
        return spawn(*args, resistant=True, **kwargs)

    with pytest.raises(StartupFault, match="injected readiness failure"):
        _startup_fault(monkeypatch, tmp_path, fixture_kind, resistant)
    assert len(children) == 1, "fault did not reach TERM-resistant child"
    assert children[0].returncode == -signal.SIGKILL, "TERM-resistant child escaped KILL/reap"
    _assert_reaped(children[0])


@pytest.mark.parametrize("fixture_kind", ["upload", "restart"])
def test_competing_process_is_untouched(
    monkeypatch, tmp_path, child_factory, fixture_kind
):
    spawn, children, _ = child_factory
    competitor = spawn()
    with pytest.raises(StartupFault, match="injected readiness failure"):
        _startup_fault(monkeypatch, tmp_path, fixture_kind, spawn)
    assert len(children) == 2, "fault did not create owned and competing children"
    _assert_reaped(children[1])
    assert competitor.poll() is None, "cleanup signalled an unrelated child"
    os.kill(competitor.pid, 0)


def test_owned_group_includes_descendant():
    # Parent survives TERM until it has reaped the descendant. Signalling only
    # the parent would leave both this wait and the descendant alive.
    child_script = (
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_DFL); "
        "print('ready', flush=True); time.sleep(60)"
    )
    parent_script = (
        "import signal, subprocess, sys; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"child = subprocess.Popen([sys.executable, '-u', '-c', {child_script!r}], "
        "stdout=subprocess.PIPE); "
        "assert child.stdout.readline() == b'ready\\n'; "
        "print(child.pid, flush=True); child.wait()"
    )
    process = None
    try:
        with owned_process(
            [sys.executable, "-u", "-c", parent_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            assert select.select([process.stdout], [], [], 5)[0], "group not ready"
            line = process.stdout.readline()
            assert line.strip().isdigit(), "descendant readiness PID missing"
            descendant = int(line)
            assert os.getpgid(process.pid) == process.pid
            assert os.getpgid(descendant) == process.pid
            assert process.pid != os.getpgrp(), "fixture owns the test runner group"
        _assert_reaped(process)
        with pytest.raises(ProcessLookupError):
            os.kill(descendant, 0)
    finally:
        if process is not None:
            try:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            finally:
                try:
                    process.wait(timeout=5)
                finally:
                    process.stdout.close()
                    process.stderr.close()


def test_term_resistant_descendant_is_gone_when_cleanup_returns(child_factory):
    spawn, _, _ = child_factory
    competitor = spawn()
    child_script = (
        "import os, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print(os.getpid(), flush=True); time.sleep(60)"
    )
    # The leader exits on TERM before the descendant has received KILL.
    # Waiting again on that reaped leader cannot establish group completion.
    parent_script = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-u', '-c', {child_script!r}]); "
        "time.sleep(60)"
    )
    process = None
    try:
        with owned_process(
            [sys.executable, "-u", "-c", parent_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            assert select.select([process.stdout], [], [], 5)[0], "descendant not ready"
            line = process.stdout.readline()
            assert line.strip().isdigit(), "descendant readiness PID missing"
            descendant = int(line)
            assert os.getpgid(process.pid) == process.pid
            assert os.getpgid(descendant) == process.pid
            assert process.pid != os.getpgrp(), "fixture owns the test runner group"
        # Assert immediately: a recovery wait must not conceal early return.
        assert process.returncode == -signal.SIGTERM, "leader did not exit on TERM"
        with pytest.raises(ProcessLookupError):
            os.kill(descendant, 0)
        _assert_reaped(process)
        assert select.select([process.stdout], [], [], 0)[0], "descendant pipe still open"
        assert process.stdout.read() == b"", "descendant output pipe did not reach EOF"
        assert competitor.poll() is None, "cleanup signalled an unrelated child"
        os.kill(competitor.pid, 0)
    finally:
        # Independent recovery also waits for the group, including on red runs.
        if process is not None:
            try:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            finally:
                try:
                    process.wait(timeout=5)
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            os.killpg(process.pid, 0)
                        except ProcessLookupError:
                            break
                        except PermissionError:
                            # EPERM is not evidence of absence under a sandbox.
                            pass
                        assert time.monotonic() < deadline, "recovery: group still exists"
                        time.sleep(0.001)
                finally:
                    process.stdout.close()
                    process.stderr.close()


@pytest.mark.parametrize("permission_denied", [False, True])
def test_group_exit_wait_is_bounded_and_reports_owned_group(monkeypatch, permission_denied):
    clock = [0.0]
    probes = []

    def probe(pgid, signum):
        probes.append((pgid, signum))
        if permission_denied:
            raise PermissionError("group probe denied")

    def advance(seconds):
        assert 0 < seconds <= 0.01, "group wait used an unbounded sleep"
        clock[0] += seconds

    monkeypatch.setattr(support.os, "killpg", probe)
    monkeypatch.setattr(support.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(support.time, "sleep", advance)
    with pytest.raises(TimeoutError, match="Owned process group 12345.*disappear"):
        support._wait_for_group_exit(SimpleNamespace(pid=12345), timeout=0.03)
    assert clock[0] == pytest.approx(0.03), "group wait exceeded its original bound"
    assert probes and set(probes) == {(12345, 0)}, "wait probed outside its owned group"
