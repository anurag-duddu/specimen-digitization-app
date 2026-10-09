"""Derived-only unit repair at the actual offline Agent/acceptance boundary.

Native dependency pins are explicit synthetic checkpoint fixtures. This does not
claim that the production request factory currently supplies those pins.
"""
import json
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.accepted_output import (
    AcceptedCheckpointProofV1, AcceptedOutputProofV1, VALIDATOR_SOURCE_SHA256,
    V3_VALIDATOR_SOURCE_SHA256, validation_boundary_pins,
)
from specimen_digitization.research_harness.contracts import (
    DependencyPin, FieldCheckpoint, FieldKey, FieldResolution, SpecialistRequest,
    SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, elevation_resolutions, settle_elevation,
)
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.sources import local_settlement_result
from test_specialist_feedback import graph_request, retry_parts, tool_agent


def derived_only(pin_kind="exact"):
    full = graph_request(SpecialistRole.MEASUREMENT, FieldKey.ELEVATION_FROM_M, "1200 m")
    source = next(row for row in elevation_resolutions(settle_elevation(full,
        assembly_ids=(full.assemblies[0].id,))) if row.field_key == FieldKey.ELEVATION_FROM_M)
    pins = (DependencyPin(field_key=source.field_key, revision=7,
        digest=digest(source) if pin_kind == "exact" else digest("different checkpoint")),)
    if pin_kind == "missing":
        pins = ()
    if pin_kind == "duplicate":
        pins = (*pins, pins[0].model_copy(update={"revision": 8}))
    requested = tuple(key for key in full.field_keys if key != source.field_key)
    request = SpecialistRequest.model_validate({**full.model_dump(mode="json"),
        "field_keys": requested, "field_revisions": dict.fromkeys(requested, 0),
        "dependencies": pins})
    arguments = {"field_key": str(requested[0]), "event_id": request.events[0].id,
        "assembly_ids": [full.assemblies[0].id]}
    return request, arguments, source


def proof(request, rows, result, *, version=None, source_sha=None):
    metadata = {} if version is None else {
        "validator_version": version, "validator_source_sha256": source_sha}
    return AcceptedOutputProofV1(original_request=request, native_run_id=str(uuid4()),
        conversation_id="offline-pinned-unit-repair", resolutions=rows,
        source_results=(result,), effect_ids=(), model_settings_digest=digest("settings"),
        **validation_boundary_pins(), **metadata)


def test_derived_only_actual_agent_uses_exact_prior_native_revision_without_returning_source():
    request, arguments, source = derived_only()
    turns = []

    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_elevation", "arguments": arguments})])
        assert not retry_parts(messages)
        returned = next(part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart))
        rows = [row for row in json.loads(returned.candidate_json[0])["resolutions"]
            if row["field_key"] in request.field_keys]
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": rows})])

    agent, deps = tool_agent(request, respond)
    output = agent.run_sync("Repair only requested derived elevation fields", deps=deps).output
    assert len(turns) == 2
    assert {row.field_key for row in output.resolutions} == set(request.field_keys)
    assert all(row.work_state == WorkState.RESOLVED for row in output.resolutions)
    assert all(row.derivation.source_field == source.field_key
        and row.derivation.source_revision == 7
        and row.dependencies == request.dependencies for row in output.resolutions)
    [result] = deps.tool_results[request.role]
    assert verify_local_utility_v2(request, result).arguments == arguments
    assert len(json.loads(result.candidate_json[0])["resolutions"]) == 4
    acceptance = proof(request, output.resolutions, result)
    checkpoints = tuple(FieldCheckpoint(scope=request.scope, field_key=row.field_key,
        revision=1, resolution=row, prompt_digest=request.prompt.digest,
        model_settings_digest=acceptance.model_settings_digest,
        source_registry_digest=request.prompt.source_registry_digest) for row in output.resolutions)
    assert AcceptedCheckpointProofV1(acceptance=acceptance, checkpoints=checkpoints).checkpoints == checkpoints


@pytest.mark.parametrize("pin_kind", ("missing", "stale"))
def test_missing_or_stale_native_source_pin_cannot_be_invented_or_rebased(pin_kind):
    request, arguments, _source = derived_only(pin_kind)
    turns = []

    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_elevation", "arguments": arguments})])
        if len(turns) == 2:
            returned = next(part.content for message in messages for part in message.parts
                if isinstance(part, ToolReturnPart))
            rows = [row for row in json.loads(returned.candidate_json[0])["resolutions"]
                if row["field_key"] in request.field_keys]
        else:
            assert len(turns) == 3
            assert "specialist_output_has_unavailable_native_dependency" in str(retry_parts(messages))
            rows = [FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
                value=FieldValue(state=ValueState.UNRESOLVED),
                reason="protected_native_dependency_unavailable:elevation_from_m").model_dump(mode="json")
                for key in request.field_keys]
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": rows})])

    agent, deps = tool_agent(request, respond)
    rows = agent.run_sync("Repair derived fields", deps=deps).output.resolutions
    assert len(turns) == 3
    assert all(row.work_state == WorkState.WAITING_POLICY and row.question is None
        and row.derivation is None and not row.dependencies for row in rows)
    [result] = deps.tool_results[request.role]
    original = json.loads(result.candidate_json[0])["resolutions"]
    assert all(row["derivation"]["source_revision"] == 0 for row in original if row["derivation"])


def test_contradictory_pins_for_one_native_source_are_not_selected_by_order():
    request, arguments, _source = derived_only("duplicate")
    with pytest.raises(EvidenceError, match="pins must be unambiguous"):
        local_settlement_result(request, "settle_elevation", arguments)


def test_current_validator_is_pinned_and_previous_v3_acceptance_still_revalidates_safe_measurements():
    request, arguments, _source = derived_only()
    result = local_settlement_result(request, "settle_elevation", arguments)
    rows = tuple(FieldResolution.model_validate(row)
        for row in json.loads(result.candidate_json[0])["resolutions"]
        if row["field_key"] in request.field_keys)
    current = proof(request, rows, result)
    previous = proof(request, rows, result, version="validate_resolution/v3",
        source_sha=V3_VALIDATOR_SOURCE_SHA256)
    assert current.validator_source_sha256 == VALIDATOR_SOURCE_SHA256
    assert previous.resolutions == current.resolutions


def test_invalid_final_value_is_corrected_from_retained_utility_without_losing_valid_siblings():
    request, arguments, _source = derived_only()
    turns = []

    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_elevation", "arguments": arguments})])
        returned = next(part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart))
        rows = [row for row in json.loads(returned.candidate_json[0])["resolutions"]
            if row["field_key"] in request.field_keys]
        if len(turns) == 2:
            rows[0]["value"]["normalized"] = "9999.00"
        else:
            assert len(turns) == 3
            assert "specialist_output_has_invalid_evidence_or_scope" in str(retry_parts(messages))
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": rows})])

    agent, deps = tool_agent(request, respond)
    rows = agent.run_sync("Repair derived fields", deps=deps).output.resolutions
    assert len(turns) == 3 and len(deps.tool_results[request.role]) == 1
    assert all(row.work_state == WorkState.RESOLVED for row in rows)
    assert rows[0].value.normalized == "1200.00"
    [result] = deps.tool_results[request.role]
    acceptance = proof(request, rows, result)
    assert acceptance.resolutions == rows
    assert verify_local_utility_v2(request, result).arguments == arguments
