"""Synthetic accepted-event assertions, real settlement and utility replay.

Independent complete labels are explicitly joined by this fixture's accepted
event. This does not qualify event relations or providers in production.
"""
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from specimen_digitization.research_harness.contracts import (
    FieldKey, SpecialistRequest, SpecialistRole, digest,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, assemble_field, elevation_resolutions, parse_measurement,
    settle_elevation, validate_resolution,
)
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.sources import local_settlement_result
from test_specialist_feedback import graph_request, policy_output, retry_parts, tool_agent


def related_measurements(*texts):
    requests = [graph_request(SpecialistRole.MEASUREMENT,
        FieldKey.ELEVATION_FROM_FT if parse_measurement(text).from_unit == "ft"
        else FieldKey.ELEVATION_FROM_M, text) for text in texts]
    base = requests[0]
    fragments = tuple(item.fragments[0].model_copy(update={
        "id": f"reading-{index}", "label_id": f"label-{index}",
        "region_id": f"label-{index}", "observation_id": f"observation-{index}",
        "order": index}) for index, item in enumerate(requests))
    evidence = tuple(item.evidence[0].model_copy(update={"id": f"evidence-{index}"})
        for index, item in enumerate(requests))
    event = base.events[0].model_copy(update={
        "fragment_ids": tuple(item.id for item in fragments),
        "evidence_ids": tuple(item.id for item in evidence)})
    assemblies = tuple(assemble_field(assembly_id=f"assembly-{index}",
        scope=base.scope, field_key=requests[index].assemblies[0].field_key,
        fragments=(fragment,), event=event)
        for index, fragment in enumerate(fragments))
    return SpecialistRequest.model_validate({**base.model_dump(mode="json"),
        "fragments": fragments, "events": (event,), "assemblies": assemblies,
        "evidence": evidence})


@pytest.mark.parametrize("texts", (
    ("100 ft", "~100 ft"),
    ("100 ft", "100 ± 2 ft"),
    ("100 ft", "100 ± 0 ft"),
    ("100 ± 2 ft", "100 ± 3 ft"),
    ("100 ± 2 ft", "30.48 ± 2 m"),
    ("~100 ft", "30.48 m"),
    ("100 ft", "100 to 100 ft"),
    ("100 ft", "30.5 m"),
    ("100 to 200 ft", "30.48 to 61 m"),
))
def test_complete_same_event_disagreement_cannot_disappear_into_first_assertion_metadata(texts):
    request = related_measurements(*texts)
    arguments = {"field_key": str(request.assemblies[0].field_key),
        "event_id": request.events[0].id,
        "assembly_ids": [item.id for item in request.assemblies]}
    with pytest.raises(EvidenceError, match="G32"):
        local_settlement_result(request, "settle_elevation", arguments)


@pytest.mark.parametrize("texts", (
    ("100 ft", "30.48 m"),
    ("100 to 200 ft", "30.48 to 60.96 m"),
    ("~100 ± 2 ft", "about 30.48 ± 0.6096 m"),
    ("ca. 6,400.50 ft", "≈1950.87240 m"),
    ("-25 to -5 ft", "-7.62 to -1.524 m"),
))
def test_exact_equivalent_related_quantities_retain_both_units_and_every_assertion(texts):
    request = related_measurements(*texts)
    arguments = {"field_key": str(request.assemblies[0].field_key),
        "event_id": request.events[0].id,
        "assembly_ids": [item.id for item in request.assemblies]}
    result = local_settlement_result(request, "settle_elevation", arguments)
    replay = verify_local_utility_v2(request, result)
    assert replay.arguments == arguments and replay.result_digest == digest(result)
    settled = settle_elevation(request, assembly_ids=arguments["assembly_ids"])
    rows = elevation_resolutions(settled)
    assert len(rows) == 4
    assert {row.field_key for row in rows} == set(request.field_keys)
    for row in rows:
        assert validate_resolution(request, row) == row
        assert row.value.verbatim_by_observation == {
            f"observation-{index}": text for index, text in enumerate(texts)}
        assert [json.loads(item)["literal"] for item in row.measurement.assertion_metadata] == list(texts)
        assert row.evidence_ids == tuple(item.id for item in request.evidence)
    for row in rows:
        if row.derivation:
            source = next(item for item in rows if item.field_key == row.derivation.source_field)
            assert source.derivation is None
            assert row.dependencies[0].digest == digest(source)


@pytest.mark.parametrize("text", (
    "100 +/- 2 ft", "about 100 ft +/- 2 ft", "100 to 200 ft +/- 2 ft",
))
def test_ascii_written_uncertainty_is_not_dropped(text):
    parsed = parse_measurement(text)
    assert parsed.uncertainty == "2" and parsed.literal == text


@pytest.mark.parametrize("text", (
    "100 +/- -2 ft", "100 ft +/- 2 m", "100 +/ 2 ft", "100 + / - 2 ft",
    "100 ft +/-", "100 ft ± 2 ± 3 ft", "100 to 200 m ± 2 ft",
))
def test_malformed_or_inapplicable_uncertainty_never_becomes_an_assertion(text):
    with pytest.raises(EvidenceError):
        parse_measurement(text)


def test_real_agent_conflict_feedback_preserves_readings_and_structured_unresolved_work():
    request = related_measurements("100 ± 2 ft", "100 ± 3 ft")
    original = request.model_dump_json()
    arguments = {"field_key": str(request.assemblies[0].field_key),
        "event_id": request.events[0].id,
        "assembly_ids": [item.id for item in request.assemblies]}
    turns = []

    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_elevation", "arguments": arguments})])
        feedback = str(retry_parts(messages))
        assert "research_measurement_assertions_disagree" in feedback
        assert "written uncertainty" in feedback and "never discard one assertion" in feedback
        output = policy_output(request)
        output = output.model_copy(update={"resolutions": tuple(row.model_copy(update={
            "reason": "missing_policy:unstructured_label_event_unqualified; accepted observation-0 "
                      "100 ± 2 ft conflicts with observation-1 100 ± 3 ft"})
            for row in output.resolutions)})
        return ModelResponse(parts=[ToolCallPart("final_result", output.model_dump(mode="json"))])

    agent, deps = tool_agent(request, respond)
    rows = agent.run_sync("Investigate uncertainty disagreement", deps=deps).output.resolutions
    assert len(turns) == 2 and not deps.tool_results
    assert all(row.work_state == "waiting_policy" and row.question is None
        and row.value.parsed is None and not row.dependencies for row in rows)
    assert request.model_dump_json() == original


def test_event_can_retain_another_domains_assembly_without_losing_elevation_replay():
    request = related_measurements("100 ft", "30.48 m")
    date = graph_request(SpecialistRole.TEMPORAL, FieldKey.DATE_VISITED_FROM, "1948-05-12")
    fragment = date.fragments[0].model_copy(update={"id": "date-fragment", "observation_id": "date-observation"})
    event = request.events[0].model_copy(update={
        "fragment_ids": (*request.events[0].fragment_ids, fragment.id)})
    assembly = assemble_field(assembly_id="date-assembly", scope=request.scope,
        field_key=FieldKey.DATE_VISITED_FROM, fragments=(fragment,), event=event)
    request = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "fragments": (*request.fragments, fragment), "events": (event,),
        "assemblies": (*request.assemblies, assembly)})
    arguments = {"field_key": "elevation_from_ft", "event_id": event.id,
        "assembly_ids": [item.id for item in request.assemblies if item.field_key != FieldKey.DATE_VISITED_FROM]}
    result = local_settlement_result(request, "settle_elevation", arguments)
    assert verify_local_utility_v2(request, result).arguments == arguments
    assert len(json.loads(result.candidate_json[0])["resolutions"]) == 4
