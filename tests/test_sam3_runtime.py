"""The real isolated SAM adapter includes auth, transport and decode in one deadline."""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_worker_recovery import setup
from specimen_digitization.application.production import Sam3Service
from specimen_digitization.application.workflow import Workflow, SyntheticAdapters
from specimen_digitization.application.storage import digest
from test_sam3_response_binding import expected_binding, legitimate_body


def local_sam_effect(payload):
    # Importable child-only test auth/transport fixture. Production never reads these variables.
    time.sleep(float(os.getenv("SPECIMEN_TEST_SAM_AUTH_DELAY", "0")))
    from specimen_digitization.application.sam3_effect import sam3_exchange

    payload["endpoint"] = os.environ["SPECIMEN_TEST_SAM_ORIGIN"]
    return sam3_exchange(payload, "synthetic")


@pytest.mark.parametrize("scenario", ["success", "slow_auth", "drip", "forged"])
def test_sam_total_deadline_durable_unknown_and_no_retry(
    tmp_path, monkeypatch, scenario
):
    state = {"requests": 0, "transcriptions": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["requests"] += 1
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if scenario == "drip":
                self.send_response(200)
                self.send_header("Content-Length", "100000")
                self.end_headers()
                try:
                    for _ in range(200):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            body = legitimate_body(request, expected_binding(request))
            if scenario == "forged":
                body["request_sha256"] = "0" * 64
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "SPECIMEN_TEST_SAM_ORIGIN", f"http://127.0.0.1:{server.server_port}"
    )
    monkeypatch.setenv(
        "SPECIMEN_TEST_SAM_AUTH_DELAY", "10" if scenario == "slow_auth" else "0"
    )
    repo, blobs, principal, items = setup(tmp_path)
    specimen = items[0]
    initial = Workflow(repo, blobs, SyntheticAdapters(blobs, "synthetic"))
    for _ in range(4):
        if "classify" in specimen.run.completed_steps:
            break
        specimen = initial.step(principal, specimen.id)
    assert "classify" in specimen.run.completed_steps
    specimen.run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    specimen.run.profile.execution.external_timeout_seconds = 3
    specimen = repo.save(
        principal, specimen, specimen.version, "sam-ready", digest("ready")
    )

    class Adapter(SyntheticAdapters):
        def transcribe(self, specimen, region, route):
            state["transcriptions"] += 1
            return super().transcribe(specimen, region, route)

        def segment(self, item):
            return Sam3Service(
                "https://synthetic.run.app",
                blobs,
                effect=local_sam_effect,
                expected=expected_binding({"sha256": item.asset.sha256}),
            ).segment(item)

    workflow = Workflow(repo, blobs, Adapter(blobs, "synthetic"))
    try:
        started = time.monotonic()
        result = workflow.step(principal, specimen.id)
        assert time.monotonic() - started < 6
        if scenario == "success":
            assert "segment" in result.run.completed_steps, result.run.blocker
            assert result.run.segmentation["validation"] == "valid"
            assert state["requests"] == 1
        elif scenario == "forged":
            assert result.run.blocker == "sam3_request_binding_mismatch"
            assert "segment" not in result.run.completed_steps
            assert not result.run.regions
            assert not result.run.observations
            retained = json.loads(blobs.get(result.run.segmentation["blob_ref"]))
            assert retained["request_sha256"] == "0" * 64
            restarted = Workflow(repo, blobs, Adapter(blobs, "synthetic"))
            after_restart = restarted.step(principal, specimen.id)
            assert after_restart.run.stage == "processing_blocked"
            assert state["transcriptions"] == 0
            assert result.run.segmentation["validation"] == "request_binding_mismatch"
            assert state["requests"] == 1
        else:
            assert result.run.blocker == "external_outcome_unknown"
            assert result.run.lease_until and result.run.disposition is None
            calls = state["requests"]
            restarted = Workflow(repo, blobs, Adapter(blobs, "synthetic"))
            restarted.step(principal, specimen.id)
            assert state["requests"] == calls
            assert calls == (0 if scenario == "slow_auth" else 1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
