"""Bounded offline native-code refresh and sanitized locked-SDK failures."""
import json
import os
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
from test_runtime_registry_login import login


def test_native_refresh_is_hard_stopped_before_docker():
    # The hard watchdog intentionally exits its process. Never run the native
    # stall inside pytest itself, or give this child any credential/transport.
    script = f'''
import hashlib, json, signal, socket, subprocess, sys, time
from types import SimpleNamespace
sys.path.insert(0, {str(Path(__file__).parent)!r})
import release_google as G
import release_publication_deadline as P
from google.auth.transport import requests
def forbidden(*args, **kwargs):
    raise AssertionError("real network or child forbidden")
socket.socket = socket.create_connection = forbidden
subprocess.Popen = forbidden
requests.Request = lambda: "synthetic-request"
soft, hard = G.request_deadline, P.total_request
G.request_deadline = lambda seconds: soft(min(seconds, .05))
P.total_request = lambda seconds: hard(min(seconds, .05))
def refresh(request):
    print(json.dumps({{"refresh_started": time.monotonic()}}), flush=True)
    hashlib.pbkdf2_hmac("sha256", b"synthetic", b"fixture", 10_000_000)
def docker(*args, **kwargs):
    print("UNEXPECTED_DOCKER", flush=True)
    raise AssertionError("Docker cannot follow the stalled refresh")
G.subprocess.run = docker
client = G.Google.__new__(G.Google)
client.plane = "runtime"
client.packet = {{"expires_at_unix": int(time.time()) + 120}}
client.credentials = SimpleNamespace(refresh=refresh, token="synthetic-unused")
try:
    client.registry_login()
except BaseException as exc:
    print(json.dumps({{"caught": type(exc).__name__}}), flush=True)
    sys.exit(23)
sys.exit(24)
'''
    result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True,
                            text=True, timeout=3, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    ended = time.monotonic()
    lines = result.stdout.splitlines()
    assert lines and json.loads(lines[0]).keys() == {"refresh_started"}
    elapsed = ended - json.loads(lines[0])["refresh_started"]
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr, elapsed)
    assert len(lines) == 1 and result.stderr == ""
    assert elapsed < .25, elapsed


def test_runtime_hard_watchdog_is_disarmed_before_docker(login, monkeypatch):
    client, events = login("runtime")
    active = [False]
    lifecycle = []
    arm = publication.faulthandler.dump_traceback_later
    cancel = publication.faulthandler.cancel_dump_traceback_later

    def armed(*args, **kwargs):
        assert kwargs["exit"] is True
        arm(*args, **kwargs)
        active[0] = True
        lifecycle.append("armed")

    def cancelled():
        cancel()
        active[0] = False
        lifecycle.append("cancelled")

    monkeypatch.setattr(publication.faulthandler, "dump_traceback_later", armed)
    monkeypatch.setattr(publication.faulthandler, "cancel_dump_traceback_later", cancelled)
    refresh = client.credentials.refresh
    docker = google.subprocess.run

    def refreshing(request):
        assert active[0], "native refresh needs the C hard watchdog"
        refresh(request)

    def logging_in(*args, **kwargs):
        assert not active[0], "no process hard exit may orphan a Docker child"
        return docker(*args, **kwargs)

    monkeypatch.setattr(client.credentials, "refresh", refreshing)
    monkeypatch.setattr(google.subprocess, "run", logging_in)
    client.registry_login()
    assert lifecycle == ["armed", "cancelled"]
    assert events[0] == "refresh" and events[1][0] == "docker"


@pytest.mark.parametrize("stage", ["oidc", "sts", "iam"])
@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_locked_sdk_failures_are_sanitized_without_retry(monkeypatch, stage, status):
    from google.auth import identity_pool
    from google.auth.transport import requests

    def forbidden(*args, **kwargs):
        pytest.fail("real network or child forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    calls = []
    fake_url = "https://synthetic.actions.githubusercontent.com/oidc"
    credential = identity_pool.Credentials.from_info({
        "type": "external_account",
        "audience": "//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/fake/providers/fake",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "token_url": "https://sts.googleapis.com/v1/token",
        "service_account_impersonation_url": "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/fake@example.invalid:generateAccessToken",
        "credential_source": {"url": fake_url, "headers": {"Authorization": "Bearer SYNTHETIC"},
                              "format": {"type": "json", "subject_token_field_name": "value"}},
    }, scopes=["https://www.googleapis.com/auth/cloud-platform"])

    def wire(url, method="GET", **kwargs):
        phase = "oidc" if url == fake_url else "sts" if url == "https://sts.googleapis.com/v1/token" else "iam"
        calls.append(phase)
        body = ({"error": "SYNTHETIC_PRIVATE_RESPONSE_CANARY"} if phase == stage else
                {"value": "synthetic-oidc"} if phase == "oidc" else
                {"access_token": "synthetic-sts", "expires_in": 3600, "token_type": "Bearer"})
        return SimpleNamespace(status=status if phase == stage else 200, data=json.dumps(body).encode(), headers={})

    monkeypatch.setattr(requests, "Request", lambda: wire)
    monkeypatch.setattr(google.subprocess, "run", forbidden)
    client = google.Google.__new__(google.Google)
    client.plane = "runtime"
    client.packet = {"expires_at_unix": int(time.time()) + 120}
    client.credentials = credential
    with pytest.raises(ValueError, match="^runtime registry credential refresh failed$") as stopped:
        client.registry_login()
    assert stopped.value.__suppress_context__ is True
    assert calls == ["oidc", "sts", "iam"][:["oidc", "sts", "iam"].index(stage) + 1]
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_runtime_main_does_not_expose_sdk_response_body(login, monkeypatch, capsys):
    from google.auth.exceptions import RefreshError

    client, events = login("runtime")

    def failed(request):
        events.append("refresh")
        raise RefreshError("Unable to acquire impersonated credentials", "SYNTHETIC_PRIVATE_RESPONSE_CANARY")

    monkeypatch.setattr(client.credentials, "refresh", failed)
    monkeypatch.setattr(runtime, "admit", lambda *args: client.packet)
    monkeypatch.setattr(runtime, "deploy", lambda *args: client.registry_login())
    monkeypatch.setattr(sys, "argv", ["deploy_runtime.py", "--plane", "runtime", "--deploy",
                                    "--packet", "synthetic-packet.json", "--receipts", "synthetic-receipts",
                                    "--output", "synthetic-output.json"])
    with pytest.raises(SystemExit) as stopped:
        runtime.main()
    captured = capsys.readouterr()
    assert str(stopped.value) == "Runtime release blocked (ValueError); inspect the named admission gate privately."
    assert "SYNTHETIC_PRIVATE_RESPONSE_CANARY" not in captured.out + captured.err + str(stopped.value)
    assert stopped.value.__suppress_context__ is True
    assert events == ["refresh"]
