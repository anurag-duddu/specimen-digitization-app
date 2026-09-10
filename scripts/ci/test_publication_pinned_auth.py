"""Opt-in exact upstream-bundle probes; all transports are synthetic loopback."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import pytest

import release_publication_deadline as M
from test_release_google import context


@pytest.fixture
def upstream():
    root = os.environ.get("SPECIMEN_TEST_AUTH_SOURCE")
    if not root:
        pytest.skip("provide the exact pinned public upstream source snapshot for offline bundle probes")
    source = Path(root)
    for part, digest in M.BUNDLE_HASHES.items():
        assert hashlib.sha256((source / f"dist/{part}/index.js").read_bytes()).hexdigest() == digest
    return source


@contextmanager
def server(mode):
    events = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def serve(self):
            target = self.headers.get("x-synthetic-target", "")
            stage = "oidc" if target == "synthetic.actions.githubusercontent.com" else "sts"
            events.append({"stage": stage, "at": time.time(), "method": self.command})
            if self.command == "POST":
                self.rfile.read(int(self.headers.get("content-length", "0")))
            if mode == "stall_" + stage:
                time.sleep(5)
            status = 500 if mode == "retry_" + stage else 200
            payload = {"value": "synthetic-oidc-value"} if stage == "oidc" else {"access_token": "synthetic-sts-value"}
            raw = json.dumps(payload).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass
        do_GET = do_POST = serve
    listener = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    listener.daemon_threads = True
    thread = threading.Thread(target=lambda: listener.serve_forever(poll_interval=.02), daemon=True)
    thread.start()
    try:
        yield listener.server_port, events
    finally:
        listener.shutdown()
        listener.server_close()
        thread.join(timeout=1)


def inputs(tmp_path, port):
    env, packet = context()
    env.update(PATH=os.environ["PATH"], RUNNER_TEMP=str(tmp_path), GITHUB_WORKSPACE=str(tmp_path),
               ACTIONS_ID_TOKEN_REQUEST_URL="https://synthetic.actions.githubusercontent.com/token?api-version=2.0",
               SYNTHETIC_AUTH_PORT=str(port), RELEASE_SERVICE_ACCOUNT="specimen-runtime-build@specimen-digitization.iam.gserviceaccount.com")
    packet["identity"]["provider"] = packet["identity"]["provider"].replace("specimen-data-release", "specimen-runtime-build")
    (tmp_path / "auth").mkdir(mode=0o700)
    for name in ("auth-output", "auth-env", "auth-path"):
        M.private_write(tmp_path / name, "")
    return M.auth_environment(env, packet, tmp_path), packet


def command(upstream):
    return [shutil.which("node"), "--require", str(Path(__file__).parent / "fixtures/publication_auth_transport.cjs"),
            str(upstream / "dist/main/index.js")]


def test_actual_pinned_default_mode_exchanges_oidc_and_sts_without_optional_iam(upstream, tmp_path):
    with server("success") as (port, events):
        env, packet = inputs(tmp_path, port)
        guard = M.Supervisor(M.Deadline(time.time() + 30))
        guard.run_owned(command(upstream), env=env, cwd=tmp_path, stage="auth", limit=10)
        assert [event["stage"] for event in events] == ["oidc", "sts"]  # Observed in this first-success fixture only.
        values = M.auth_outputs(tmp_path / "auth-output")
        assert set(values) == {"credentials_file_path", "project_id"}
        credential = Path(values["credentials_file_path"])
        from release_google import github_credential_bytes, validate_credentials
        validate_credentials(M.strict_json(github_credential_bytes(credential)), packet, env)
        post = {**env, "GOOGLE_GHA_CREDS_PATH": str(credential)}
        before = len(events)
        guard.run_owned([shutil.which("node"), str(upstream / "dist/post/index.js")],
                        env=post, cwd=tmp_path, stage="post", limit=5)
        assert not credential.exists() and len(events) == before


@pytest.mark.parametrize("mode", ["stall_oidc", "stall_sts", "retry_oidc", "retry_sts"])
def test_upstream_stall_or_retry_cannot_escape_original_cutoff(upstream, tmp_path, mode):
    with server(mode) as (port, events):
        env, _ = inputs(tmp_path, port)
        end = time.time() + M.STOP_RESERVE + .5
        guard = M.Supervisor(M.Deadline(end))
        with pytest.raises(M.PublicationStopped):
            guard.run_owned(command(upstream), env=env, cwd=tmp_path, stage="auth", limit=120)
        assert events
        assert len([event for event in guard.events if event["event"] == "started"]) == 1
        assert not M.process_group_alive(guard.last_group)
        count = len(events)
        time.sleep(.15)
        assert len(events) == count
        assert all(event["at"] < end for event in events)
        assert all(event["stage"] == "auth" for event in guard.events)
