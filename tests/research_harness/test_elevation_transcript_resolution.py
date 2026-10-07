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
from specimen_digitization.research_harness.evidence import validate_resolution
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
