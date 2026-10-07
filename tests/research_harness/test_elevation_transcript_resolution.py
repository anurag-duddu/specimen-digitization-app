"""Offline transcript handover -> real Agent utility loop -> accepted endpoints.

The model is scripted; readings are synthetic. No external model or source call.
"""
from decimal import Decimal
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart

from specimen_digitization.research_harness.accepted_output import (
    AcceptedOutputProofV1, VALIDATOR_VERSION, validation_boundary_pins,
)
from specimen_digitization.research_harness.contracts import FieldKey, SpecialistRole, WorkState, digest
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, _research_input
from specimen_digitization.research_harness.evidence import validate_resolution
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.prompts import MEASUREMENT_EVIDENCE_PROMPT_VERSION
from test_organiser_raw_reading_evidence import build, request_for, two_labels
from test_specialist_feedback import retry_parts, tool_agent


@pytest.mark.parametrize(('line', 'literal', 'lower_ft', 'upper_ft'), (
    ('Elev. 6,400 ft', '6,400 ft', '6400', '6400'),
    ('Camp in mossy forest, 6,400 ft', '6,400 ft', '6400', '6400'),
    ('Camp in mossy forest,6,400 ft', '6,400 ft', '6400', '6400'),
    ('Camp between 6,400 to 6,500 ft', '6,400 to 6,500 ft', '6400', '6500'),
))
def test_written_elevation_reaches_four_accepted_fields_without_human_command(line, literal, lower_ft, upper_ft):
    built = build(two_labels(a=line), [
        ('elevation_from_ft', '2A', literal, line),
        ('elevation_from_ft', '2B', literal, line),
    ])
    request = request_for(built, SpecialistRole.MEASUREMENT)
    assert request.prompt.version == MEASUREMENT_EVIDENCE_PROMPT_VERSION
    assemblies = tuple(item for item in request.assemblies if item.field_key == FieldKey.ELEVATION_FROM_FT)
    assert assemblies
    event_id = assemblies[0].event_id
    assembly_ids = [item.id for item in request.assemblies if item.event_id == event_id]
    turns = []

    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart('invoke_utility', {
                'tool_id': 'settle_elevation',
                'arguments': {'field_key': 'elevation_from_ft', 'event_id': event_id,
                              'assembly_ids': assembly_ids},
            })])
        assert not retry_parts(messages)
        retained = next(part.content for message in messages for part in message.parts
                        if isinstance(part, ToolReturnPart))
        return ModelResponse(parts=[ToolCallPart('final_result', {
            'role': request.role, **json.loads(retained.candidate_json[0]),
        })])

    agent, deps = tool_agent(request, respond)
    result = agent.run_sync('Resolve the written elevation', deps=deps,
                            conversation_id='offline-stated-elevation')
    resolutions = result.output.resolutions
    assert len(turns) == 2
    assert len(resolutions) == 4
    assert all(item.work_state == WorkState.RESOLVED for item in resolutions)
    values = {item.field_key: item for item in resolutions}
    assert Decimal(values[FieldKey.ELEVATION_FROM_FT].value.normalized) == Decimal(lower_ft)
    assert Decimal(values[FieldKey.ELEVATION_TO_FT].value.normalized) == Decimal(upper_ft)
    assert Decimal(values[FieldKey.ELEVATION_FROM_M].value.normalized) == Decimal(lower_ft) * Decimal('0.3048')
    assert Decimal(values[FieldKey.ELEVATION_TO_M].value.normalized) == Decimal(upper_ft) * Decimal('0.3048')
    for item in resolutions:
        assert validate_resolution(request, item) == item
        assert item.value.verbatim_by_observation
        assert line in item.value.verbatim_by_observation.values()
        assert item.value.evidence_ids and item.value.evidence_relations
        if item.value_layer == 'derived':
            assert item.derivation and item.dependencies
    proof = AcceptedOutputProofV1(
        original_request=request, native_run_id=result.run_id,
        conversation_id=result.conversation_id, resolutions=resolutions,
        source_results=tuple(deps.tool_results[request.role]), effect_ids=(),
        model_settings_digest=digest('offline fixture settings'), **validation_boundary_pins(),
    )
    assert proof.validator_version == VALIDATOR_VERSION
    assert proof.resolutions == resolutions


@pytest.mark.parametrize('requested', (
    (FieldKey.ELEVATION_TO_M, FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT),
    (FieldKey.ELEVATION_FROM_FT,),
))
def test_narrowed_measurement_agent_returns_only_requested_fields_and_retains_complete_utility_proof(requested):
    """Actual Agent/tool/validator/acceptance path; model and readings are synthetic.

    The three-field case mirrors an engine request excluding a preserved human
    elevation_from_m. The one-field case mirrors a bounded retry/partial run.
    Neither performs a native publication transaction or a paid model request.
    """
    line, literal = 'Camp at 6,400 ft', '6,400 ft'
    built = build(two_labels(a=line), [
        ('elevation_from_ft', '2A', literal, line),
        ('elevation_from_ft', '2B', literal, line),
    ])
    full = request_for(built, SpecialistRole.MEASUREMENT)
    # Match ResearchEngine.run's immutable request narrowing and revalidation.
    request = type(full).model_validate({**full.model_dump(mode='json'),
        'field_keys': requested, 'field_revisions': {key: 0 for key in requested}})
    assembly = next(item for item in request.assemblies if item.field_key == FieldKey.ELEVATION_FROM_FT)
    arguments = {'field_key': 'elevation_from_ft', 'event_id': assembly.event_id,
                 'assembly_ids': [item.id for item in request.assemblies if item.event_id == assembly.event_id]}
    turns = []

    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            assert 'Copy only returned resolutions whose field_key' in repr(messages)
            return ModelResponse(parts=[ToolCallPart('invoke_utility', {
                'tool_id': 'settle_elevation', 'arguments': arguments,
            })])
        assert not retry_parts(messages)
        result = next(part.content for message in messages for part in message.parts
                      if isinstance(part, ToolReturnPart))
        payload = json.loads(result.candidate_json[0])
        assert len(payload['resolutions']) == 4
        selected = [row for row in payload['resolutions'] if row['field_key'] in requested]
        return ModelResponse(parts=[ToolCallPart('final_result', {
            'role': request.role, 'resolutions': selected,
        })])

    agent, deps = tool_agent(request, respond)
    agent.instructions(PinnedManagedPrompt(request).get_instructions())
    result = agent.run_sync(_research_input(request), deps=deps,
        conversation_id='offline-protected-elevation-subset')
    resolutions = result.output.resolutions
    assert len(turns) == 2 and {row.field_key for row in resolutions} == set(requested)
    retained = tuple(deps.tool_results[request.role])
    assert len(retained) == 1
    assert len(json.loads(retained[0].candidate_json[0])['resolutions']) == 4
    replay = verify_local_utility_v2(request, retained[0])
    assert replay.arguments == arguments
    proof = AcceptedOutputProofV1(original_request=request, native_run_id=result.run_id,
        conversation_id=result.conversation_id, resolutions=resolutions, source_results=retained,
        effect_ids=(), model_settings_digest=digest('offline subset fixture settings'),
        **validation_boundary_pins())
    assert proof.resolutions == resolutions and proof.source_results == retained
    assert all(validate_resolution(request, row, retained) == row for row in resolutions)
    assert FieldKey.ELEVATION_FROM_M not in {row.field_key for row in proof.resolutions}
