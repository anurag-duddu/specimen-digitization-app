"""Actual registry-login method and callers with synthetic credentials/transport."""
import json
from pathlib import Path
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


@pytest.mark.parametrize("plane", ["runtime", "runtime-build"])
@pytest.mark.parametrize("phase", ["refresh", "login"])
def test_shared_real_alarm_interrupts_stalled_refresh_or_login(login, monkeypatch, plane, phase):
    client, events = login(plane)
    owner, name = ((google, "request_deadline") if plane == "runtime" and phase == "login"
                   else (publication, "total_request"))
    guard = getattr(owner, name)
    monkeypatch.setattr(owner, name, lambda seconds: guard(min(seconds, .08)))

    def stalled(*args, **kwargs):
        events.append("stalled-" + phase)
        time.sleep(1)
        pytest.fail("deadline did not stop synthetic stall")

    monkeypatch.setattr(client.credentials if phase == "refresh" else google.subprocess,
                        "refresh" if phase == "refresh" else "run", stalled)
    began = time.monotonic()
    expected = ValueError if plane == "runtime" and phase == "refresh" else (TimeoutError, publication.RequestExpired)
    with pytest.raises(expected):
        client.registry_login()
    assert time.monotonic() - began < .5
    assert events == (["stalled-refresh"] if phase == "refresh" else ["refresh", "stalled-login"])
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


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
