"""Synthetic exact source context: consumed dependencies cannot erase science."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from specimen_digitization.research_harness.contracts import DependencyPin, FieldKey, SpecialistRole, digest
from specimen_digitization.research_harness.evidence import EvidenceError, elevation_resolutions, settle_elevation
from specimen_digitization.research_harness.measurement import pinned_elevation_resolutions
from test_specialist_feedback import graph_request


def contextual_case(text="1200 m"):
    full = graph_request(SpecialistRole.MEASUREMENT, FieldKey.ELEVATION_FROM_M, text)
    settled = settle_elevation(full, assembly_ids=(full.assemblies[0].id,))
    written = next(row for row in elevation_resolutions(settled) if row.field_key == FieldKey.ELEVATION_FROM_M)
    related = DependencyPin(field_key=FieldKey.COUNTRY, revision=11,
        digest=digest("synthetic previously consumed country checkpoint"))
    native = written.model_copy(update={"dependencies": (related,)})
    pin = DependencyPin(field_key=native.field_key, revision=7, digest=digest(native))
    context = SimpleNamespace(resolution=native, pin=pin,
        accepted_proof_digest=digest("synthetic accepted checkpoint proof"))
    request = SimpleNamespace(field_keys=tuple(key for key in full.field_keys if key != native.field_key),
        dependencies=(pin,), settled_context=(context,), original_request=full)
    return request, settled, written, native, pin


@pytest.mark.parametrize("text", ("1200 m", "~1200 m +/- 10 m", "-20 to 1200 m"))
def test_exact_written_source_context_preserves_science_and_native_consumed_dependencies(text):
    request, settled, written, native, pin = contextual_case(text)
    rows = pinned_elevation_resolutions(request, settled)
    restored = next(row for row in rows if row.field_key == native.field_key)
    assert restored == native and restored.value == written.value and restored.measurement == written.measurement
    assert restored.dependencies != written.dependencies
    for row in rows:
        if row.derivation and row.derivation.source_field == native.field_key:
            assert row.dependencies == (pin,) and row.derivation.source_revision == 7
            assert row.derivation.source_digest == next(peer.derivation.source_digest
                for peer in elevation_resolutions(settled) if peer.field_key == row.field_key)
    assert request.settled_context[0].resolution == native


@pytest.mark.parametrize("tamper", ("value", "event", "assembly", "measurement", "evidence", "dependency",
    "pin_revision", "proof_digest", "duplicate"))
def test_context_cannot_substitute_or_relabel_arbitrary_written_source(tamper):
    request, settled, _, native, pin = contextual_case("~1200 m +/- 10 m")
    context = request.settled_context[0]
    if tamper == "value":
        native = native.model_copy(update={"value": native.value.model_copy(update={"normalized": "1200.01"})})
    elif tamper == "event":
        native = native.model_copy(update={"event_id": "unrelated-event"})
    elif tamper == "assembly":
        native = native.model_copy(update={"assembly_ids": ("another-assembly",)})
    elif tamper == "measurement":
        native = native.model_copy(update={"measurement": native.measurement.model_copy(update={"uncertainty": "0"})})
    elif tamper == "evidence":
        native = native.model_copy(update={"evidence_ids": ("unrelated-evidence",)})
    elif tamper == "dependency":
        native = native.model_copy(update={"dependencies": (native.dependencies[0].model_copy(update={"revision": 12}),)})
    elif tamper == "pin_revision":
        context.pin = pin.model_copy(update={"revision": 8})
    elif tamper == "proof_digest":
        context.accepted_proof_digest = "not-a-proof-digest"
    else:
        request.settled_context = (*request.settled_context, deepcopy(context))
    if tamper in {"value", "event", "assembly", "measurement", "evidence"}:
        # Even a consistently hashed forged context must not replace deterministic
        # source science. The native proof reader is the upstream authority seam.
        pin = pin.model_copy(update={"digest": digest(native)})
        context.pin = pin
        request.dependencies = (pin,)
    context.resolution = native
    with pytest.raises(EvidenceError, match="source context"):
        pinned_elevation_resolutions(request, settled)


def test_missing_full_context_cannot_turn_a_digest_only_contextual_pin_into_a_repair():
    request, settled, _, native, _ = contextual_case()
    request.settled_context = ()
    rows = pinned_elevation_resolutions(request, settled)
    assert all(row.derivation.source_revision == 0 for row in rows if row.derivation)
    assert next(row for row in rows if row.field_key == native.field_key).dependencies == ()



def typed_context_case(text="~1200 m +/- 10 m"):
    from specimen_digitization.research_harness.contracts import SettledFieldContext, SpecialistRequest

    fixture, settled, written, native, pin = contextual_case(text)
    context = SettledFieldContext(resolution=native, pin=pin,
        accepted_proof_digest=fixture.settled_context[0].accepted_proof_digest)
    request = SpecialistRequest.model_validate({**fixture.original_request.model_dump(mode="json"),
        "field_keys": fixture.field_keys, "field_revisions": dict.fromkeys(fixture.field_keys, 0),
        "dependencies": fixture.dependencies, "settled_context": (context,)})
    arguments = {"field_key": str(request.field_keys[0]), "event_id": settled.event_id,
        "assembly_ids": list(settled.assembly_ids)}
    return request, arguments, native, pin


def test_contextual_source_survives_typed_actual_agent_acceptance_and_exact_utility_replay():
    import json
    from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
    from specimen_digitization.research_harness.contracts import FieldResolution, SpecialistRequest, WorkState
    from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
    from test_measurement_dependencies import proof
    from test_specialist_feedback import retry_parts, tool_agent

    request, arguments, native, pin = typed_context_case()
    reopened = SpecialistRequest.model_validate(request.model_dump(mode="json"))
    assert reopened == request and reopened.settled_context[0].resolution == native
    turns = []
    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_elevation", "arguments": arguments})])
        assert not retry_parts(messages)
        result = next(part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart))
        inventory = json.loads(result.candidate_json[0])["resolutions"]
        retained = next(row for row in inventory if row["field_key"] == str(native.field_key))
        assert FieldResolution.model_validate(retained) == native
        rows = [row for row in inventory if row["field_key"] in request.field_keys]
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": rows})])
    agent, deps = tool_agent(request, respond)
    rows = agent.run_sync("Repair requested unit endpoints from exact accepted context", deps=deps).output.resolutions
    assert len(turns) == 2
    assert all(row.work_state == WorkState.RESOLVED and row.dependencies == (pin,)
        and row.derivation.source_revision == pin.revision for row in rows)
    assert native.field_key not in {row.field_key for row in rows}
    [result] = deps.tool_results[request.role]
    assert verify_local_utility_v2(reopened, result).arguments == arguments
    accepted = proof(reopened, rows, result)
    assert accepted.original_request.settled_context[0].resolution == native
    assert accepted.resolutions == rows


def test_typed_context_replay_refuses_other_event_value_even_with_consistent_digests():
    from specimen_digitization.research_harness.contracts import SettledFieldContext, SpecialistRequest
    from specimen_digitization.research_harness.sources import local_settlement_result

    request, arguments, native, pin = typed_context_case()
    forged = native.model_copy(update={"event_id": "unrelated-event"})
    pin = pin.model_copy(update={"digest": digest(forged)})
    context = SettledFieldContext(resolution=forged, pin=pin,
        accepted_proof_digest=request.settled_context[0].accepted_proof_digest)
    crossed = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "dependencies": (pin,), "settled_context": (context,)})
    with pytest.raises(EvidenceError, match="source context differs"):
        local_settlement_result(crossed, "settle_elevation", arguments)
