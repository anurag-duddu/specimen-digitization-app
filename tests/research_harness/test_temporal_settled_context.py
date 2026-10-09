"""Synthetic native From context keeps exact consumed dependency lineage."""
import json

import pytest

from specimen_digitization.research_harness.contracts import (
    DependencyPin, FieldKey, FieldResolution, SettledFieldContext, SpecialistRequest, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.sources import local_settlement_result
from test_temporal_native_subset import narrowed_case


def contextual_date():
    _, request, event, source, _ = narrowed_case()
    related = DependencyPin(field_key=FieldKey.COUNTRY, revision=11,
        digest=digest("synthetic previously consumed country checkpoint"))
    native = source.model_copy(update={"dependencies": (related,)})
    pin = DependencyPin(field_key=native.field_key, revision=7, digest=digest(native))
    context = SettledFieldContext(resolution=native, pin=pin,
        accepted_proof_digest=digest("synthetic native From accepted proof"))
    request = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "dependencies": (pin,), "settled_context": (context,)})
    return request, event, native, pin


def test_full_from_context_reconstructs_exact_source_and_preserves_g44_science_on_replay():
    request, event, native, pin = contextual_date()
    arguments = {"field_key": "date_visited_to", "event_id": event.id}
    reopened = SpecialistRequest.model_validate(request.model_dump(mode="json"))
    result = local_settlement_result(reopened, "settle_temporal", arguments)
    source, end = [FieldResolution.model_validate(row) for row in json.loads(result.candidate_json[0])["resolutions"]]
    assert source == native and source.dependencies != ()
    assert end.dependencies == (pin,) and end.derivation.source_revision == pin.revision
    assert end.value.normalized == source.value.normalized == "1946-09-14"
    assert end.value.precision == source.value.precision == "day"
    assert end.derivation.rule_id == "G44" and end.derivation.operation == "copy_endpoint"
    assert verify_local_utility_v2(reopened, result).arguments == arguments


@pytest.mark.parametrize("tamper", ("value", "event", "assembly", "precision", "evidence"))
def test_full_from_context_cannot_replace_deterministic_event_or_written_precision(tamper):
    request, event, native, pin = contextual_date()
    if tamper == "value":
        native = native.model_copy(update={"value": native.value.model_copy(update={"normalized": "1946-09-15"})})
    elif tamper == "event":
        native = native.model_copy(update={"event_id": "unrelated-date-event"})
    elif tamper == "assembly":
        native = native.model_copy(update={"assembly_ids": ("unrelated-date-assembly",)})
    elif tamper == "precision":
        native = native.model_copy(update={"value": native.value.model_copy(update={"precision": "month"})})
    else:
        native = native.model_copy(update={"evidence_ids": ("unrelated-date-evidence",)})
    pin = pin.model_copy(update={"digest": digest(native)})
    context = SettledFieldContext(resolution=native, pin=pin,
        accepted_proof_digest=request.settled_context[0].accepted_proof_digest)
    request = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "dependencies": (pin,), "settled_context": (context,)})
    with pytest.raises(EvidenceError, match="source context"):
        local_settlement_result(request, "settle_temporal", {"field_key": "date_visited_to", "event_id": event.id})


def test_contextual_to_actual_agent_outputs_only_target_with_exact_acceptance():
    from uuid import uuid4
    from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
    from specimen_digitization.research_harness.accepted_output import AcceptedOutputProofV1, validation_boundary_pins
    from test_specialist_feedback import retry_parts, tool_agent

    request, event, native, pin = contextual_date()
    turns = []
    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {"tool_id": "settle_temporal",
                "arguments": {"field_key": "date_visited_to", "event_id": event.id}})])
        assert not retry_parts(messages)
        result = next(part.content for message in messages for part in message.parts if isinstance(part, ToolReturnPart))
        rows = json.loads(result.candidate_json[0])["resolutions"]
        assert FieldResolution.model_validate(rows[0]) == native
        return ModelResponse(parts=[ToolCallPart("final_result", {"role": request.role,
            "resolutions": [row for row in rows if row["field_key"] == "date_visited_to"]})])
    agent, deps = tool_agent(request, respond)
    output = agent.run_sync("Repair To from exact accepted From context", deps=deps).output
    assert len(turns) == 2 and len(output.resolutions) == 1
    [end] = output.resolutions
    assert end.field_key == FieldKey.DATE_VISITED_TO and end.dependencies == (pin,)
    assert end.derivation.source_revision == pin.revision
    proof = AcceptedOutputProofV1(original_request=request, native_run_id=str(uuid4()),
        conversation_id="offline-contextual-date-repair", resolutions=output.resolutions,
        source_results=tuple(deps.tool_results[request.role]), effect_ids=(),
        model_settings_digest=digest("offline contextual date settings"), **validation_boundary_pins())
    assert proof.original_request.settled_context[0].resolution == native
    assert proof.resolutions == output.resolutions
