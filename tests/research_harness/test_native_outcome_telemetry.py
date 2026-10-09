"""Facade diagnostics with synthetic writer results; no native authority or IO."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness import native_service
from specimen_digitization.research_harness.contracts import FieldKey, FieldResolution, WorkState
from specimen_digitization.research_harness.telemetry import ResearchTrace, metadata_attributes, resolution_outcome


def span_rows(capfire):
    return [row for row in capfire.exporter.exported_spans_as_dict()
        if row["attributes"].get("logfire.span_type") == "span"]


@pytest.mark.parametrize("wire", ["running","processing_blocked","completed"])
@pytest.mark.parametrize("replayed", [False,True])
def test_native_facade_reports_publication_and_domain_finalization_separately(capfire, monkeypatch, wire, replayed):
    prepared=SimpleNamespace(basis=SimpleNamespace(scope=SimpleNamespace(specimen_id="synthetic-specimen",
        job_id="synthetic-run-r3",generation=1),field_key=FieldKey.COUNTRY,
        checkpoint_id="a"*64,binding_digest="b"*64),model_dump=lambda **kwargs:{})
    monkeypatch.setattr(native_service,"PreparedNativePublication",SimpleNamespace(model_validate=lambda _:prepared))
    result=SimpleNamespace(replayed=replayed,published=SimpleNamespace(record_revision=8,publication_digest="c"*64),
        causal=SimpleNamespace(progress_receipt=SimpleNamespace(wire_status=wire)))
    calls=[]
    async def publish(principal, target, **kwargs):
        calls.append((principal,target,kwargs))
        return result
    service=object.__new__(native_service.SqlConnectNativeCanonicalServiceV2)
    service.writer=SimpleNamespace(publish_checkpoint=publish)
    assert asyncio.run(service.publish_checkpoint("synthetic-principal",prepared,
        server_request_identity_digest="d"*64)) is result
    assert len(calls)==1
    rows=span_rows(capfire)
    writer=next(row for row in rows if row["name"]=="research_harness.writer")["attributes"]
    final=next(row for row in rows if row["name"]=="research_harness.finalization")["attributes"]
    assert writer["research.terminal_state"] == ("replayed" if replayed else "published")
    assert writer["research.publication_count"] == 1 and writer["research.revision"] == 8
    assert final["research.terminal_state"] == wire
    assert writer["research.outcome"] == final["research.outcome"] == "completed"
    assert "synthetic-principal" not in json.dumps(rows)


def test_mixed_fields_report_explicit_operational_failure_without_content():
    rows=tuple(FieldResolution(field_key=key,work_state=state,value=FieldValue(),reason="PRIVATE_CANARY")
        for key,state in [(FieldKey.COUNTRY,WorkState.OPERATIONAL_FAILED),
            (FieldKey.CITY,WorkState.WAITING_SOURCE)])
    outcome=resolution_outcome(rows,durable=True)
    assert outcome==dict(terminal_state="mixed",resolved_count=0,failed_count=1,unresolved_count=1,
        stop_states=("operational_failed","waiting_source"))
    assert "PRIVATE_CANARY" not in json.dumps(metadata_attributes(**outcome))


@pytest.mark.parametrize("bad", [dict(failed_count=True),dict(publication_count=21),
    dict(terminal_state="PRIVATE_CANARY"),dict(stop_states=("PRIVATE_CANARY",))])
def test_unapproved_outcome_metadata_is_refused(bad):
    with pytest.raises(ValueError,match="invalid_trace_metadata"):
        metadata_attributes(**bad)
