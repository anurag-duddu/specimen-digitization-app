"""Opt-in local Linux Docker cancellation; never an application/cloud image."""
import io
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import uuid

import pytest

import release_publication_deadline as M


@pytest.mark.skipif(sys.platform != "linux" or os.environ.get("SPECIMEN_TEST_DOCKER") != "1",
                    reason="explicit local Linux daemon/loopback qualification only")
def test_actual_push_cancellation_stops_owned_operation_and_keeps_daemon_running(tmp_path):
    port = int(os.environ["SYNTHETIC_REGISTRY_PORT"])
    assert 1024 <= port <= 65535
    docker = shutil.which("docker")
    assert docker
    env = {**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock", "DOCKER_CONFIG": str(tmp_path / "docker")}
    Path(env["DOCKER_CONFIG"]).mkdir(mode=0o700)
    (Path(env["DOCKER_CONFIG"]) / "config.json").write_text("{}")
    target = f"localhost:{port}/cutoff-synthetic/image:{uuid.uuid4().hex}"
    uploaded, disconnected = threading.Event(), threading.Event()
    stopping = threading.Event()
    observations = []
    evidence = {"fixture": "isolated Linux Docker daemon and synthetic loopback registry",
                "production_behavior": "not_tested", "outcome": "not_completed",
                "accepted_request_outcome": "unknown_not_rollback"}
    def observe(event):
        observations.append({"event": event, "at": time.time()})
    class Registry(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *args):
            pass
        def reply(self, status, **headers):
            self.send_response(status)
            self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
            self.send_header("Content-Length", "0")
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
        def do_GET(self):
            observe("GET")
            self.reply(200 if self.path.rstrip("/") == "/v2" else 404)
        def do_HEAD(self):
            observe("HEAD")
            self.reply(404)
        def do_POST(self):
            observe("POST")
            assert "/blobs/uploads/" in self.path
            self.reply(202, Location=f"http://localhost:{port}/v2/cutoff-synthetic/image/blobs/uploads/synthetic",
                       **{"Docker-Upload-UUID": "synthetic", "Range": "0-0"})
        def hold(self):
            observe(self.command)
            uploaded.set()
            self.connection.settimeout(.1)
            try:
                while not stopping.is_set():
                    try:
                        body = self.connection.recv(65536)
                    except socket.timeout:
                        continue
                    if not body:
                        observe("client_disconnected")
                        disconnected.set()
                        break
            except ConnectionResetError:
                disconnected.set()
            self.close_connection = True
        do_PATCH = do_PUT = hold
    server = ThreadingHTTPServer(("0.0.0.0", port), Registry)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
    thread.start()
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w") as archive:
        data = b"public-synthetic-publication-cancellation\n" * 32768
        info = tarfile.TarInfo("synthetic.txt")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    created = False
    supervisor = None
    try:
        before = subprocess.check_output([docker, "info", "--format", "{{.ID}}"], env=env, timeout=10)
        subprocess.run([docker, "import", "-", target], input=tar.getvalue(), env=env,
                       check=True, capture_output=True, timeout=30)
        created = True
        end = time.time() + M.STOP_RESERVE + 3
        evidence.update(original_deadline_unix=end, work_cutoff_unix=end - M.STOP_RESERVE)
        supervisor = M.Supervisor(M.Deadline(end))
        diagnostic = tmp_path / "synthetic-push.log"
        command = [sys.executable, "-c", "import subprocess,sys; "
            + f"f=open({str(diagnostic)!r},'w'); "
            + f"sys.exit(subprocess.run({[docker, 'push', target]!r},stdout=f,stderr=f).returncode)"]
        with pytest.raises(M.PublicationStopped):
            supervisor.run_owned(command, env=env, cwd=tmp_path, stage="push", limit=600)
        assert uploaded.is_set(), "fixture did not reach upload: " + diagnostic.read_text()
        # An already accepted remote request need not close or roll back. Observe
        # cancellation independently in this otherwise-empty fixture daemon.
        daemon_log = Path(os.environ["SYNTHETIC_DAEMON_LOG"])
        wait_end = time.monotonic() + 3
        while "Not continuing with push after error" not in daemon_log.read_text() and time.monotonic() < wait_end:
            time.sleep(.02)
        cancellation = [line for line in daemon_log.read_text().splitlines()
                        if "Not continuing with push after error" in line]
        assert len(cancellation) == 1 and 'context canceled' in cancellation[0]
        cancellation_time = datetime.fromisoformat(re.search(r'time="([^"]+)"', cancellation[0])[1]).timestamp()
        evidence.update(daemon_cancellation_line=cancellation[0], daemon_cancellation_unix=cancellation_time,
                        cancellation_observed_unix=time.time())
        count = len(observations)
        time.sleep(.2)
        evidence["observation_end_unix"] = time.time()
        assert len(observations) == count, "no new registry operation may follow cancellation"
        assert not M.process_group_alive(supervisor.last_group)
        evidence["owned_group_terminated"] = True
        assert subprocess.check_output([docker, "info", "--format", "{{.ID}}"], env=env, timeout=10) == before
        evidence["daemon_identity_unchanged"] = True
        requests = [event for event in observations if event["event"] != "client_disconnected"]
        assert requests and all(event["at"] <= cancellation_time for event in requests)
        assert all(event["at"] < end - M.STOP_RESERVE for event in requests)
        assert not any(event["event"] == "completed" for event in supervisor.events)
        evidence["outcome"] = "local_cancellation_observed"
    finally:
        evidence.update(registry_trace=list(observations),
                        supervisor_events=[] if supervisor is None else supervisor.events)
        evidence_path = os.environ.get("SYNTHETIC_DOCKER_EVIDENCE")
        if evidence_path:
            Path(evidence_path).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
        stopping.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
        if created:
            subprocess.run([docker, "image", "rm", "--force", target], env=env, check=True,
                           capture_output=True, timeout=20)
