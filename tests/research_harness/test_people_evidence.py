"""People roles and recovery against real immutable ordinary label graphs."""
import hashlib

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.contracts import (
    EventHypothesis, EventKind, FieldKey, FieldResolution, SourceFragment, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, assemble_field, missing_irn_resolution, validate_resolution,
)
from specimen_digitization.research_harness.people import (
    PEOPLE_RULE, collector_resolution, reading_assertions,
)
from test_organiser_raw_reading_evidence import Label, build, candidates, request_for, two_labels
from test_specialist_feedback import retry_parts, tool_agent


def recovery_fixture(text="Collectors: J. Smith & A. Brown", *, other=None, decided=None, quote=True):
    body = "forest\n" + text
    peer = None if other is None else "forest\n" + other
    # Ordinary extraction overlooks people. Its captured quote still includes
    # their line. Recovery reuses that row, never writes a replacement row.
    answers = [("habitat", name, "forest", body if name == "2A" else peer or body)
        for name in ("2A", "2B")] if quote else ()
    return build(two_labels(a=body, b=peer, decided=decided), answers)


def collector_assemblies(built):
    return [item for item in built.graph[2] if item.field_key == FieldKey.COLLECTORS]


@pytest.mark.parametrize("names", ("J. Smith & A. Brown", "Smith, John; Brown, Anna", "H. Hoogstraal", "Smith"))
def test_omitted_collector_on_another_label_recovers_exact_name_span_and_all_native_custody(names):
    built = recovery_fixture("Collectors: " + names)
    request = request_for(built, SpecialistRole.PARTIES)
    [assembly] = collector_assemblies(built)
    result = collector_resolution(request, assembly_id=assembly.id)
    assert result.value.literal == result.value.parsed == result.value.normalized == names
    [fragment] = [item for item in request.fragments if item.id in assembly.fragment_ids]
    assert fragment.observation_text[fragment.start:fragment.end] == names
    assert fragment.observation_digest == hashlib.sha256(fragment.observation_text.encode()).hexdigest()
    assert fragment.reader == "handwriting-qwen" and fragment.input_source == "raw_reading"
    assert fragment.region_id == built.readings["2A"].region_id
    assert fragment.asset_digest == built.specimen.asset.sha256 and fragment.asset_generation == "1"
    assert result.value.verbatim_by_observation == {fragment.observation_id: fragment.observation_text}
    assert result.value.input_source_by_observation == {fragment.observation_id: "raw_reading"}
    assert set(result.evidence_ids) <= {item.id for item in built.specimen.run.evidence}
    assert any(item.rule_version == PEOPLE_RULE for item in request.events)
    assert validate_resolution(request, missing_irn_resolution()).value.authority_id is None


def test_collecting_and_identification_lines_keep_distinct_roles_and_no_inferred_irn():
    built = recovery_fixture("Collected by: Jane Smith\nDet. Alex Brown\nPrep. Casey Green")
    request = request_for(built, SpecialistRole.PARTIES)
    [assembly] = collector_assemblies(built)
    assert collector_resolution(request, assembly_id=assembly.id).value.normalized == "Jane Smith"
    assertions = reading_assertions(request.fragments[-1])
    assert {(item.role, item.literal) for item in assertions} == {
        ("collecting", "Jane Smith"), ("determination", "Alex Brown"), ("preparation", "Casey Green")}
    irn = missing_irn_resolution()
    assert irn.work_state == WorkState.NONBLOCKING_EXCEPTION and irn.value.state == ValueState.UNKNOWN
    assert irn.value.parsed is irn.value.normalized is irn.value.authority_id is None
    assert "eparties" in irn.exception.dependency and "determination join" in irn.exception.reevaluate_when


@pytest.mark.parametrize(("line", "literal"), (
    ("Det. Jane Smith", "Jane Smith"), ("Prep. Jane Smith", "Jane Smith"),
    ("Det:Jane Smith", "Jane Smith"), ("Prep:Jane Smith", "Jane Smith"),
    ("Locality: Smith", "Smith"), ("Collectors: J. S.", "J. S."),
    ("Collectors: Jane Smith & Alex Brown", "Jane Smith"),
    ("Collectors: Jane Smith; det. Alex Brown", "Jane Smith; det. Alex Brown"),
    ("Collectors: Jane Smith; determiner Alex Brown", "Jane Smith; determiner Alex Brown"),
    ("Collectors: Jane Smith & prep Alex Brown", "Jane Smith & prep Alex Brown"),
    ("Jane Smith & Alex Brown", "Jane Smith"),
    ("Collectors: Jane Smith\n& Alex Brown", "Jane Smith"),
    ("Collectors: Jane Smith,\nAlex Brown", "Jane Smith,"),
    ("Jane Smith, Alex Brown", "Jane Smith"),
    ("Province: Smith", "Smith"),
))
def test_wrong_role_initials_and_partial_lists_never_ground_from_organiser_assignment(line, literal):
    built = build((Label(line),), [("collectors", name, literal, line) for name in ("1A", "1B")])
    assert not [item for item in candidates(built, "collectors") if item.status == "grounded" and item.literal == literal]
    assert all(item.interpreted_text != literal for item in collector_assemblies(built))


@pytest.mark.parametrize(("line", "literal"), (
    ("Det. Jane Smith", "Jane Smith"), ("Prep. Jane Smith", "Jane Smith"), ("Locality: Smith", "Smith"),
    ("Collectors: Jane Smith & Alex Brown", "Jane Smith"),
    ("Jane Smith & Alex Brown", "Jane Smith"),
    ("Collectors: Jane Smith\n& Alex Brown", "Jane Smith"),
    ("Collectors: Jane Smith,\nAlex Brown", "Jane Smith,"),
    ("Jane Smith, Alex Brown", "Jane Smith"),
))
def test_validator_refuses_a_falsely_accepted_collecting_event_even_when_factory_was_bypassed(line, literal):
    built = build((Label(line),))
    request = request_for(built, SpecialistRole.PARTIES)
    original = request.fragments[0]
    start = line.index(literal)
    fragment = SourceFragment.model_validate(original.model_copy(update={"id": "false-fragment",
        "start": start, "end": start + len(literal), "literal": literal, "granularity": "span"}).model_dump())
    event = EventHypothesis(id="false-event", scope=request.scope, kind=EventKind.COLLECTING,
        fragment_ids=(fragment.id,), evidence_ids=("false-fixture-evidence",), status="accepted",
        validator_version="fixture-false-assignment", reason="Deliberately wrong collecting assignment")
    assembly = assemble_field(assembly_id="false-assembly", scope=request.scope, field_key=FieldKey.COLLECTORS,
        fragments=(fragment,), event=event)
    altered = request.model_copy(update={"fragments": (*request.fragments, fragment),
        "events": (*request.events, event), "assemblies": (assembly,)})
    with pytest.raises(EvidenceError, match="People"):
        collector_resolution(altered, assembly_id=assembly.id)


@pytest.mark.parametrize(("other", "decided"), (("Collectors: J. Smyth", None),
    ("no people line", None)))
def test_alternative_or_silent_readers_remain_located_and_keep_original_spans(other, decided):
    built = recovery_fixture("Collectors: J. Smith", other=other, decided=decided)
    assert not collector_assemblies(built)
    rows = candidates(built, "collectors")
    assert rows and all(item.status == "located" for item in rows)
    assert {item.literal for item in rows} == ({"J. Smith", "J. Smyth"} if "Smyth" in other else {"J. Smith"})
    for row in rows:
        reading = next(item for item in built.specimen.run.observations if item.id == row.observation_id)
        assert reading.literal_text[row.start:row.end] == row.literal


def test_retained_text_without_native_quote_and_initials_are_structured_policy_work():
    for text, reason in (("Collectors: Jane Smith", "native_literal_evidence_unavailable"),
        ("Collectors: J. S.", "initials_without_a_surname")):
        built = recovery_fixture(text, quote=False)
        assert not collector_assemblies(built)
        rows = candidates(built, "collectors")
        assert rows and all(item.status == "located" and item.reason == reason for item in rows)
        assert all(not item.evidence_ids for item in rows)
    assert not collector_assemblies(recovery_fixture("Prep. Jane Smith"))
    assert not candidates(recovery_fixture("forest only", quote=False), "collectors")


def test_recovery_is_deterministic_after_restart_and_unreadable_readings_never_ground():
    from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
    from specimen_digitization.research_harness.contracts import digest
    built = recovery_fixture()
    def serialized(graph):
        return [[item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in part]
            for part in graph]
    assert digest(serialized(built.graph)) == digest(serialized(
        NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)))
    unreadable = build((Label("Collectors: Jane Smith", unreadable=("Jane",)),),
        [("habitat", name, "Jane Smith", "Collectors: Jane Smith") for name in ("1A", "1B")])
    assert not collector_assemblies(unreadable)
    assert all(item.reason == "reading_has_unreadable_spans" for item in candidates(unreadable, "collectors"))


def test_different_labels_need_a_relationship_and_overflow_stays_visible_with_every_raw_reading():
    labels = tuple(Label("Collectors: Person " + name) for name in (
        "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"))
    built = build(labels)
    rows = candidates(built, "collectors")
    assert len(rows) == 5 and rows[-1].reason == "more_people_assertions_than_handed_over"
    assert not collector_assemblies(built)
    assert len({item.observation_id for item in built.graph[0]}) == 12


def test_an_oversized_people_assertion_retains_raw_text_without_aborting_or_truncating_a_value():
    from specimen_digitization.research_harness.contracts import MAX_ORGANISER_LITERAL
    name = "Long" * (MAX_ORGANISER_LITERAL // 4 + 1)
    built = recovery_fixture("Collectors: " + name, quote=False)
    assert not collector_assemblies(built)
    rows = candidates(built, "collectors")
    assert all(item.status == "ungrounded" and item.reason == "person_name_assertion_exceeds_limit" for item in rows)
    assert all(item.observation_id is None and item.start is None and not item.evidence_ids for item in rows)
    assert any(name in item.observation_text for item in built.graph[0])


def test_a_role_line_with_a_written_year_does_not_add_the_date_to_the_person_name():
    built = recovery_fixture("leg. J. Smith, 1948")
    request = request_for(built, SpecialistRole.PARTIES)
    [assembly] = collector_assemblies(built)
    result = collector_resolution(request, assembly_id=assembly.id)
    assert result.value.literal == "J. Smith" and "1948" in next(iter(result.value.verbatim_by_observation.values()))


def test_public_web_or_memory_quote_cannot_supply_native_label_evidence():
    built = recovery_fixture()
    for row in built.specimen.run.evidence:
        row.source = "public_biography"
        row.locator = "region:" + row.region_id
    from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert not [item for item in graph[2] if item.field_key == FieldKey.COLLECTORS]
    assert all(item.reason == "native_literal_evidence_unavailable" for item in graph[5]
        if item.field_key == FieldKey.COLLECTORS)


def test_real_agent_corrects_an_invalid_irn_sibling_and_retains_valid_collector_progress():
    built = recovery_fixture()
    request = request_for(built, SpecialistRole.PARTIES)
    collector = collector_resolution(request, assembly_id=collector_assemblies(built)[0].id)
    bad_irn = FieldResolution(field_key=FieldKey.IDENTIFIED_BY_IRN, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, parsed="123", normalized="123", authority_id="123",
            evidence_ids=["invented"]), evidence_ids=("invented",), reason="Invalid public biography identity")
    turns = []

    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 2:
            assert retry_parts(messages)
        resolutions = (collector, bad_irn if len(turns) == 1 else missing_irn_resolution())
        return ModelResponse(parts=[ToolCallPart("final_result", {"role": request.role,
            "resolutions": [item.model_dump(mode="json") for item in resolutions]})])

    agent, deps = tool_agent(request, respond)
    output = agent.run_sync("Resolve people", deps=deps).output
    assert len(turns) == 2 and output.resolutions == (collector, missing_irn_resolution())


@pytest.mark.parametrize("overflow", (1, 100))
def test_out_of_bounds_native_quote_cannot_ground_recovered_collector(overflow):
    from dataclasses import replace
    from specimen_digitization.application.organiser import format_locator, parse_locator
    from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory

    built = recovery_fixture()
    assert collector_assemblies(built)
    before = [(row.id, row.excerpt, tuple(row.observation_ids)) for row in built.specimen.run.evidence]
    malformed = 0
    for row in built.specimen.run.evidence:
        location = parse_locator(row.locator)
        if location is not None and "Collectors:" in row.excerpt:
            row.locator = format_locator(replace(location, quote_end=location.quote_end + overflow))
            malformed += 1
    assert malformed == 2
    built.graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert not collector_assemblies(built)
    assert all(row.reason == "native_literal_evidence_unavailable" for row in built.graph[5]
        if row.field_key == FieldKey.COLLECTORS)
    assert before == [(row.id, row.excerpt, tuple(row.observation_ids)) for row in built.specimen.run.evidence]
    assert {"forest\nCollectors: J. Smith & A. Brown"} <= {
        row.observation_text for row in built.graph[0]}
