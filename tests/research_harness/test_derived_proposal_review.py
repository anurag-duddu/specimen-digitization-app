"""A computed spatial proposal is a real, captured reason to ask a human."""

import hashlib

import pytest

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.research_harness.contracts import (
    EvidenceItem, FieldKey, FieldResolution, HumanQuestion, ResearchScope,
    SourceCoverageReceipt, SourceCoverageState, SourceResult, SpecialistRequest,
    SpecialistRole, ToolReceipt, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.sources import canonical_json, result_envelope


FIELD = FieldKey.CITY
EVIDENCE = EvidenceItem(id="computed:1", kind="computed_derivation_result",
    source_id="georeference_spatial", locator="pinned:fixture", response_digest="1" * 64,
    source_version="retrospective-georeferencing-v1", publisher_assertion_id="fixture")
COVERAGE = SourceCoverageReceipt(source_id="georeference_spatial", field_key=FIELD,
    state=SourceCoverageState.SEARCHED, source_version="retrospective-georeferencing-v1",
    qualification_digest=digest("retrospective-georeferencing-v1"),
    receipt_ids=(EVIDENCE.id,), candidate_count=1, coverage_limit="pinned fixture",
    reason="computed_proposal")


def _request():
    scope = ResearchScope(organization_id="org", collection_id="collection", specimen_id="specimen",
        job_id="job", generation=1, input_digest="2" * 64, profile_digest="3" * 64,
        sensitive=False)
    prompt = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=scope.profile_digest,
        source_registry_digest="4" * 64, toolset_digest="5" * 64,
        model_route="fixture", output_schema_digest="6" * 64)
    return SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
        field_keys=(FIELD,), prompt=prompt, field_revisions={FIELD: 0})


def _result(request, *, human=True, automatic=False):
    candidate = {"field_key": str(FIELD), "value": "Yepocapa", "value_layer": "derived",
        "human_review_required": human, "automatic_settlement_allowed": automatic,
        "tool_call_id": "effect:validator", "evidence_ids": [EVIDENCE.id]}
    source = SourceResult(status=LookupStatus.SUCCESS, coverage=COVERAGE, evidence=(EVIDENCE,),
        candidate_json=(canonical_json(candidate),))
    body = result_envelope(source)
    receipt = ToolReceipt(id="effect:computed", scope=request.scope, tool_id="source_lookup",
        source_id="georeference_spatial", field_keys=(FIELD,), effect_id="computed",
        attempt_ids=("attempt",), request_digest="7" * 64, binding_digest="8" * 64,
        outcome=LookupStatus.SUCCESS, effect_status="completed", evidence_ids=(EVIDENCE.id,),
        settled_micro_usd=0, result_json=body,
        result_digest=hashlib.sha256(body.encode()).hexdigest())
    return source.model_copy(update={"receipt": receipt})


def _resolution():
    question = HumanQuestion(field_key=FIELD, question="Review the computed place.",
        reason="derived_proposal", coverage=(COVERAGE,), evidence_ids=(EVIDENCE.id,))
    return FieldResolution(field_key=FIELD, work_state=WorkState.WAITING_HUMAN,
        value=FieldValue(state=ValueState.UNKNOWN, reason="Human decision pending"),
        evidence_ids=(EVIDENCE.id,), source_coverage=(COVERAGE,), question=question,
        reason="derivation_request:fixture")


def test_derived_proposal_reaches_human_only_with_genuine_successful_source():
    request = _request()
    assert validate_resolution(request, _resolution(), (_result(request),)) == _resolution()
    with pytest.raises(EvidenceError, match="captured human proposal"):
        validate_resolution(request, _resolution(), (_result(request, human=False),))
    with pytest.raises(EvidenceError, match="captured human proposal"):
        validate_resolution(request, _resolution(), (_result(request, automatic=True),))


def test_derived_reason_rejects_unrelated_or_failed_coverage():
    for altered in (COVERAGE.model_copy(update={"reason": "no_match"}),
                    COVERAGE.model_copy(update={"state": SourceCoverageState.FAILED}),
                    COVERAGE.model_copy(update={"source_id": "geolocate"})):
        with pytest.raises(ValueError, match="captured computed proposal"):
            HumanQuestion(field_key=FIELD, question="Review", reason="derived_proposal",
                coverage=(altered,), evidence_ids=(EVIDENCE.id,))
