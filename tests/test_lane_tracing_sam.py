"""SAM 3 in the run's trace (docs/execution/golive/LANE.md, T5c)."""

import json

import httpx
import pytest
from logfire.propagate import (
    NoExtractTraceContextPropagator,
    WarnOnExtractTraceContextPropagator,
)
from logfire.testing import CaptureLogfire
from opentelemetry import propagate

import specimen_digitization.application.bounded_effect as bounded
from specimen_digitization import observability
from specimen_digitization.application import production, sam3_effect, sam3_server
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.hub_models import SAM3_MODEL

from test_lane_sam_client import envelope, isolated, lane_specimen
from test_lane_sam_server import TOKEN, run_request, served

__all__ = ["served"]  # The shared fixture, imported for pytest.

SEGMENT = "Segment specimen with SAM 3"
SERVE = "Serve SAM 3 segmentation"
TRACE = "a" * 32
PARENT = "b" * 16
TRACEPARENT = f"00-{TRACE}-{PARENT}-01"


def named(capfire, name):
    return [s for s in capfire.exporter.exported_spans_as_dict() if s["name"] == name]


def parameters(attributes):
    return (
        json.loads(attributes["sam3.concepts"]),
        attributes["sam3.label_threshold"],
        attributes["sam3.mask_threshold"],
        attributes["sam3.record_floor"],
        attributes["sam3.max_detections"],
        attributes["sam3.model_revision"],
    )


APPLIED = (["label"], 0.5, 0.5, 0.5, 64, SAM3_MODEL.revision)


def test_the_worker_span_records_the_parameters_and_hands_on_its_traceparent(
    monkeypatch, tmp_path, capfire: CaptureLogfire
):
    payloads = []

    def run_isolated(effect, payload, *args, **kwargs):
        payloads.append(payload)
        return isolated("completed", "ok", envelope(503, {"detail": "down"}))

    monkeypatch.setattr(bounded, "run_isolated", run_isolated)
    service = production.Sam3Service(
        "https://sam.run.app", LocalBlobs(tmp_path), effect=lambda payload: b""
    )
    specimen = lane_specimen()
    with pytest.raises(AdapterFailure):
        service.segment_per_run(specimen)
    [span] = named(capfire, SEGMENT)
    attributes = span["attributes"]
    assert attributes["specimen.id"] == specimen.id
    assert attributes["specimen.run.id"] == specimen.run.id
    assert parameters(attributes) == APPLIED
    assert attributes["sam3.checkpoint_sha256"] == "e" * 64
    # The child gets the span's own traceparent and nothing else of the context.
    trace = format(span["context"]["trace_id"], "032x")
    parent = format(span["context"]["span_id"], "016x")
    [payload] = payloads
    assert payload["trace"] == {"traceparent": f"00-{trace}-{parent}-01"}


def test_the_request_carries_only_the_traceparent(monkeypatch):
    headers = []

    def answer(request):
        headers.append(request.headers)
        return httpx.Response(503, json={"detail": "down"})

    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(transport=httpx.MockTransport(answer), **kwargs),
    )
    payload = {
        "endpoint": "https://sam.run.app",
        "request": {"run_id": "run-a"},
        "timeout_seconds": 5,
        "max_response_bytes": 1024,
    }
    valid = lambda value, payload: "valid"  # noqa: E731
    sam3_effect._exchange(dict(payload, trace={"traceparent": TRACEPARENT}), "x", valid)
    sam3_effect._exchange(payload, "x", valid)
    assert headers[0]["traceparent"] == TRACEPARENT
    assert "tracestate" not in headers[0] and "baggage" not in headers[0]
    assert "traceparent" not in headers[1]


def textmap(extract):
    """The process's propagator with Logfire's guard replaced, as configured."""
    inner = propagate.get_global_textmap()
    while isinstance(
        inner, (WarnOnExtractTraceContextPropagator, NoExtractTraceContextPropagator)
    ):
        inner = inner.wrapped
    return inner if extract else NoExtractTraceContextPropagator(inner)


def serve(served, headers=None, bearer="fixture"):
    response = served.client.post(
        "/v1/segment",
        json=run_request(served.raw),
        headers={"Authorization": "Bearer " + bearer, **(headers or {})},
    )
    return response


def test_the_service_continues_the_workers_trace(
    served, monkeypatch, capfire: CaptureLogfire
):
    # LOGFIRE_DISTRIBUTED_TRACING=true: Logfire extracts without its guard.
    monkeypatch.setattr(propagate, "get_global_textmap", lambda: textmap(True))
    assert serve(served, {"traceparent": TRACEPARENT}).status_code == 200
    [span] = named(capfire, SERVE)
    assert format(span["context"]["trace_id"], "032x") == TRACE
    assert format(span["parent"]["span_id"], "016x") == PARENT
    assert parameters(span["attributes"]) == APPLIED
    checkpoint = served.engine.checkpoint_sha256
    assert span["attributes"]["sam3.checkpoint_sha256"] == checkpoint


def test_without_distributed_tracing_the_service_starts_its_own_trace(
    served, monkeypatch, capfire: CaptureLogfire
):
    monkeypatch.setattr(propagate, "get_global_textmap", lambda: textmap(False))
    assert serve(served, {"traceparent": TRACEPARENT}).status_code == 200
    [span] = named(capfire, SERVE)
    assert span["parent"] is None
    assert format(span["context"]["trace_id"], "032x") != TRACE


def test_health_checks_and_refused_requests_open_no_span(
    served, capfire: CaptureLogfire
):
    assert served.client.get("/health/live").status_code == 200
    assert serve(served, bearer="wrong").status_code == 403
    assert named(capfire, SERVE) == []


def test_the_service_configures_logfire_in_the_metadata_mode(monkeypatch, tmp_path):
    modes = []
    monkeypatch.setattr(
        observability,
        "configure_observability",
        lambda **kwargs: modes.append(kwargs.get("capture_mode")),
    )
    monkeypatch.setattr(sam3_server, "offline_checkpoint_digest", lambda: None)
    monkeypatch.setattr(sam3_server, "Sam3Engine", lambda: None)
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setenv("SPECIMEN_SAM3_LAB_TOKEN", TOKEN)
    monkeypatch.setenv("SPECIMEN_SAM3_LAB_DIR", str(tmp_path))
    sam3_server.serve_runs("lab")
    assert modes == [observability.CaptureMode.METADATA]


def test_both_spans_record_the_parameters_as_applied_and_no_content():
    # One definition for both sides, so the two spans always compare.
    request = run_request(b"x", parameters={"label_threshold": 0.6})
    attributes = sam3_effect.span_attributes(request, "c" * 64)
    assert attributes["sam3.concepts"] == ("label",)
    assert attributes["sam3.label_threshold"] == attributes["sam3.record_floor"] == 0.6
    assert set(attributes) == {
        "specimen.id",
        "specimen.run.id",
        "sam3.concepts",
        "sam3.label_threshold",
        "sam3.mask_threshold",
        "sam3.record_floor",
        "sam3.max_detections",
        "sam3.model_revision",
        "sam3.checkpoint_sha256",
    }
