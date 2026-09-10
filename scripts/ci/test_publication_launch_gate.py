"""Real high-descriptor launch gate; local files/processes only."""
from contextlib import ExitStack
import json
import os
import subprocess
import sys
import time

import pytest

import release_publication_deadline as M


def test_high_descriptor_gate_preserves_command_and_waits_for_durable_record(tmp_path):
    output, recorded = tmp_path / "entered", tmp_path / "recorded"
    argument = "literal spaces $() ; ' \""
    env = {**os.environ, "GATE_TEST_VALUE": "literal environment"}
    events = []
    def retain(values):
        events[:] = values
        if values[-1]["event"] == "started":
            assert not output.exists()
            recorded.write_text("ownership recorded")
    script = ("import json,os,pathlib,sys; "
              f"assert pathlib.Path({str(recorded)!r}).read_text()=='ownership recorded'; "
              f"pathlib.Path({str(output)!r}).write_text(json.dumps([sys.argv[1],os.environ['GATE_TEST_VALUE']]))")
    with ExitStack() as stack:
        held = [stack.enter_context(open(os.devnull, "rb")) for _ in range(64)]
        assert min(handle.fileno() for handle in held[-10:]) > 9
        supervisor = M.Supervisor(M.Deadline(time.time() + 30), retain)
        supervisor.run_owned([sys.executable, "-c", script, argument], env=env, cwd=tmp_path,
                             stage="auth", limit=5)
    assert json.loads(output.read_text()) == [argument, "literal environment"]
    assert [value["event"] for value in events] == ["intent", "started", "completed"]
    assert not M.process_group_alive(supervisor.last_group)


@pytest.mark.parametrize("token", [b"", b"g", b"go\n", b"go\nx"])
def test_gate_eof_and_descriptor_lifetime(token, tmp_path):
    marker = tmp_path / "entered"
    script = f"""
import errno, os, pathlib, sys
try:
    os.fstat(int(sys.argv[1]))
except OSError as error:
    assert error.errno == errno.EBADF
else:
    raise AssertionError("gate descriptor survived exec")
pathlib.Path({str(marker)!r}).write_text("entered with gate closed")
"""
    with ExitStack() as stack:
        held = [stack.enter_context(open(os.devnull, "rb")) for _ in range(64)]
        assert held[-1].fileno() > 9
        read_gate, write_gate = os.pipe()
        try:
            if token:
                os.write(write_gate, token)
        finally:
            os.close(write_gate)
        try:
            result = subprocess.run([sys.executable, "-I", "-S", "-c", M.LAUNCH_GATE, str(read_gate),
                                     sys.executable, "-c", script, str(read_gate)],
                                    pass_fds=(read_gate,), capture_output=True, timeout=3)
        finally:
            os.close(read_gate)
    assert result.returncode == (0 if token == b"go\n" else 1)
    assert marker.exists() == (token == b"go\n")
