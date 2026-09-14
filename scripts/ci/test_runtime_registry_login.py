"""Actual registry-login method and callers with synthetic credentials/transport."""
import hashlib
import json
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import deploy_runtime as runtime
import release_google as google
import release_publication_deadline as publication


@pytest.fixture
def login(monkeypatch):
    from google.auth.transport import requests

    def denied(*args, **kwargs):
        pytest.fail("Real network, credential acquisition and subprocesses are forbidden")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(requests, "Request", lambda: "synthetic-request")
    monkeypatch.setattr(publication, "CURRENT", None)
    monkeypatch.setattr(publication, "BOUND_PACKET", None)
    events = []
    client = google.Google.__new__(google.Google)
    client.packet = {"expires_at_unix": int(time.time()) + 120}
    client.credentials = SimpleNamespace(token="synthetic-old-value")

    def refresh(request):
        assert request == "synthetic-request"
        assert signal.getitimer(signal.ITIMER_REAL)[0] > 0
        events.append("refresh")
        client.credentials.token = "synthetic-refreshed-value"

    def docker(command, **kwargs):
        assert command == ["docker", "login", "-u", "oauth2accesstoken", "--password-stdin",
                           "https://us-east4-docker.pkg.dev"]
        assert kwargs.keys() == {"input", "capture_output", "timeout"}
        assert kwargs["input"] == b"synthetic-refreshed-value"
        assert kwargs["capture_output"] is True and 0 < kwargs["timeout"] <= 30
        assert signal.getitimer(signal.ITIMER_REAL)[0] > 0
        events.append(("docker", kwargs["timeout"]))
        return SimpleNamespace(returncode=0)

    client.credentials.refresh = refresh
    monkeypatch.setattr(google.subprocess, "run", docker)

    def select(plane):
        client.plane = plane
        if plane == "runtime-build":
            monkeypatch.setattr(publication, "CURRENT", publication.Deadline(client.packet["expires_at_unix"]))
            monkeypatch.setattr(publication, "BOUND_PACKET", client.packet.copy())
        return client, events

    return select


@pytest.mark.parametrize("plane", ["runtime", "runtime-build"])
def test_approved_planes_refresh_once_and_login_with_current_value(login, plane):
    client, events = login(plane)
    previous = signal.getsignal(signal.SIGALRM)
    client.registry_login()
    assert len(events) == 2 and events[0] == "refresh" and events[1][0] == "docker"
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == previous


@pytest.mark.parametrize("plane", ["data", "data-initialization", "hosting", "production", "runtime-other", "", None])
def test_unrelated_planes_fail_before_refresh_or_login(login, plane):
    client, events = login(plane)
    with pytest.raises(ValueError):
        client.registry_login()
    assert events == []


@pytest.mark.parametrize("plane", ["runtime", "runtime-build"])
def test_expired_original_packet_never_refreshes(login, monkeypatch, plane):
    client, events = login(plane)
    client.packet["expires_at_unix"] = int(time.time()) - 1
    if plane == "runtime-build":
        monkeypatch.setattr(publication, "BOUND_PACKET", client.packet.copy())
        monkeypatch.setattr(publication, "CURRENT", publication.Deadline(client.packet["expires_at_unix"]))
    with pytest.raises(ValueError):
        client.registry_login()
    assert events == []


@pytest.mark.parametrize("plane", ["runtime", "runtime-build"])
def test_failed_refresh_is_not_retried_and_never_logs_in(login, monkeypatch, plane):
    client, events = login(plane)

    def failed(request):
        events.append("failed-refresh")
        raise RuntimeError("synthetic refresh failure")

    monkeypatch.setattr(client.credentials, "refresh", failed)
    with pytest.raises(RuntimeError, match="synthetic refresh failure"):
        client.registry_login()
    assert events == ["failed-refresh"]
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


@pytest.mark.parametrize("plane", ["runtime", "runtime-build"])
@pytest.mark.parametrize("failure", ["rejected", "timeout"])
def test_login_failure_is_not_retried_and_clears_alarm(login, monkeypatch, plane, failure):
    client, events = login(plane)

    def failed(command, **kwargs):
        events.append("failed-login")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(google.subprocess, "run", failed)
    expected = subprocess.TimeoutExpired if failure == "timeout" else ValueError
    with pytest.raises(expected):
        client.registry_login()
    assert events == ["refresh", "failed-login"]
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def alarm_case_probe(plane, phase, watchdog_path, native_stall=False):
    """The real C hard watchdog may exit; it must never own the pytest runner."""
    monkeypatch = pytest.MonkeyPatch()
    client, events = login.__wrapped__(monkeypatch)(plane)
    owner, name = ((google, "request_deadline") if plane == "runtime" and phase == "login"
                   else (publication, "total_request"))
    guard = getattr(owner, name)
    monkeypatch.setattr(owner, name, lambda seconds: guard(min(seconds, .08)))
    hard = {"armed": False, "seconds": None}
    watchdog = open(watchdog_path, "w")
    arm = publication.faulthandler.dump_traceback_later
    cancel = publication.faulthandler.cancel_dump_traceback_later

    def armed(seconds, **kwargs):
        assert kwargs["exit"] is True
        arm(seconds, **{**kwargs, "file": watchdog})
        hard.update(armed=True, seconds=seconds)

    def cancelled():
        cancel()
        hard.update(armed=False, seconds=None)

    monkeypatch.setattr(publication.faulthandler, "dump_traceback_later", armed)
    monkeypatch.setattr(publication.faulthandler, "cancel_dump_traceback_later", cancelled)

    def stalled(*args, **kwargs):
        events.append("stalled-" + phase)
        print(json.dumps({"event": "started", "at": time.monotonic(), "events": events,
                          "hard_armed": hard["armed"], "hard_seconds": hard["seconds"]}), flush=True)
        if native_stall:
            hashlib.pbkdf2_hmac("sha256", b"synthetic", b"fixture", 10_000_000)
        else:
            time.sleep(1)
        print(json.dumps({"event": "late"}), flush=True)
        raise AssertionError("deadline did not stop synthetic stall")

    monkeypatch.setattr(client.credentials if phase == "refresh" else google.subprocess,
                        "refresh" if phase == "refresh" else "run", stalled)
    began = time.monotonic()
    previous = signal.getsignal(signal.SIGALRM)
    expected = ValueError if plane == "runtime" and phase == "refresh" else (TimeoutError, publication.RequestExpired)
    try:
        with pytest.raises(expected):
            client.registry_login()
        assert time.monotonic() - began < .5
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
        assert signal.getsignal(signal.SIGALRM) == previous
        print(json.dumps({"event": "soft_interrupt", "events": events}), flush=True)
    finally:
        monkeypatch.undo()
        watchdog.close()


def assert_guarded_hard_watchdog_stack(dump):
    """Only the blocked call or its exact guarded unwind can explain hard exit."""
    stalled = [("test_runtime_registry_login.py", "stalled"),
               ("release_google.py", "registry_login"),
               ("test_runtime_registry_login.py", "alarm_case_probe")]
    unwind = [("test_runtime_registry_login.py", "cancelled"),
              ("release_publication_deadline.py", "total_request"),
              ("contextlib.py", "__exit__"),
              *stalled[1:]]
    for stack in (stalled, unwind):
        pattern = r"^(?:Thread|Current thread) 0x[0-9a-fA-F]+ \(most recent call first\):\n"
        pattern += "".join(
            r'  File "[^"\n]*/' + re.escape(filename) + r'", line [0-9]+ in '
            + re.escape(function) + r"\n" for filename, function in stack
        )
        if re.search(pattern, dump, re.MULTILINE):
            return
    pytest.fail("hard watchdog must stop the stalled call or its guarded unwind")


@pytest.mark.parametrize(("plane", "phase", "native_stall"), [
    ("runtime", "refresh", False),
    ("runtime-build", "refresh", False),
    ("runtime", "login", False),
    ("runtime-build", "login", False),
    ("runtime", "refresh", True),
])
def test_shared_real_alarm_interrupts_stalled_refresh_or_login(tmp_path, plane, phase, native_stall):
    watchdog_path = tmp_path / "hard-watchdog.txt"
    result = subprocess.run([
        sys.executable, "-c", "import sys; sys.path.insert(0,sys.argv[1]); "
        "from test_runtime_registry_login import alarm_case_probe; "
        "alarm_case_probe(sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5]=='True')",
        str(Path(__file__).parent), plane, phase, str(watchdog_path), str(native_stall),
    ], capture_output=True, text=True, timeout=3)
    ended = time.monotonic()
    (tmp_path / "child.stdout").write_text(result.stdout)
    (tmp_path / "child.stderr").write_text(result.stderr)
    dump = watchdog_path.read_text()
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert lines and lines[0]["event"] == "started", (result.returncode, result.stdout, result.stderr)
    assert ended - lines[0]["at"] < .5
    expected = ["stalled-refresh"] if phase == "refresh" else ["refresh", "stalled-login"]
    assert lines[0]["events"] == expected
    assert result.stderr == ""
    if result.returncode == 0:
        assert not native_stall and dump == ""
        assert lines[1:] == [{"event": "soft_interrupt", "events": expected}]
    else:
        # Only the deliberately armed 80 ms C hard exit is an alternative to
        # Python's 72 ms signal. No other nonzero/late/event sequence is accepted.
        assert result.returncode == 1 and len(lines) == 1
        assert (plane, phase) != ("runtime", "login")
        assert lines[0]["hard_armed"] and 0 < lines[0]["hard_seconds"] <= .08
        assert dump.startswith("Timeout (")
        # The C deadline may win while the soft exception is cancelling it in
        # total_request's finally. That is still a bounded, fail-closed exit.
        assert_guarded_hard_watchdog_stack(dump)
    (tmp_path / "alarm-result.json").write_text(json.dumps({
        "plane": plane, "phase": phase, "native_stall": native_stall,
        "exit_code": result.returncode,
        "elapsed_since_stall": ended - lines[0]["at"], "events": lines,
    }, sort_keys=True))


@pytest.mark.parametrize("case", [
    "stalled", "unwind", "unrelated-top", "wrong-guard-file", "reordered",
    "split-threads", "unrelated-exit", "unarmed", "late-event", "late-observation",
    "soft-only-hard", "empty-dump", "prefixed-header",
])
def test_hard_watchdog_controller_requires_exact_causality(tmp_path, monkeypatch, case):
    frames = [("test_runtime_registry_login.py", "cancelled"),
              ("release_publication_deadline.py", "total_request"),
              ("contextlib.py", "__exit__"),
              ("release_google.py", "registry_login"),
              ("test_runtime_registry_login.py", "alarm_case_probe")]
    if case == "stalled":
        frames = [("test_runtime_registry_login.py", "stalled"), *frames[3:]]
    elif case == "unrelated-top":
        frames.insert(0, ("unrelated.py", "cancelled"))
    elif case == "wrong-guard-file":
        frames[1] = ("unrelated.py", "total_request")
    elif case == "reordered":
        frames[1], frames[2] = frames[2], frames[1]
    header = "Thread 0x123 (most recent call first):\n"
    lines = [f'  File "/synthetic/{file}", line 1 in {function}\n' for file, function in frames]
    if case == "split-threads":
        lines.insert(1, header)
    dump = "Timeout (0:00:00.080000)!\n" + ("prefix: " if case == "prefixed-header" else "") + header + "".join(lines)
    (tmp_path / "hard-watchdog.txt").write_text("" if case == "empty-dump" else dump)
    phase = "login" if case == "soft-only-hard" else "refresh"
    events = ["refresh", "stalled-login"] if phase == "login" else ["stalled-refresh"]
    output = [{"event": "started", "at": 100, "events": events,
               "hard_armed": case != "unarmed", "hard_seconds": .08}]
    if case == "late-event":
        output.append({"event": "late"})
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=2 if case == "unrelated-exit" else 1, stderr="",
        stdout="\n".join(json.dumps(item) for item in output) + "\n",
    ))
    monkeypatch.setattr(sys.modules[__name__], "time", SimpleNamespace(
        monotonic=lambda: 100.6 if case == "late-observation" else 100.1,
    ))
    if case in {"stalled", "unwind"}:
        test_shared_real_alarm_interrupts_stalled_refresh_or_login(tmp_path, "runtime", phase, False)
    else:
        with pytest.raises((AssertionError, pytest.fail.Exception)):
            test_shared_real_alarm_interrupts_stalled_refresh_or_login(tmp_path, "runtime", phase, False)


@pytest.mark.parametrize("expiry", [105, 160])
def test_runtime_refresh_consumes_original_shared_window(login, monkeypatch, expiry):
    client, events = login("runtime")
    clocks = [100.0, 50.0]
    client.packet["expires_at_unix"] = expiry
    monkeypatch.setattr(google.time, "time", lambda: clocks[0])
    monkeypatch.setattr(google.time, "monotonic", lambda: clocks[1])
    original = client.credentials.refresh

    def refresh(request):
        original(request)
        clocks[:] = [101, 52]

    monkeypatch.setattr(client.credentials, "refresh", refresh)
    client.registry_login()
    assert events[1] == ("docker", 3 if expiry == 105 else 28)


@pytest.mark.parametrize("phase", ["refresh", "login"])
@pytest.mark.parametrize("clock", ["wall", "monotonic"])
def test_runtime_deadline_is_rechecked_without_extension(login, monkeypatch, phase, clock):
    client, events = login("runtime")
    clocks = [100.0, 50.0]
    client.packet["expires_at_unix"] = 120
    monkeypatch.setattr(google.time, "time", lambda: clocks[0])
    monkeypatch.setattr(google.time, "monotonic", lambda: clocks[1])
    original = client.credentials.refresh if phase == "refresh" else google.subprocess.run

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        clocks[:] = [121, 51] if clock == "wall" else [90, 71]
        return result

    monkeypatch.setattr(client.credentials if phase == "refresh" else google.subprocess,
                        "refresh" if phase == "refresh" else "run", delayed)
    with pytest.raises((ValueError, TimeoutError)):
        client.registry_login()
    assert len(events) == (1 if phase == "refresh" else 2)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


@pytest.mark.parametrize("fault", ["missing-supervisor", "changed-packet", "expired-work-window"])
def test_publisher_still_requires_original_supervisor_and_packet(login, monkeypatch, fault):
    client, events = login("runtime-build")
    if fault == "missing-supervisor":
        monkeypatch.setattr(publication, "CURRENT", None)
    elif fault == "changed-packet":
        client.packet["expires_at_unix"] += 1
    else:
        monkeypatch.setattr(publication, "CURRENT", publication.Deadline(time.time() + 5))
    with pytest.raises(ValueError):
        client.registry_login()
    assert events == []


@pytest.mark.parametrize("plane", ["runtime", "runtime-build"])
def test_foreign_alarm_is_not_replaced(login, plane):
    client, events = login(plane)
    signal.setitimer(signal.ITIMER_REAL, 10)
    try:
        with pytest.raises(ValueError):
            client.registry_login()
        assert 9 < signal.getitimer(signal.ITIMER_REAL)[0] <= 10
        assert events == []
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


@pytest.mark.parametrize("plane", ["runtime", "runtime-build"])
@pytest.mark.parametrize("pending", [False, True])
def test_blocked_or_pending_alarm_cannot_disable_login_deadline(login, plane, pending):
    client, events = login(plane)
    original = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
    try:
        if pending:
            signal.raise_signal(signal.SIGALRM)
        with pytest.raises(ValueError):
            client.registry_login()
        assert events == []
        assert (signal.SIGALRM in signal.sigpending()) is pending
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if signal.SIGALRM in signal.sigpending():
            signal.sigwait({signal.SIGALRM})
        signal.pthread_sigmask(signal.SIG_SETMASK, original)


@pytest.mark.parametrize("phase", ["prepare", "activate"])
def test_actual_runtime_callers_reach_attestation_after_registry_login(login, monkeypatch, tmp_path, phase):
    client, events = login("runtime")
    packet = client.packet
    packet.update(source_sha="a" * 40, release_run_id=123, release_run_attempt=1)
    prepared = {"run_id": 123, "run_attempt": 1, "sha256": "b" * 64}
    plan = {"version": "runtime-" + phase + "/v1", "activation": {"prepared_receipt": prepared}}

    def initialize(path, plane):
        assert plane == "runtime"
        return client

    monkeypatch.setattr(runtime, "Google", initialize)
    monkeypatch.setattr(runtime, "read_bound_plan", lambda *args: plan)
    monkeypatch.setattr(runtime, "validate_plan", lambda value, authority: value)
    monkeypatch.setattr(runtime, "validate_activation_inputs", lambda *args: (None, None, None))
    image = runtime.REGISTRY + "/api@sha256:" + "c" * 64
    receipt = {"version": "runtime-prepared/v1", "source_sha": packet["source_sha"], "run_id": 123,
               "run_attempt": 1, "worker_executed": False, "images": {role: image.replace("/api@", "/" + role + "@")
                                                                           for role in ("api", "worker", "sam")}}
    monkeypatch.setattr(runtime, "checked", lambda *args: None)
    monkeypatch.setattr(runtime, "verified_receipt_bytes", lambda *args: json.dumps(receipt).encode())
    folder = tmp_path / ("runtime-image-api-" + packet["source_sha"] + "-1")
    folder.mkdir()
    (folder / "api.json").write_text(json.dumps({"version": "runtime-image/v1", "role": "api",
        "source_sha": packet["source_sha"], "run_id": 123, "run_attempt": 1, "reference": image}))

    class ReachedAttestation(Exception):
        pass

    def attest(*args):
        assert events[0] == "refresh" and events[1][0] == "docker"
        raise ReachedAttestation()

    monkeypatch.setattr(runtime, "verify_attestation", attest)
    with pytest.raises(ReachedAttestation):
        runtime.deploy(tmp_path / "packet.json", tmp_path, tmp_path / "out.json")
