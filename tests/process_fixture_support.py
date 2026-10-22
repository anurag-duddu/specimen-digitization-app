"""Bounded cleanup for process groups created by HTTP test fixtures."""

from contextlib import contextmanager
import os
import signal
import subprocess
import time


def _signal_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _wait_for_group_exit(process, timeout):
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            # A denied probe does not establish absence (including while an
            # orphan is exiting under a sandbox). Require actual ESRCH.
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Owned process group {process.pid} did not disappear "
                f"within {timeout} seconds after KILL/reap"
            )
        time.sleep(min(0.01, remaining))


@contextmanager
def owned_process(command, **kwargs):
    """Own a fresh group from spawn through startup, test body and teardown."""
    process = subprocess.Popen(command, start_new_session=True, **kwargs)
    try:
        yield process
    finally:
        try:
            _signal_group(process, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        finally:
            # Kill surviving descendants even when the direct child exited on
            # TERM (or exited before teardown), then reap the direct child.
            deadline = time.monotonic() + 10
            try:
                _signal_group(process, signal.SIGKILL)
            finally:
                remaining = max(0, deadline - time.monotonic())
                process.wait(timeout=remaining)
            # wait() only observes the leader; after it has been reaped its
            # cached return code says nothing about surviving descendants.
            # Share the existing final-wait budget with group observation.
            _wait_for_group_exit(process, timeout=max(0, deadline - time.monotonic()))
