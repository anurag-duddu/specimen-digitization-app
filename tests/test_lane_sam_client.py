"""The worker's side of SAM 3 per run (docs/execution/golive/LANE.md, T3a)."""

import base64
import hashlib
import io
import json
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.sam3_effect import (
    canonical_sha256,
    validate_sam3_run_response,
)
from specimen_digitization.application.sam3_server import (
    LocalObjects,
    RunSegmenter,
    create_app,
    lab_authenticator,
)
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.hub_models import SAM3_MODEL

from test_lane_sam_server import TOKEN, image_bytes, post, run_request, served
from test_sam3_server import FixtureEngine

__all__ = ["served"]  # The shared fixture, imported for pytest.


def test_a_served_response_passes_the_worker_binding(served):
    request = run_request(served.raw)
    body = post(served.client, request).json()
    assert validate_sam3_run_response(
        body,
        {
            "request": request,
            "pins": {"checkpoint_sha256": served.engine.checkpoint_sha256},
        },
    ) == "valid"


def test_a_lab_response_passes_the_worker_binding(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    raw = image_bytes()
    ref = blobs.put(raw)
    engine = FixtureEngine()
    engine.checkpoint_sha256 = canonical_sha256(engine.checkpoint_files)
    client = TestClient(
        create_app(
            RunSegmenter(LocalObjects(tmp_path / "blobs"), engine),
            lab_authenticator(TOKEN),
        )
    )
    request = run_request(raw, blob_ref=ref)
    body = post(client, request, bearer=TOKEN).json()
    pins = {"checkpoint_sha256": engine.checkpoint_sha256}
    assert validate_sam3_run_response(
        body, {"request": request, "pins": dict(pins, lab=True)}
    ) == "valid"
    assert validate_sam3_run_response(
        body, {"request": request, "pins": pins}
    ) == "mask_binding_mismatch"


def test_the_worker_rejects_responses_that_break_its_pins(served):
    request = run_request(served.raw)
    body = post(served.client, request).json()
    pins = {"checkpoint_sha256": served.engine.checkpoint_sha256}
    assert validate_sam3_run_response(
        body, {"request": request, "pins": {"checkpoint_sha256": "d" * 64}}
    ) == "checkpoint_binding_mismatch"
    other_run = run_request(served.raw, run_id="run-b")
    assert validate_sam3_run_response(
        body, {"request": other_run, "pins": pins}
    ) == "request_binding_mismatch"
    forged = json.loads(json.dumps(body))
    forged["regions"][0]["id"] = str(uuid5(NAMESPACE_URL, "sam3-run/run-b/0"))
    assert validate_sam3_run_response(
        forged, {"request": request, "pins": pins}
    ) == "invalid_region_provenance"


def lane_specimen():
    from specimen_digitization.application.collection_profiles import (
        SegmentationSettings,
    )
    from specimen_digitization.application.domain import Asset, Run, Scope, Specimen

    raw = image_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    run = Run(
        profile_rules={
            "segmentation_settings": SegmentationSettings(prompt="label").model_dump(
                mode="json"
            )
        },
        dependencies={
            "segmentation": {
                "endpoint": "https://sam.run.app",
                "revision": SAM3_MODEL.revision,
                "checkpoint_sha256": "e" * 64,
            }
        },
    )
    return Specimen(
        scope=Scope(
            organization_id="00000000-0000-4000-8000-00000000000b",
            collection_id="00000000-0000-4000-8000-00000000000c",
        ),
        run=run,
        asset=Asset(
            sensitive=False,
            sha256=sha,
            blob_ref=sha + ":7",
            media_type="image/png",
            size_bytes=len(raw),
            width=4,
            height=4,
            filename="slide.png",
            uploader="lane",
        ),
    )


def isolated(status, reason, value=None):
    return SimpleNamespace(
        status=status,
        reason=reason,
        value=value,
        cleanup_complete=True,
        elapsed_seconds=1.0,
    )


def envelope(status, body):
    raw = json.dumps(body).encode()
    return json.dumps(
        {
            "http_status": status,
            "validation": "http_error" if status != 200 else "valid",
            "body_base64": base64.b64encode(raw).decode(),
        }
    ).encode()


@pytest.mark.parametrize(
    ("result", "code", "status"),
    [
        (isolated("deadline_exceeded", "worker_deadline"), "sam3_timeout", LookupStatus.TIMEOUT),
        (isolated("worker_failed", "worker_call_failed"), "sam3_unavailable", LookupStatus.PROVIDER),
        (
            isolated("completed", "ok", envelope(429, {"detail": "sam3_busy"})),
            "sam3_busy",
            LookupStatus.RATE_LIMITED,
        ),
        (
            isolated("completed", "ok", envelope(409, {"detail": "sam3_busy"})),
            "sam3_busy",
            LookupStatus.RATE_LIMITED,
        ),
        (
            isolated("completed", "ok", envelope(503, {"detail": "down"})),
            "sam3_unavailable",
            LookupStatus.PROVIDER,
        ),
    ],
)
def test_per_run_failures_are_retryable(monkeypatch, tmp_path, result, code, status):
    from specimen_digitization.application import production
    import specimen_digitization.application.bounded_effect as bounded

    monkeypatch.setattr(bounded, "run_isolated", lambda *args, **kwargs: result)
    service = production.Sam3Service(
        "https://sam.run.app", LocalBlobs(tmp_path), effect=lambda payload: b""
    )
    with pytest.raises(AdapterFailure) as failure:
        service.segment_per_run(lane_specimen())
    assert (failure.value.code, failure.value.status) == (code, status)
    assert failure.value.outcome_unknown is False


def test_a_refused_request_blocks_without_retry(monkeypatch, tmp_path):
    from specimen_digitization.application import production
    from specimen_digitization.application.workflow import OperationalBlock
    import specimen_digitization.application.bounded_effect as bounded

    monkeypatch.setattr(
        bounded,
        "run_isolated",
        lambda *args, **kwargs: isolated(
            "completed", "ok", envelope(409, {"detail": "sam3_run_request_mismatch"})
        ),
    )
    service = production.Sam3Service(
        "https://sam.run.app", LocalBlobs(tmp_path), effect=lambda payload: b""
    )
    with pytest.raises(OperationalBlock, match="sam3_http_409"):
        service.segment_per_run(lane_specimen())


@pytest.mark.parametrize(
    ("endpoint", "lab_token", "allowed"),
    [
        ("https://sam.run.app", None, True),
        ("http://127.0.0.1:18080", TOKEN, True),
        ("http://127.0.0.1:18080", None, False),
        ("http://localhost:18080", TOKEN, False),
        ("http://127.0.0.1:18080/path", TOKEN, False),
        ("https://example.com", None, False),
    ],
)
def test_lab_endpoints_need_the_lab_switch(tmp_path, endpoint, lab_token, allowed):
    from specimen_digitization.application.production import Sam3Service

    if allowed:
        Sam3Service(endpoint, LocalBlobs(tmp_path), lab_token=lab_token)
    else:
        with pytest.raises(ValueError):
            Sam3Service(endpoint, LocalBlobs(tmp_path), lab_token=lab_token)


def test_the_run_pins_the_checkpoint_the_worker_expects(monkeypatch, tmp_path):
    from specimen_digitization.application.domain import Run
    from specimen_digitization.application.production import ProductionAdapters

    monkeypatch.setenv("SPECIMEN_SAM3_ENDPOINT", "https://sam.run.app")
    monkeypatch.setenv("SPECIMEN_SAM3_REVISION", SAM3_MODEL.revision)
    monkeypatch.setenv("SPECIMEN_SAM3_CHECKPOINT_SHA256", "e" * 64)
    pins = ProductionAdapters(LocalBlobs(tmp_path)).pin_dependencies(Run())
    assert pins["segmentation"] == {
        "endpoint": "https://sam.run.app",
        "revision": SAM3_MODEL.revision,
        "checkpoint_sha256": "e" * 64,
    }


def test_the_pilot_allowance_gives_segmentation_time_and_keeps_readers_short():
    from specimen_digitization.application.collection_profiles import (
        published_registry,
    )

    allowance = published_registry().resolve("insects").profile.processing
    assert (
        allowance.external_timeout_seconds,
        allowance.reader_timeout_seconds,
        allowance.lease_seconds,
    ) == (270, 120, 300)


def test_the_allowance_timeouts_must_fit_their_lease():
    from specimen_digitization.application.collection_profiles import ProcessingPolicy
    from specimen_digitization.application.domain import StageCostReservations

    costs = StageCostReservations(
        version="stage-cost-reservations-v1", cost_micros={"segment": 1}
    )
    with pytest.raises(ValueError):
        ProcessingPolicy(
            run_cost_limit_micros=1,
            stage_cost_micros=costs,
            external_timeout_seconds=270,
            lease_seconds=299,
        )
    with pytest.raises(ValueError):
        ProcessingPolicy(
            run_cost_limit_micros=1,
            stage_cost_micros=costs,
            external_timeout_seconds=100,
            reader_timeout_seconds=120,
            lease_seconds=300,
        )


def test_a_queued_run_carries_the_segment_timeout(tmp_path):
    from specimen_digitization.application.collection_profiles import (
        published_registry,
    )
    from specimen_digitization.application.lane import queue

    specimen = lane_specimen()
    queue(specimen, published_registry({specimen.scope.collection_id: "insects"}), "lab")
    execution = specimen.run.profile.execution
    assert execution.effect_timeout_for_step("segment") == 270
    assert execution.effect_timeout_for_step("transcribe:region:handwriting-qwen") == 120
    assert execution.lease_seconds == 300
