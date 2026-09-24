"""Local exporter evidence across the real, deadline-owned model subprocess."""

import json
import os
from pathlib import Path

import logfire
import pytest
from fastapi.testclient import TestClient
from opentelemetry import baggage, context
from test_application import HEADERS, PREFIX, TOKEN, intake
from test_hardening_concurrency import repository
from test_model_runtime import ModelAdapters, local_model_factory

from specimen_digitization.application.api import SYNTHETIC_TEXT, create_app
from specimen_digitization.application.storage import LocalBlobs


def traced_model_factory(payload):
    """Use the real application configuration with a local buffered exporter."""
    from logfire.testing import TestExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    exporter = TestExporter()
    configure = logfire.configure
    configured = []

    def configure_locally(**options):
        configured.append(options["resource_attributes"])
        # No token, network destination, or provider is used in this fixture.
        options.update(
            send_to_logfire=False,
            console=False,
            additional_span_processors=[
                BatchSpanProcessor(exporter, schedule_delay_millis=60_000)
            ],
        )
        return configure(**options)

    logfire.configure = configure_locally
    if os.getenv("SPECIMEN_TEST_TRACE_UNEXPECTED_ERROR") == "true":
        from specimen_digitization.application.production import ProductionAdapters

        def fail_with_private_body(*args):
            raise RuntimeError("PRIVATE-STORAGE-ERROR-CANARY")

        ProductionAdapters._transcribe_direct = fail_with_private_body
    try:
        return local_model_factory(payload)
    finally:
        # Capture before interpreter exit: atexit flushing cannot satisfy this test.
        root = Path(payload["storage"]["root"]).parent
        (root / (payload.get("route", "extract") + ".trace.json")).write_text(
            json.dumps(
                {
                    "configured": configured,
                    "telemetry": payload.get("telemetry"),
                    "spans": exporter.exported_spans_as_dict(),
                }
            )
        )


class TracedModelAdapters(ModelAdapters):
    def __init__(self, blobs):
        super().__init__(blobs)
        self.model_effect = traced_model_factory


def test_fresh_model_children_export_linked_private_spans_before_return(
    tmp_path, monkeypatch, capfire
):
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    # The child must force metadata policy even if its environment asks for content.
    monkeypatch.setenv("LOGFIRE_CAPTURE_MODE", "approved-content")
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=repository(tmp_path, "sqlite"),
        blobs=blobs,
        adapters=TracedModelAdapters(blobs),
        token=TOKEN,
    )
    token = context.attach(baggage.set_baggage("private", "BAGGAGE-CANARY"))
    try:
        with logfire.span("Synthetic parent"), TestClient(app) as http:
            row = intake(http)
            work = http.get(
                PREFIX + "/specimens/" + row["specimen_id"] + "/workspace",
                headers=HEADERS,
            ).json()
    finally:
        context.detach(token)
    assert work["blocker"] is None, work["blocker"]
    parent_spans = capfire.exporter.exported_spans_as_dict()
    checkpoints = [
        s for s in parent_spans if s["name"] == "Run specimen processing stage"
    ]
    records = [json.loads(p.read_text()) for p in tmp_path.glob("*.trace.json")]
    assert len(records) == 3  # Both independent readers and resolved extraction.
    for record in records:
        assert record["configured"] == [{"specimen.telemetry.capture_mode": "metadata"}]
        spans = record["spans"]
        effect = next(s for s in spans if s["name"] == "Run isolated specimen model")
        assert any(
            effect["parent"]["span_id"] == parent["context"]["span_id"]
            and effect["context"]["trace_id"] == parent["context"]["trace_id"]
            for parent in checkpoints
        )
        attrs = effect["attributes"]
        assert attrs["specimen.id"] == row["specimen_id"]
        assert attrs["specimen.run.id"] == work["run"]["id"]
        assert attrs["specimen.model.outcome"] == "completed"
        assert set(record["telemetry"]) == {"traceparent", "specimen_id", "run_id"}
        agent = next(s for s in spans if s["name"].startswith("invoke_agent "))
        chat = next(s for s in spans if s["name"].startswith("chat "))
        assert agent["parent"]["span_id"] == effect["context"]["span_id"]
        assert chat["parent"]["span_id"] == agent["context"]["span_id"]
        assert agent["context"]["trace_id"] == effect["context"]["trace_id"]
        if attrs["specimen.model.operation"] == "transcribe":
            observation = next(
                o
                for o in work["run"]["observations"]
                if o["id"] == attrs["specimen.observation.id"]
            )
            assert attrs["specimen.region.id"] == observation["region_id"]
            assert attrs["specimen.route.id"] == observation["route_id"]
        exported = json.dumps(record)
        for private in (
            "BAGGAGE-CANARY",
            SYNTHETIC_TEXT,
            "synthetic.png",
            "data:image/",
            work["run"]["dependencies"]["prompts"]["literal-label-transcription"][
                "text"
            ],
        ):
            assert private not in exported


def test_unexpected_child_failure_exports_only_safe_failure_and_does_not_replay(
    tmp_path, monkeypatch, capfire
):
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("SPECIMEN_TEST_TRACE_UNEXPECTED_ERROR", "true")
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=repository(tmp_path, "sqlite"),
        blobs=blobs,
        adapters=TracedModelAdapters(blobs),
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        assert work["blocker"] == "external_outcome_unknown"
        assert not work["run"]["observations"]
        calls = work["run"]["usage"]["external_calls"]
        http.post(path + "/process", headers=HEADERS)
        after = http.get(path + "/workspace", headers=HEADERS).json()
        assert after["run"]["usage"]["external_calls"] == calls
    records = [json.loads(p.read_text()) for p in tmp_path.glob("*.trace.json")]
    assert len(records) == 1
    span = next(
        s for s in records[0]["spans"] if s["name"] == "Run isolated specimen model"
    )
    assert span["attributes"]["specimen.model.outcome"] == "failed"
    assert not span.get("events")
    assert "PRIVATE-STORAGE-ERROR-CANARY" not in json.dumps(records)


@pytest.mark.parametrize(
    "carrier",
    [
        {
            "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
            "baggage": "PRIVATE-BAGGAGE",
            "tracestate": "PRIVATE-STATE",
        },
        {"traceparent": "PRIVATE-INVALID-PARENT"},
        {},
    ],
)
def test_model_context_excludes_baggage_tracestate_and_invalid_parent(
    monkeypatch, carrier
):
    from specimen_digitization.observability import model_trace_context

    monkeypatch.setattr(logfire, "get_context", lambda: carrier)
    result = model_trace_context("specimen-001", "run-001")
    assert result["specimen_id"] == "specimen-001"
    assert result["run_id"] == "run-001"
    if carrier.get("traceparent", "").startswith("00-"):
        assert result["traceparent"] == carrier["traceparent"]
    else:
        assert "traceparent" not in result
    assert "PRIVATE" not in json.dumps(result)
