"""Real process lifecycle with injected model/cloud boundaries; no model calls."""

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest


STANDING_SAM_TRACE_CONFIGURATION = r'''
def configure_fixture_sam_trace(root):
    """Reach the real standing G3 configuration with a strictly local SDK sink."""
    import json
    import os
    from pathlib import Path
    import logfire
    from logfire.testing import TestExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from specimen_digitization import observability

    # A fresh child must not inherit the retired bounded-export configuration.
    for key in list(os.environ):
        if key.startswith(("SPECIMEN_TRACE_", "OTEL_")) or key in {
            "LOGFIRE_BASE_URL", "LOGFIRE_ENVIRONMENT", "LOGFIRE_SERVICE_VERSION"
        }:
            os.environ.pop(key, None)
    package = Path(root) / "built-package"
    package.mkdir()
    source_sha = "a" * 40  # Synthetic embedded provenance, not a deployed build.
    (package / "_build.json").write_text(json.dumps({"source_sha": source_sha}))
    observability.__file__ = str(package / "observability.py")
    os.environ.update({
        "APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "approved-content",
        "LOGFIRE_SEND_TO_LOGFIRE": "true", "LOGFIRE_SERVICE_NAME": "specimen-sam",
        "LOGFIRE_HEAD_SAMPLE_RATE": "1.0", "LOGFIRE_DISTRIBUTED_TRACING": "true",
        "LOGFIRE_TOKEN": "SYNTHETIC-SAM-LIFECYCLE-WRITER-CANARY",
        "OTEL_TRACES_EXPORTER": "none", "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
    })
    configure = logfire.configure
    exporter = TestExporter()

    def configure_local_sink(**options):
        assert options["send_to_logfire"] is True
        assert options["environment"] == "production"
        assert options["service_name"] == "specimen-sam"
        assert options["service_version"] == source_sha
        assert options["resource_attributes"] == {
            "specimen.telemetry.capture_mode": "approved-content"
        }
        assert options["distributed_tracing"] is True
        assert options["advanced"].base_url == "https://logfire-us.pydantic.dev"
        assert options["advanced"].exception_callback is observability._private_exception_callback
        assert options["inspect_arguments"] is False
        assert options["variables"].instrument is False
        assert options["add_baggage_to_attributes"] is False
        assert options["console"] is False and options["metrics"] is False
        # Adapt only the transport. Actual configuration/SDK validation and
        # runtime.main's expiry, inference and shutdown controls still execute.
        offline = dict(options)
        offline.update(send_to_logfire=False, token=None,
            additional_span_processors=[SimpleSpanProcessor(exporter)])
        return configure(**offline)

    logfire.configure = configure_local_sink
'''


@pytest.mark.parametrize("startup_failure", [False, True])
def test_sam_expiry_watchdog_does_not_keep_failed_or_stopped_process_alive(
    tmp_path, startup_failure
):
    marker = tmp_path / "boundary-reached"
    script = STANDING_SAM_TRACE_CONFIGURATION + r'''
import os, sys, time
from pathlib import Path
from types import SimpleNamespace
from specimen_digitization.application import sam3_server as runtime
from google.cloud import storage
import uvicorn

marker, failure = sys.argv[1:]
sys.argv = ["sam3"]
os.environ.update(
    SPECIMEN_SAM3_ENABLE="authorized-pilot", K_SERVICE="fixture-only",
    SPECIMEN_SAM3_BUDGET_AUTHORIZATION="fixture-only",
    SPECIMEN_PILOT_MANIFEST_SHA256="a" * 64,
    SPECIMEN_SAM3_EXPIRES_UNIX=str(time.time() + 300),
    SPECIMEN_SAM3_AUDIENCE="https://fixture.invalid",
    SPECIMEN_SAM3_CALLER_EMAIL="fixture@example.invalid",
    SPECIMEN_SAM3_OUTPUT_BUCKET="fixture-only",
    SPECIMEN_SAM3_CHECKPOINT_SHA256="a" * 64,
)
configure_fixture_sam_trace(Path(marker).parent)
from huggingface_hub import constants
constants.HF_HUB_OFFLINE = True
for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
    os.environ.pop(key, None)
runtime.read_runtime_manifest = lambda **kwargs: SimpleNamespace()
storage.Client = lambda **kwargs: SimpleNamespace()
def engine():
    if failure == "True":
        Path(marker).touch()
        raise RuntimeError("fixture-startup-failure")
    return SimpleNamespace()
runtime.Sam3Engine = engine
def stopped(*args, **kwargs):
    Path(marker).touch()
uvicorn.run = stopped
runtime.main()
'''
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(marker), str(startup_failure)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    try:
        try:
            _, error = process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            assert marker.exists(), "Injected startup/server boundary was not reached"
            pytest.fail("SAM process remained alive after startup failure/server return")
        assert marker.exists(), error.decode()
        assert (process.returncode != 0) is startup_failure
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_production_sam_stops_stuck_inference_before_platform_deadline(tmp_path):
    marker = tmp_path / "inference-entered"
    script = STANDING_SAM_TRACE_CONFIGURATION + r'''
import os, sys, time
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI
from google.cloud import storage
from specimen_digitization.application import sam3_server as runtime

port, marker = sys.argv[1:]
sys.argv = ["sam3"]
os.environ.update(
    SPECIMEN_SAM3_ENABLE="authorized-pilot", K_SERVICE="fixture-only",
    SPECIMEN_SAM3_BUDGET_AUTHORIZATION="fixture-only",
    SPECIMEN_PILOT_MANIFEST_SHA256="a" * 64,
    SPECIMEN_SAM3_EXPIRES_UNIX=str(time.time() + 300),
    SPECIMEN_SAM3_AUDIENCE="https://fixture.invalid",
    SPECIMEN_SAM3_CALLER_EMAIL="fixture@example.invalid",
    SPECIMEN_SAM3_OUTPUT_BUCKET="fixture-only", PORT=port,
    SPECIMEN_SAM3_CHECKPOINT_SHA256="a" * 64,
)
configure_fixture_sam_trace(Path(marker).parent)
from huggingface_hub import constants
constants.HF_HUB_OFFLINE = True
for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
    os.environ.pop(key, None)
runtime.read_runtime_manifest = lambda **kwargs: SimpleNamespace()
storage.Client = lambda **kwargs: SimpleNamespace()
runtime.Sam3Engine = lambda: SimpleNamespace()
app = FastAPI()
@app.get("/live")
async def live():
    return {}
@app.get("/stuck")
def stuck():
    Path(marker).touch()
    time.sleep(120)
    return {}
runtime.create_app = lambda *args, **kwargs: app
runtime.main()
'''
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(port), str(marker)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    connection = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None
            try:
                if (
                    httpx.get(f"http://127.0.0.1:{port}/live", timeout=0.5).status_code
                    == 200
                ):
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        else:
            pytest.fail("SAM startup deadline exceeded")
        connection = socket.create_connection(("127.0.0.1", port))
        connection.sendall(b"GET /stuck HTTP/1.1\r\nHost: localhost\r\n\r\n")
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists()
        started = time.monotonic()
        process.terminate()
        try:
            process.wait(timeout=11)
        except subprocess.TimeoutExpired:
            pytest.fail("SAM inference thread survived the hard shutdown deadline")
        assert time.monotonic() - started < 10
    finally:
        if connection is not None:
            connection.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
