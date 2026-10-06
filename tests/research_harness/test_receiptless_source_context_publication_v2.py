"""Unsent source refusals remain context, not utility or search authority.

The production composer uses scripted models, fixture transport, SQLite and the
existing fake connector. No live source, model or native SQL proof is claimed.
"""
import json
from dataclasses import replace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from test_canonical_materialization import materialization, native_basis
from test_canonical_materialization_v2 import v2_case
from test_native_canonical_contract import ident
from test_unkeyed_label_reading_citation import (
    FAR, LOCALITY, VALUE, geography, instructed, no_network, refusals,
    run_research, specialist_factory, unkeyed,
)
from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.accepted_output import (
    AcceptedCheckpointProofV1, AcceptedOutputProofV1, validation_boundary_pins,
)
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    FieldCheckpoint, FieldKey, FieldResolution, LookupStatus, SourceCoverageReceipt,
    SourceCoverageState, SourceResult, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.local_utility_proof_v2 import local_utility_replays_v2
from specimen_digitization.research_harness.persistence import BlobRef


def refused_then_corrected_geography(log):
    ordinary = specialist_factory(log)

    def factory(request, binding):
        if request.role != SpecialistRole.GEOGRAPHY:
            return ordinary(request, binding)

        async def respond(messages, info):
            results, attempted = support._results(messages)
            if attempted < 4:
                # Two genuine scoped no-matches, an unsendable query, then a
                # corrected precise-location search. This is the failure shape
                # retained from the original321 geography acceptance proof.
                keys = (FieldKey.COUNTRY, FieldKey.PROVINCE_STATE,
                    FieldKey.PRECISE_LOCATION) if not attempted else (FieldKey.PRECISE_LOCATION,)
                calls = []
                for key in keys:
                    query = {**LOCALITY, **FAR, "value": VALUE[key]}
                    if key == FieldKey.PRECISE_LOCATION and not attempted:
                        query["locality"] = "Chicago 600 ft. 12 VI 1948"
                    calls.append(ToolCallPart("lookup_source", {"query": {
                        "source_id": "geolocate", "field_key": str(key),
                        "query_text": json.dumps(query)}},
                        tool_call_id=f"refusal-context-{attempted}-{key}"))
                return ModelResponse(parts=calls, usage=support.USAGE)
            assert len(results) == 4
            assert [item.status for item in results].count(LookupStatus.POLICY) == 1
            chosen = replace(instructed(request), human_literal=None)
            resolutions = tuple(
                geography(request, key, results, chosen)
                if key in (FieldKey.COUNTRY, FieldKey.PROVINCE_STATE) else
                FieldResolution(field_key=key,
                    work_state=WorkState.WAITING_SOURCE if key == FieldKey.PRECISE_LOCATION
                        else WorkState.WAITING_POLICY,
                    value=FieldValue(), reason="No supported value; existing source or missing-policy hold")
                for key in request.field_keys)
            output = SpecialistOutput(role=request.role, resolutions=resolutions)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="refusal-context-output")], usage=support.USAGE)

        return FunctionModel(respond)
    return factory


def test_unsent_sibling_refusal_does_not_block_genuine_human_question_publication(unkeyed, refusals):
    _, specimen, hold, published = run_research(unkeyed,
        refused_then_corrected_geography(unkeyed.model_calls))
    assert refusals == [], f"publication was refused: {refusals}"
    assert published == ["taxon", "country", "province_state", "identified_by_irn"]
    assert hold is None or str(hold) == "native_research_operational_hold"
    assert specimen.run.stage == "processing_blocked" and specimen.run.disposition is None
    for key in ("country", "province_state"):
        assert specimen.run.fields[key].state == ValueState.UNRESOLVED
        assert specimen.run.fields[key].normalized is None
    _, state = support.research_state(unkeyed.fake, unkeyed.specimen_id)
    [job] = list(state["jobs"].values())
    assert len(job["fields"]) == 20
    assert job["fields"]["precise_location"]["work_state"] == "waiting_source"
    assert job["fields"]["city"]["work_state"] == "waiting_policy"
    assert job["fields"]["county"]["work_state"] == "waiting_policy"
    native = job["fields"]["country"]["checkpoint"]
    proof = AcceptedCheckpointProofV1.model_validate_json(unkeyed.research_blobs.get(
        BlobRef(**native["accepted_output_proof"]["capture"])))
    assert len(proof.checkpoints) == 5 and len(proof.acceptance.source_results) == 4
    [refused] = [item for item in proof.acceptance.source_results if item.receipt is None]
    assert refused.status == LookupStatus.POLICY
    assert refused.coverage.state == SourceCoverageState.UNQUALIFIED
    assert refused.coverage.field_key == FieldKey.PRECISE_LOCATION
    assert not refused.evidence and not refused.candidate_json and not refused.coverage.receipt_ids
    # Neither the preflight refusal nor the repair fabricates a fourth source
    # effect or a local utility replay. The accepted negative context survives.
    assert len([item for item in proof.acceptance.source_results if item.receipt]) == 3
    assert local_utility_replays_v2(proof.acceptance.original_request,
        proof.acceptance.source_results, accepted_checkpoint_proof=proof) == ()


def source_refusal(key=FieldKey.COUNTRY):
    return SourceResult(status=LookupStatus.POLICY, coverage=SourceCoverageReceipt(
        source_id="geolocate", field_key=key, state=SourceCoverageState.UNQUALIFIED,
        source_version="synthetic-source-version",
        coverage_limit="No qualified exact scientific search completed",
        reason="Synthetic unsendable place text"))


def acceptance_for(request, results):
    """Actual acceptance validation, with explicitly synthetic checkpoint custody."""
    resolutions = tuple(FieldResolution(field_key=key, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(), reason="No completed source supports a value") for key in request.field_keys)
    settings = digest("synthetic receiptless-context settings")
    return AcceptedCheckpointProofV1(acceptance=AcceptedOutputProofV1(
        original_request=request, native_run_id=ident("synthetic receiptless-context run"),
        conversation_id="synthetic-context-conversation", resolutions=resolutions,
        source_results=results, effect_ids=(), model_settings_digest=settings,
        **validation_boundary_pins()), checkpoints=tuple(FieldCheckpoint(
            scope=request.scope, field_key=row.field_key,
            revision=request.field_revisions[row.field_key] + 1, resolution=row,
            prompt_digest=request.prompt.digest, source_registry_digest=request.prompt.source_registry_digest,
            model_settings_digest=settings, effect_receipt_ids=()) for row in resolutions))


def context_request(materialization):
    request = v2_case(materialization).source.context.request
    return request.model_copy(update={"field_revisions": {key: 0 for key in request.field_keys}})


def test_empty_refusal_preserves_exact_context_without_scientific_or_utility_authority(materialization):
    request = context_request(materialization)
    result = source_refusal()
    proof = acceptance_for(request, (result,))
    before = proof.model_dump(mode="json")
    assert local_utility_replays_v2(request, (result,), accepted_checkpoint_proof=proof) == ()
    assert proof.model_dump(mode="json") == before
    assert all(cp.resolution.work_state == WorkState.WAITING_SOURCE for cp in proof.checkpoints)


@pytest.mark.parametrize("mutation", ["candidate", "evidence", "success", "no_match", "ambiguous",
    "searched", "exhausted", "failed", "query", "qualification", "receipt_ids", "candidate_count",
    "join", "coverage_limit", "foreign_field", "utility", "blank_source", "blank_version", "blank_reason"])
def test_receiptless_claims_and_failed_effect_context_still_hold(materialization, mutation):
    b = v2_case(materialization)
    request, result = context_request(materialization), source_refusal()
    coverage = {}
    if mutation == "candidate": result = result.model_copy(update={"candidate_json": ('{"value":"invented"}',)})
    elif mutation == "evidence": result = result.model_copy(update={"evidence": (b.evidence[0].evidence,)})
    elif mutation in {"success", "no_match", "ambiguous"}: result = result.model_copy(update={"status": LookupStatus(mutation)})
    elif mutation in {"searched", "failed"}: coverage = {"state": SourceCoverageState(mutation)}
    elif mutation == "exhausted": coverage = {"state": SourceCoverageState.EXHAUSTED, "exact_join_attempted": True,
        "receipt_ids": ("invented",), "query_digest": digest("invented query"),
        "qualification_digest": digest("invented qualification")}
    elif mutation == "query": coverage = {"query_digest": digest("invented query")}
    elif mutation == "qualification": coverage = {"qualification_digest": digest("invented qualification")}
    elif mutation == "receipt_ids": coverage = {"receipt_ids": ("invented",)}
    elif mutation == "candidate_count": coverage = {"candidate_count": 0}
    elif mutation == "join": coverage = {"exact_join_attempted": True}
    elif mutation == "coverage_limit": coverage = {"coverage_limit": "Claims completed search"}
    elif mutation == "foreign_field": coverage = {"field_key": FieldKey.HABITAT}
    elif mutation == "utility": coverage = {"source_id": "catalog_number"}
    elif mutation == "blank_source": coverage = {"source_id": " "}
    elif mutation == "blank_version": coverage = {"source_version": " "}
    elif mutation == "blank_reason": coverage = {"reason": " "}
    if coverage: result = result.model_copy(update={"coverage": result.coverage.model_copy(update=coverage)})
    result = SourceResult.model_validate(result.model_dump(mode="json"))
    proof = acceptance_for(request, (result,))
    with pytest.raises(PublicationUnavailable, match="canonical_local_utility_unproved"):
        local_utility_replays_v2(request, (result,), accepted_checkpoint_proof=proof)


@pytest.mark.parametrize("mutation", ["missing", "other_results", "other_request", "invalid_checkpoint"])
def test_empty_refusal_cannot_bypass_exact_forward_acceptance(materialization, mutation):
    request = context_request(materialization)
    result = source_refusal()
    proof = acceptance_for(request, (result,))
    if mutation == "missing": proof = None
    elif mutation == "other_results": result = result.model_copy(update={
        "coverage": result.coverage.model_copy(update={"reason": "Different negative context"})})
    elif mutation == "other_request": request = request.model_copy(update={"retry_command_id": "different-retry"})
    else: proof = proof.model_copy(update={"checkpoints": ()})
    with pytest.raises(PublicationUnavailable, match="canonical_local_utility_acceptance_unproved"):
        local_utility_replays_v2(request, (result,), accepted_checkpoint_proof=proof)
