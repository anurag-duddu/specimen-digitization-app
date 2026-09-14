"""Actual classifier child and FunctionModel, using local storage and fake TLS."""

import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import logfire
from fastapi.testclient import TestClient
from opentelemetry import baggage, context
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
import pytest
from test_application import HEADERS, PREFIX, TOKEN, intake

from specimen_digitization.application.api import create_app, SYNTHETIC_TEXT
from specimen_digitization.application.classifier_runtime import ConfiguredClassifier
from specimen_digitization.application.hf_collection_classifier import HFClassifierConfig
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.bounded_telemetry import worker_trace_scope


def bounded_classifier_factory(payload):
    import socket
    import requests
    import httpx
    from specimen_digitization import bounded_trace_transport
    from specimen_digitization.application.hf_collection_classifier import HFCollectionClassifier
    from test_classifier_runtime import local_classifier_factory

    root = Path(payload["storage"]["root"]).parent
    (root / "classifier-carrier.json").write_text(json.dumps(payload.get("telemetry", {})))

    def forbidden(*args, **kwargs):
        raise AssertionError("Native network is forbidden in the classifier fixture")

    socket.getaddrinfo = forbidden
    socket.socket.connect = forbidden
    requests.Session.request = forbidden
    httpx.Client.send = forbidden
    httpx.AsyncClient.send = forbidden

    class LocalTLS:
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"

        def settimeout(self, timeout):
            assert timeout > 0

        def sendall(self, wire):
            with (root / "classifier-wire.bin").open("ab") as output:
                output.write(len(wire).to_bytes(4, "big") + wire)

        def recv(self, count):
            data, self.response = self.response[:count], self.response[count:]
            return data

        def close(self):
            pass

    bounded_trace_transport._open_tls = lambda deadline: LocalTLS()
    if os.getenv("SPECIMEN_TEST_CLASSIFIER_PRIVATE_FAILURE") == "true":
        def private_failure(*args, **kwargs):
            raise RuntimeError("PRIVATE-CLASSIFIER-ERROR-CANARY")

        HFCollectionClassifier.classify = private_failure
    return local_classifier_factory(payload)


@pytest.fixture
def approved_tracing(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    values = {
        "SPECIMEN_TRACE_EXPORT_MODE": "bounded-v1",
        "SPECIMEN_TRACE_APPROVAL_SHA256": "06af8483b7b190a5b0f2549475681a60483f2aff98a714472baad28376703b48",  # pragma: allowlist secret (approval digest)
        "SPECIMEN_TRACE_SCOPE_SHA256": "a" * 64,
        "APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "metadata",
        "LOGFIRE_SEND_TO_LOGFIRE": "false", "LOGFIRE_HEAD_SAMPLE_RATE": "1.0",
        "LOGFIRE_DISTRIBUTED_TRACING": "false", "LOGFIRE_SERVICE_NAME": "specimen-worker",
        "LOGFIRE_TOKEN": "synthetic-writer",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SPECIMEN_TRACE_LEDGER_PATH", raising=False)


def exercise(tmp_path, *, allow_sensitive=True, repeat=False):
    blobs = LocalBlobs(tmp_path / "blobs")
    config = HFClassifierConfig(
        route_id="synthetic-classifier", expected_model_id="fixture/classifier",
        expected_provider="novita", prompt_text="PRIVATE-CLASSIFIER-PROMPT-CANARY",
        prompt_version="synthetic-prompt-v1", approved=True, total_deadline_seconds=5,
    )
    classifier = ConfiguredClassifier(
        blobs, config, allow_sensitive=allow_sensitive, effect=bounded_classifier_factory,
    )
    app = create_app(
        mode="synthetic", repository=SQLiteRepository(tmp_path / "state.db"),
        blobs=blobs, adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        classifier=classifier, token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        before = http.get(path + "/workspace", headers=HEADERS).json()
        if repeat:
            http.post(path + "/process", headers=HEADERS)
        after = http.get(path + "/workspace", headers=HEADERS).json()
    return before, after


def exported_spans(tmp_path):
    wire = (tmp_path / "classifier-wire.bin").read_bytes()
    spans, bodies = [], []
    while wire:
        count = int.from_bytes(wire[:4], "big")
        frame, wire = wire[4:4 + count], wire[4 + count:]
        headers, body = frame.split(b"\r\n\r\n", 1)
        assert headers.startswith(b"POST /v1/traces HTTP/1.1")
        request = ExportTraceServiceRequest.FromString(body)
        spans.extend(span for resource in request.resource_spans
                     for scope in resource.scope_spans for span in scope.spans)
        bodies.append(body)
    body = b"".join(bodies)
    for private in (b"CANARY", SYNTHETIC_TEXT.encode(), b"synthetic.png", b"\x89PNG",
                    b"synthetic_visible_structure", b"data:image/"):
        assert private not in body
    assert all(not span.events and not span.links and not span.status.message for span in spans)
    return spans


def attributes(span):
    return {item.key: item.value.string_value for item in span.attributes}


def test_classifier_child_exports_metadata_linked_to_actual_parent(
    approved_tracing, tmp_path, capfire,
):
    token = context.attach(baggage.set_baggage("private", "PRIVATE-BAGGAGE-CANARY"))
    try:
        with WorkerDeadline(time.monotonic() + 30, workspace=tmp_path).scope():
            with worker_trace_scope() as ledger, logfire.span("Synthetic classifier parent"):
                before, after = exercise(tmp_path)
                snapshot = ledger.snapshot()
    finally:
        context.detach(token)
    assert before["run"]["classification"]["status"] == "completed"
    assert after["run"]["classification"] == before["run"]["classification"]
    assert snapshot["completion"] and snapshot["requests"] == snapshot["accepted"] > 0
    assert snapshot["unknown"] == 0
    assert (tmp_path / "classifier-model-calls").read_text() == "called\n"
    carrier = json.loads((tmp_path / "classifier-carrier.json").read_text())
    assert set(carrier) == {"traceparent", "specimen_id", "run_id"}
    assert "CANARY" not in json.dumps(carrier)
    spans = exported_spans(tmp_path)
    effect = next(span for span in spans if span.name == "Run isolated specimen model")
    attrs = attributes(effect)
    assert attrs["specimen.model.operation"] == "classify"
    assert attrs["specimen.model.outcome"] == "completed"
    assert attrs["specimen.id"] == before["specimen_id"]
    assert attrs["specimen.run.id"] == before["run"]["id"]
    assert attrs["specimen.route.id"] == "synthetic-classifier"
    parents = [span for span in capfire.exporter.exported_spans
               if span.name == "Process specimen checkpoint"]
    assert any(parent.context.trace_id == int.from_bytes(effect.trace_id, "big")
               and parent.context.span_id == int.from_bytes(effect.parent_span_id, "big")
               for parent in parents)
    agent = next(span for span in spans if span.name == "Invoke specimen agent")
    assert agent.parent_span_id == effect.span_id and agent.trace_id == effect.trace_id


def test_sensitive_denial_has_metadata_without_model_execution(approved_tracing, tmp_path, capfire):
    with WorkerDeadline(time.monotonic() + 30, workspace=tmp_path).scope():
        with worker_trace_scope() as ledger:
            before, _ = exercise(tmp_path, allow_sensitive=False)
            snapshot = ledger.snapshot()
    assert before["run"]["classification"]["status"] == "blocked"
    assert not (tmp_path / "classifier-model-calls").exists()
    effect = next(span for span in exported_spans(tmp_path) if span.name == "Run isolated specimen model")
    assert attributes(effect)["specimen.model.outcome"] == "blocked"
    assert snapshot["completion"] and snapshot["requests"] == snapshot["accepted"] > 0


def test_classifier_private_failure_exports_safe_failure_and_never_replays(
    approved_tracing, tmp_path, monkeypatch, capfire,
):
    monkeypatch.setenv("SPECIMEN_TEST_CLASSIFIER_PRIVATE_FAILURE", "true")
    with WorkerDeadline(time.monotonic() + 30, workspace=tmp_path).scope():
        with worker_trace_scope() as ledger:
            before, after = exercise(tmp_path, repeat=True)
            snapshot = ledger.snapshot()
    assert before["blocker"] == after["blocker"] == "external_outcome_unknown"
    assert before["run"]["usage"]["external_calls"] == after["run"]["usage"]["external_calls"]
    assert not (tmp_path / "classifier-model-calls").exists()
    effect = next(span for span in exported_spans(tmp_path) if span.name == "Run isolated specimen model")
    assert attributes(effect)["specimen.model.outcome"] == "failed"
    assert snapshot["completion"] is False


def test_classifier_missing_trace_approval_stops_before_model_or_export(
    approved_tracing, tmp_path, monkeypatch, capfire,
):
    monkeypatch.delenv("SPECIMEN_TRACE_APPROVAL_SHA256")
    with WorkerDeadline(time.monotonic() + 30, workspace=tmp_path).scope():
        with worker_trace_scope() as ledger:
            before, after = exercise(tmp_path, repeat=True)
            snapshot = ledger.snapshot()
    assert before["blocker"] == after["blocker"] == "external_outcome_unknown"
    assert before["run"]["usage"]["external_calls"] == after["run"]["usage"]["external_calls"]
    assert not (tmp_path / "classifier-model-calls").exists()
    assert not (tmp_path / "classifier-wire.bin").exists()
    assert snapshot["completion"] is False and snapshot["requests"] == 0


@pytest.mark.parametrize("configured", [False, True])
def test_unconfigured_or_unapproved_classifier_does_not_start_child(
    tmp_path, monkeypatch, configured,
):
    from specimen_digitization.application import bounded_effect

    def forbidden(*args, **kwargs):
        pytest.fail("An unapproved classifier cannot create an effect child")

    monkeypatch.setattr(bounded_effect, "run_isolated", forbidden)
    config = None if not configured else HFClassifierConfig(
        route_id="synthetic", expected_model_id="fixture/classifier", expected_provider="novita",
        prompt_text="Synthetic prompt", prompt_version="1", approved=False,
    )
    facade = ConfiguredClassifier(LocalBlobs(tmp_path / "blobs"), config)
    run = SimpleNamespace(profile=SimpleNamespace(execution=SimpleNamespace(external_timeout_seconds=5)),
                          dependencies={})
    run.dependencies["classifier"] = facade.pin(run)
    result = facade.bind(SimpleNamespace(run=run), SimpleNamespace(nodes=[])).classify(
        SimpleNamespace(input_sha256="a" * 64),
    )
    assert result.status == "blocked" and result.reason == "approved_classifier_route_missing"
