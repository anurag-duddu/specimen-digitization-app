"""Bare pilot collecting dates use exact label context, never preparation codes."""
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.accepted_output import AcceptedOutputProofV1, validation_boundary_pins
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import FieldKey, FieldResolution, SpecialistRole, WorkState, digest
from specimen_digitization.research_harness.evidence import temporal_resolutions, validate_resolution
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from test_organiser_raw_reading_evidence import build, candidates, request_for, two_labels
from test_specialist_feedback import retry_parts, tool_agent


# Exact locality-label layout retained for pilot subject 105526325. Preparation
# and collecting dates occupy different lines; neither extractor assignment nor
# chronological order alone supplies the collecting event.
PILOT_LOCALITY = (
    "IX-17-66-1\nE. Slope Mt.\nMcKimley, Davao\nProv., Mindanao,\nPhilippine Islands\n"
    "H. Hoogstraal\nIX-14-46 3300'\nCNHM"
)


def collecting_fixture(date="IX-14-46", *, line=None, extra="", context=True, field="date_visited_from"):
    line = line if line is not None else date
    text = f"Philippine Islands\nH. Hoogstraal\n{line}{extra}"
    answers = [(field, name, date, line) for name in ("2A", "2B")]
    if context:
        answers += [("country", name, "Philippine Islands", "Philippine Islands") for name in ("2A", "2B")]
        answers += [("collectors", name, "H. Hoogstraal", "H. Hoogstraal") for name in ("2A", "2B")]
    return build(two_labels(a=text), answers)


@pytest.mark.parametrize(("date", "line", "iso"), (
    ("IX-14-46", "IX-14-46 3300'", "1946-09-14"),
    ("IV-24-48", "IV-24-48", "1948-04-24"),
    ("3 sept. '46", "3 sept. '46", "1946-09-03"),
))
def test_complete_bare_collecting_date_grounds_with_each_readers_exact_context(date, line, iso):
    built = collecting_fixture(date, line=line)
    rows = candidates(built, "date_visited_from")
    assert [item.status for item in rows] == ["grounded", "located"]
    request = request_for(built, SpecialistRole.TEMPORAL)
    event = next(item for item in request.events if item.id == rows[0].event_id)
    assert event.reason == "parser_qualified_collecting_locality_context_across_readers"
    written, copied = temporal_resolutions(request, event_id=event.id)
    assert written.value.normalized == copied.value.normalized == iso
    assert written.value.literal == date and written.value.precision == "day"
    assert copied.value_layer == "derived" and copied.derivation.rule_id == "G44"
    date_rows = [item for item in built.specimen.run.evidence if item.excerpt == line]
    assert set(event.evidence_ids) == {item.id for item in date_rows}
    event_fragments = [item for item in request.fragments if item.id in event.fragment_ids]
    assert {item.literal for item in event_fragments} == {date, "Philippine Islands", "H. Hoogstraal"}
    assert all(validate_resolution(request, item) == item for item in (written, copied))
    assert not [item for item in request.assemblies if item.field_key == FieldKey.DATE_IDENTIFIED]


def test_pilot_date_keeps_its_preparation_code_separate_and_preserves_the_whole_reading():
    answers = [("date_visited_from", name, "IX-14-46", "IX-14-46 3300'") for name in ("2A", "2B")]
    answers += [("country", name, "Philippine Islands", "Philippine Islands") for name in ("2A", "2B")]
    answers += [("collectors", name, "H. Hoogstraal", "H. Hoogstraal") for name in ("2A", "2B")]
    built = build(two_labels(a=PILOT_LOCALITY, decided="a"), answers)
    [grounded] = [item for item in candidates(built, "date_visited_from") if item.status == "grounded"]
    request = request_for(built, SpecialistRole.TEMPORAL)
    written, copied = temporal_resolutions(request, event_id=grounded.event_id)
    assert written.value.normalized == copied.value.normalized == "1946-09-14"
    assert set(written.value.verbatim_by_observation.values()) == {PILOT_LOCALITY}
    assert written.value.literal == "IX-14-46"


@pytest.mark.parametrize(("date", "line", "extra"), (
    ("IX-17-66", "IX-17-66-1", ""),
    ("IX-17-66-1", "IX-17-66-1", ""),
    ("IX-14-46", "Determination date: IX-14-46", ""),
    ("IX-14-46", "Prep. IX-14-46", ""),
    ("IX-14-46", "IX-14-46", "\nslide preparation"),
    ("IX-14-46", "IX-14-46", "\ndet. Example"),
    ("IX-14-46", "IX-14-46", "\nIX-15-46"),
    ("IX-14-46", "IX-14-46", "\nCollection date: IX-15-46"),
    ("4-5-48", "4-5-48", ""),
    ("IV-24", "IV-24", ""),
    ("IX-14-46", "IX-14-46 unknown-number", ""),
))
def test_incomplete_preparation_determination_and_competing_events_never_ground(date, line, extra):
    built = collecting_fixture(date, line=line, extra=extra)
    assert not [item for item in candidates(built, "date_visited_from") if item.status == "grounded"]
    assert not [item for item in built.graph[2] if item.field_key in {
        FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO}]


def test_bare_date_without_independently_quoted_context_stays_unqualified():
    built = collecting_fixture(context=False)
    assert not [item for item in candidates(built, "date_visited_from") if item.status == "grounded"]


def test_locality_context_never_supplies_a_determination_event():
    built = collecting_fixture(field="date_identified")
    assert not [item for item in candidates(built, "date_identified") if item.status == "grounded"]
    assert not [item for item in built.graph[2] if item.field_key == FieldKey.DATE_IDENTIFIED]


def test_unreported_competing_reader_and_silent_reader_remain_for_review():
    first = "Philippine Islands\nH. Hoogstraal\nIX-14-46"
    second = "Philippine Islands\nH. Hoogstraal\nIX-15-46"
    answers = [("date_visited_from", "2A", "IX-14-46", "IX-14-46")]
    answers += [("country", name, "Philippine Islands", "Philippine Islands") for name in ("2A", "2B")]
    answers += [("collectors", name, "H. Hoogstraal", "H. Hoogstraal") for name in ("2A", "2B")]
    for other in (first, second):
        built = build(two_labels(a=first, b=other, decided="a"), answers)
        assert not [item for item in candidates(built, "date_visited_from") if item.status == "grounded"]


@pytest.mark.parametrize("protected_to", (False, True))
def test_real_agent_invokes_contextual_date_utility_and_exact_output_proof(protected_to):
    built = collecting_fixture(line="IX-14-46 3300'")
    fields = (FieldKey.DATE_VISITED_FROM, FieldKey.DATE_IDENTIFIED) if protected_to else (
        FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO, FieldKey.DATE_IDENTIFIED)
    protected_value = FieldValue(state=ValueState.UNKNOWN, reason="Retained protected human Unknown")
    if protected_to:
        built.specimen.run.fields[str(FieldKey.DATE_VISITED_TO)] = protected_value
    request = request_for(built, SpecialistRole.TEMPORAL, field_keys=fields,
        field_revisions={key: 0 for key in fields})
    [grounded] = [item for item in candidates(built, "date_visited_from") if item.status == "grounded"]
    arguments = {"field_key": "date_visited_from", "event_id": grounded.event_id}
    turns = []

    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_temporal", "arguments": arguments})])
        assert not retry_parts(messages)
        tool_result = next(part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart))
        full = json.loads(tool_result.candidate_json[0])["resolutions"]
        assert {item["field_key"] for item in full} == {"date_visited_from", "date_visited_to"}
        resolutions = [item for item in full if FieldKey(item["field_key"]) in request.field_keys]
        unresolved = FieldResolution(field_key=FieldKey.DATE_IDENTIFIED,
            work_state=WorkState.WAITING_POLICY, value=FieldValue(state=ValueState.UNRESOLVED),
            reason="missing_policy:unstructured_label_event_unqualified; no determination event")
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": [*resolutions, unresolved.model_dump(mode="json")]})])

    agent, deps = tool_agent(request, respond)
    run = agent.run_sync("Resolve the accepted collecting event", deps=deps,
        conversation_id="offline-collecting-context")
    output = run.output
    assert isinstance(output, SpecialistOutput) and len(turns) == 2
    settled = [item for item in output.resolutions if item.work_state == WorkState.RESOLVED]
    assert [item.value.normalized for item in settled] == ["1946-09-14"] * (1 if protected_to else 2)
    assert {item.field_key for item in output.resolutions} == set(request.field_keys)
    if protected_to:
        assert FieldKey.DATE_VISITED_TO not in {item.field_key for item in output.resolutions}
        assert built.specimen.run.fields[str(FieldKey.DATE_VISITED_TO)] == protected_value
    [result] = deps.tool_results[request.role]
    proof = verify_local_utility_v2(request, result)
    assert proof.as_receipt()["arguments"] == arguments
    accepted = AcceptedOutputProofV1(original_request=request, native_run_id=run.run_id,
        conversation_id=run.conversation_id, resolutions=output.resolutions,
        source_results=tuple(deps.tool_results[request.role]), effect_ids=(),
        model_settings_digest=digest("offline collecting-context fixture"), **validation_boundary_pins())
    assert accepted.resolutions == output.resolutions
    assert accepted.source_results[0].candidate_json == result.candidate_json
    altered = json.loads(result.candidate_json[0])
    altered["resolutions"][0]["value"]["normalized"] = "1966-09-17"
    with pytest.raises(PublicationUnavailable, match="canonical_local_utility_unproved"):
        verify_local_utility_v2(request, result.model_copy(update={"candidate_json": (json.dumps(altered),)}))
