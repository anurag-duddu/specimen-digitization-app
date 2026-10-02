"""Actual local exported trace proof, independent of remote Logfire admission."""

import json

import pytest
from logfire.testing import CaptureLogfire

from specimen_digitization.research_harness.telemetry import ResearchTrace, TraceIdentity, TraceParent, current_trace_parent


def test_linked_effect_checkpoint_and_writer_spans_export_only_metadata(capfire: CaptureLogfire):
    trace = ResearchTrace(TraceIdentity(specimen_id="specimen-test", job_id="job-test", generation=0))
    with trace.span("research"):
        with trace.span("specialist", role="specimen_taxonomy", field_key="taxon"):
            with trace.span("model", effect_id="a" * 64, attempt_id="attempt-1"):
                pass
            with trace.span("tool", effect_id="b" * 64, attempt_id="attempt-2"):
                pass
            with trace.span("checkpoint", field_key="taxon", revision=1):
                with trace.span("writer", field_key="taxon", revision=1):
                    pass
    exported = [s for s in capfire.exporter.exported_spans_as_dict() if s["attributes"].get("logfire.span_type") == "span"]
    assert {s["name"] for s in exported} >= {"research_harness.research", "research_harness.specialist", "research_harness.model", "research_harness.tool", "research_harness.checkpoint", "research_harness.writer"}
    assert len({s["context"]["trace_id"] for s in exported}) == 1
    root = next(s for s in exported if s["name"] == "research_harness.research")
    child = next(s for s in exported if s["name"] == "research_harness.specialist")
    assert child["parent"]["span_id"] == root["context"]["span_id"]
    wire = json.dumps(exported)
    assert "response_body" not in wire and "prompt" not in wire


@pytest.mark.parametrize("extra", [
    {"prompt": "PRIVATE_LABEL_CANARY"},
    {"error": "PRIVATE_PROVIDER_CANARY"},
    {"source_url": "https://unapproved.invalid/?key=secret-canary"},
    {"effect_id": "PRIVATE_LABEL_CANARY"},
    {"role": "attacker"},
    {"field_key": "unknown"},
    {"revision": True},
])
def test_unapproved_content_never_enters_trace(capfire: CaptureLogfire, extra):
    trace = ResearchTrace(TraceIdentity(specimen_id="specimen-test", job_id="job-test", generation=0))
    with pytest.raises(ValueError):
        with trace.span("tool", **extra):
            pytest.fail("Unapproved span was opened")
    assert "CANARY" not in json.dumps(capfire.exporter.exported_spans_as_dict())


def test_source_and_identifier_errors_are_rejected_without_echo():
    with pytest.raises(ValueError) as error:
        TraceIdentity(specimen_id="PRIVATE_CANARY@example.org", job_id="job-test", generation=0)
    assert "PRIVATE_CANARY" not in str(error.value)


def test_exported_failure_does_not_capture_original_exception(capfire: CaptureLogfire):
    trace = ResearchTrace(TraceIdentity(specimen_id="specimen-test", job_id="job-test", generation=1))
    with pytest.raises(RuntimeError, match="PRIVATE_PROVIDER_CANARY"):
        with trace.span("research"):
            with trace.span("model", role="specimen_taxonomy"):
                raise RuntimeError("PRIVATE_PROVIDER_CANARY https://provider.invalid/?key=SECRET_CANARY")
    spans = capfire.exporter.exported_spans_as_dict()
    assert "CANARY" not in json.dumps(spans)
    assert all(s["attributes"].get("research.outcome") == "failed"
               for s in spans if s["attributes"].get("logfire.span_type") == "span")


def test_saved_w3c_parent_links_a_new_research_session(capfire: CaptureLogfire):
    identity = TraceIdentity(specimen_id="specimen-test", job_id="job-test", generation=1)
    with ResearchTrace(identity).span("research"):
        parent = current_trace_parent()
    assert parent is not None
    # JSON persisted values rebuild a fresh context after the original span ends.
    restored = TraceParent(**json.loads(json.dumps({"trace_id":parent.trace_id,
        "span_id":parent.span_id, "trace_flags":parent.trace_flags})))
    with ResearchTrace(identity, parent=restored).span("research"):
        with ResearchTrace(identity).span("resume"):
            pass
    spans = [s for s in capfire.exporter.exported_spans_as_dict()
             if s["attributes"].get("logfire.span_type") == "span"]
    assert len({s["context"]["trace_id"] for s in spans}) == 1
    resumed = [s for s in spans if s["name"] == "research_harness.research"][1]
    assert resumed["parent"]["span_id"] == int(parent.span_id, 16)
