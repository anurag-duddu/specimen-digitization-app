"""Collection evidence procedures on retained synthetic native label readings.

The request factory, collection procedure, validator and local broker are real.
These cases make no model or publisher calls and claim no live publication proof.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from test_organiser_handover import FieldSpec, RegionSpec, build as historical_build, request_for
from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.collection import (
    COLLECTION_RULE, collection_resolution, qualify_collection_span,
)
from specimen_digitization.research_harness.contracts import (
    EventHypothesis, EventKind, FieldKey, FieldResolution, FragmentRelation,
    RelationKind, SourceFragment, SpecialistRequest, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, assemble_field, dts_policy_resolution, validate_resolution,
)
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry, UtilityInputError


def build(*args, **kwargs):
    return historical_build(*args, **kwargs, collection_recovery=True)


def retained(text, *, raw=None, native_quote=True, claimed_key="country", claimed_literal=None):
    """The unrelated organiser claim retains a native quote without proposing collection fields."""
    fields = (FieldSpec(claimed_key, claimed_literal or text),) if native_quote else ()
    return build((RegionSpec(text, raw=raw),), fields)



def undecided(built, *, regions=None):
    """A genuinely undecided native reading graph, retaining every alternative."""
    from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
    for index, transcript in enumerate(built.specimen.run.transcripts):
        if regions is not None and index not in regions:
            continue
        transcript.resolved = False
        transcript.selected_observation_id = None
        transcript.decision_kind = None
        transcript.handoffs = [row.model_copy(update={"role":"raw_reading"}) for row in transcript.handoffs]
    built.graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope, collection_recovery=True)
    return built


def collection_request(built):
    return request_for(built, SpecialistRole.COLLECTION)


def span(text, literal):
    built = retained(text, native_quote=False)
    original = next(row for row in built.graph[0] if row.input_source == "decided_transcript")
    start = text.index(literal)
    data = original.model_dump(mode="json")
    data.update(start=start, end=start + len(literal), literal=literal, granularity="span")
    return SourceFragment.model_validate(data)


def invoke(request, tool_id, arguments):
    return asyncio.run(SourceBroker(SourceRegistry(())).invoke_utility(request, tool_id, arguments))


@pytest.mark.parametrize(("key", "text", "literal", "expected"), (
    (FieldKey.FMNH_INS_NUMBER, "FMNHINS 0012345", "FMNHINS 0012345", "0012345"),
    (FieldKey.FMNH_INS_NUMBER, "FMNH-INS #0012345", "FMNH-INS #0012345", "0012345"),
    (FieldKey.FMNH_INS_NUMBER, "Catalog number: 0012345", "0012345", "0012345"),
    (FieldKey.FMNH_INS_NUMBER, "FMNH INS\n0012345", "FMNH INS\n0012345", "0012345"),
    (FieldKey.COLLECTION_CODE, "Collection code: INSECTS", "INSECTS", "INSECTS"),
    (FieldKey.COLLECTION_CODE, "Collection code: AB 12", "AB 12", "AB 12"),
    (FieldKey.HABITAT, "oak woodland margin", "oak woodland margin", "oak woodland margin"),
    (FieldKey.HABITAT, "Habitat: beneath fallen log", "beneath fallen log", "beneath fallen log"),
    (FieldKey.COLLECTION_METHOD, "light trap", "light trap", "light trap"),
    (FieldKey.COLLECTION_METHOD, "Collection method: hand digging at rotting stump",
        "hand digging at rotting stump", "hand digging at rotting stump"),
))
def test_exact_field_qualification_keeps_catalogue_zeroes_and_explicit_unlisted_phrases(key, text, literal, expected):
    fragment = span(text, literal)
    assert qualify_collection_span(key, fragment) == expected
    assert fragment.literal == literal and fragment.observation_text == text


@pytest.mark.parametrize(("key", "text", "literal"), (
    (FieldKey.FMNH_INS_NUMBER, "0012345", "0012345"),
    (FieldKey.FMNH_INS_NUMBER, "Locality number: 0012345", "0012345"),
    (FieldKey.COLLECTION_CODE, "FMNHINS", "FMNHINS"),
    (FieldKey.COLLECTION_CODE, "Collection code: FMNH INS 0012345", "FMNH INS 0012345"),
    (FieldKey.COLLECTION_CODE, "Collection code: 0012345", "0012345"),
    (FieldKey.COLLECTION_CODE, "Collection code: VI-24-68-7", "VI-24-68-7"),
    (FieldKey.COLLECTION_CODE, "INSECTS", "INSECTS"),
    (FieldKey.HABITAT, "Habitat: light trap", "light trap"),
    (FieldKey.HABITAT, "Habitat: Davao Prov.", "Davao Prov."),
    (FieldKey.HABITAT, "Habitat: Synthetic Collector", "Synthetic Collector"),
    (FieldKey.HABITAT, "Habitat: VI-24-68-7", "VI-24-68-7"),
    (FieldKey.HABITAT, "Habitat: FMNH INS 0012345", "FMNH INS 0012345"),
    (FieldKey.HABITAT, "Habitat: FMNHINS", "FMNHINS"),
    (FieldKey.COLLECTION_METHOD, "Collection method: oak woodland margin", "oak woodland margin"),
    (FieldKey.COLLECTION_METHOD, "Collection method: FMNH INS 0012345", "FMNH INS 0012345"),
    (FieldKey.COLLECTION_METHOD, "slide prepared from light trap", "light trap"),
    (FieldKey.HABITAT, "Locality: oak woodland", "oak woodland"),
))
def test_catalogue_locality_preparation_and_field_kind_do_not_cross_qualify(key, text, literal):
    with pytest.raises(EvidenceError):
        qualify_collection_span(key, span(text, literal))


@pytest.mark.parametrize(("text", "key", "expected"), (
    ("FMNH INS 0012345", FieldKey.FMNH_INS_NUMBER, "0012345"),
    ("FMNH INS\n0012345", FieldKey.FMNH_INS_NUMBER, "0012345"),
    ("Habitat: oak woodland margin", FieldKey.HABITAT, "oak woodland margin"),
    ("Collecting method: light trap", FieldKey.COLLECTION_METHOD, "light trap"),
    ("Collection code: INSECTS", FieldKey.COLLECTION_CODE, "INSECTS"),
    ("Collection code: AB 12", FieldKey.COLLECTION_CODE, "AB 12"),
))
def test_factory_recovers_omitted_collection_assertion_from_original_native_quote(text, key, expected):
    built = retained(text)
    request = collection_request(built)
    result = collection_resolution(request, key)
    assert result.work_state == WorkState.RESOLVED
    assert result.value.parsed == result.value.normalized == expected
    assert result.evidence_ids and set(result.evidence_ids) <= {row.id for row in built.specimen.run.evidence}
    assert result.value.verbatim_by_observation == {built.first_reading[0].id: text}
    assert built.specimen.run.fields["country"].literal == text
    assert all(row.observation_text == text for row in request.fragments)
    assert validate_resolution(request, result) == result


def test_misfiled_method_is_recovered_without_promoting_the_habitat_hint():
    built = retained("light trap", claimed_key="habitat")
    request = collection_request(built)
    assert collection_resolution(request, FieldKey.COLLECTION_METHOD).value.parsed == "light trap"
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY
    assert built.specimen.run.fields["habitat"].literal == "light trap"
    assert any(row.field_key == FieldKey.HABITAT and row.literal == "light trap"
        for row in built.graph[5])


@pytest.mark.parametrize("partial", ("oak", "oak woodland"))
def test_incomplete_organiser_span_does_not_conflict_with_recovered_complete_assertion(partial):
    text = "Habitat: oak woodland margin"
    built = retained(text, claimed_key="habitat", claimed_literal=partial)
    result = collection_resolution(collection_request(built), FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED
    assert result.value.parsed == "oak woodland margin"
    assert built.specimen.run.fields["habitat"].literal == partial
    assert any(row.field_key == FieldKey.HABITAT and row.literal == partial for row in built.graph[5])


def test_recovery_uses_evidenced_raw_reader_when_decided_reader_has_no_native_quote():
    text = "Habitat: oak woodland"
    built = build((RegionSpec(text),), (FieldSpec("country", text, shape="reading", readers=(1,)),))
    request = collection_request(built)
    raw = next(row for row in request.fragments if row.input_source == "raw_reading")
    assert {observation for row in built.specimen.run.evidence for observation in row.observation_ids} == {
        raw.observation_id}
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED and result.value.parsed == "oak woodland"
    assert result.value.verbatim_by_observation == {raw.observation_id: text}
    assert result.value.input_source_by_observation == {raw.observation_id: "raw_reading"}
    assert set(result.evidence_ids) == {row.id for row in built.specimen.run.evidence}
    assert validate_resolution(request, result) == result


def test_explicit_multiline_habitat_preserves_exact_span_and_both_raw_readings():
    text = "Habitat: oak\n  woodland margin\nCollection method: light trap"
    built = retained(text)
    request = collection_request(built)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED
    assert result.value.literal == "oak\n  woodland margin"
    assert result.value.parsed == "oak\n  woodland margin"
    assembly = next(row for row in request.assemblies if row.id in result.assembly_ids)
    fragment = next(row for row in request.fragments if row.id in assembly.fragment_ids)
    assert fragment.observation_text[fragment.start:fragment.end] == result.value.literal
    assert {row.reader for row in request.fragments} == {"handwriting-qwen", "handwriting-muse"}
    assert all(row.observation_text == text for row in request.fragments)
    assert validate_resolution(request, result) == result


@pytest.mark.parametrize("raw", ("Habitat: wet grassland", "Synthetic Locality", ""))
def test_disagreeing_or_absent_reader_counterpart_stays_structured_review(raw):
    request = collection_request(undecided(retained("Habitat: oak woodland", raw=raw)))
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY
    assert result.value.state == ValueState.UNRESOLVED and result.value.parsed is None
    assert result.question is None and not result.evidence_ids
    assert "collection" in result.reason


def test_unsettled_habitat_does_not_suppress_omitted_method_supported_by_both_readers():
    text = "Habitat: oak woodland\nCollection method: light trap"
    raw = "Habitat: wet grassland\nCollection method: light trap"
    built = build((RegionSpec(text, raw=raw),),
        (FieldSpec("country", "light trap", quote="Collection method: light trap"),))
    request = collection_request(undecided(built))
    habitat = collection_resolution(request, FieldKey.HABITAT)
    method = collection_resolution(request, FieldKey.COLLECTION_METHOD)
    assert habitat.work_state == WorkState.WAITING_POLICY
    assert method.work_state == WorkState.RESOLVED and method.value.parsed == "light trap"
    assert validate_resolution(request, method) == method


@pytest.mark.parametrize("text", ("Habitat: oak woodland", "Synthetic Locality", ""))
def test_no_native_quote_or_no_qualified_evidence_does_not_manufacture_a_value(text):
    request = collection_request(retained(text, native_quote=False))
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY
    assert result.value.literal is None and result.value.parsed is None
    assert not result.assembly_ids and not result.evidence_ids and result.question is None


def test_collection_kind_qualification_rejects_unreadable_fragment():
    fragment = span("Habitat: oak woodland", "oak woodland").model_copy(update={"unreadable": True})
    with pytest.raises(EvidenceError, match="readable"):
        qualify_collection_span(FieldKey.HABITAT, fragment)


@pytest.mark.parametrize("corruption", ("asset", "region", "observation", "extra_observation"))
def test_recovery_cannot_use_native_quote_from_another_source_identity(corruption):
    text = "Habitat: oak woodland"

    def corrupt(row):
        if corruption == "extra_observation":
            return row.model_copy(update={"observation_ids": [*row.observation_ids, "another-reading"]})
        key = {"asset": "asset_id", "region": "region_id", "observation": "observation_ids"}[corruption]
        return row.model_copy(update={key: ["another-reading"] if corruption == "observation" else "another-identity"})

    built = build((RegionSpec(text),), (FieldSpec("country", text, edit=corrupt),))
    result = collection_resolution(collection_request(built), FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY
    assert not result.evidence_ids and not result.assembly_ids


def test_unknown_phrase_with_native_evidence_is_review_work_without_a_question():
    request = collection_request(retained("Synthetic Locality"))
    assert request.evidence
    for key in (FieldKey.HABITAT, FieldKey.COLLECTION_METHOD, FieldKey.COLLECTION_CODE):
        result = collection_resolution(request, key)
        assert result.work_state == WorkState.WAITING_POLICY
        assert result.question is None and result.value.state == ValueState.UNRESOLVED


def test_independent_catalogue_labels_agree_on_digits_without_losing_original_prefixes():
    texts = ("fmnh_ins_number: FMNH INS 0012345", "fmnh_ins_number: 0012345")
    built = build(tuple(RegionSpec(text) for text in texts), keyed=True)
    request = collection_request(built)
    result = collection_resolution(request, FieldKey.FMNH_INS_NUMBER)
    assert result.work_state == WorkState.RESOLVED
    assert result.value.parsed == result.value.normalized == "0012345"
    assert len(result.assembly_ids) == 2
    assert set(result.value.verbatim_by_observation.values()) == set(texts)
    assert validate_resolution(request, result) == result


@pytest.mark.parametrize(("text", "raw"), (
    ("FMNHINS 0012345", "FMNH INS 0012345"),
    ("FMNH INS 0012345", "FMNH-INS #0012345"),
))
def test_reader_catalogue_prefix_variations_settle_exact_digit_identity_without_rewriting_raw(text, raw):
    request = collection_request(retained(text, raw=raw))
    assert {row.observation_text for row in request.fragments} == {text, raw}
    result = collection_resolution(request, FieldKey.FMNH_INS_NUMBER)
    assert result.work_state == WorkState.RESOLVED
    assert result.value.parsed == result.value.normalized == "0012345"
    assert result.value.literal == text
    assert validate_resolution(request, result) == result


@pytest.mark.parametrize("suffix", (".6", "-6", "/6"))
def test_catalogue_fragment_does_not_clear_an_invalid_longer_numeric_assertion(suffix):
    text = "Catalog number: 0012345" + suffix
    request = collection_request(retained(text, claimed_key="fmnh_ins_number", claimed_literal="0012345"))
    result = collection_resolution(request, FieldKey.FMNH_INS_NUMBER)
    assert result.work_state == WorkState.WAITING_POLICY
    assert result.value.parsed is None and not result.evidence_ids


@pytest.mark.parametrize("raw_native_quote", (False, True))
def test_repeated_identical_assertions_keep_distinct_exact_source_spans(raw_native_quote):
    text = "Habitat: oak woodland\nHabitat: oak woodland"
    field = (FieldSpec("country", text, shape="reading", readers=(1,)) if raw_native_quote
        else FieldSpec("country", text))
    built = build((RegionSpec(text),), (field,))
    request = collection_request(built)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED and result.value.parsed == "oak woodland"
    assert len(result.assembly_ids) == 2
    parts = [row for row in request.fragments if any(row.id in assembly.fragment_ids
        for assembly in request.assemblies if assembly.id in result.assembly_ids)]
    assert len(parts) == len({row.id for row in parts}) == len({(row.start, row.end) for row in parts}) == 2
    assert all(row.observation_text[row.start:row.end] == "oak woodland" for row in parts)
    if raw_native_quote:
        assert {row.input_source for row in parts} == {"raw_reading"}
    assert validate_resolution(request, result) == result


def test_conflicting_complete_labels_cannot_be_hidden_by_selecting_one_event():
    built = build((RegionSpec("habitat: oak woodland"), RegionSpec("habitat: wet grassland")), keyed=True)
    request = collection_request(built)
    assemblies = [row for row in request.assemblies if row.field_key == FieldKey.HABITAT]
    assert len(assemblies) == 2 and len({row.event_id for row in assemblies}) == 2
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY
    first = assemblies[0]
    fragment = next(row for row in request.fragments if row.id in first.fragment_ids)
    forged = FieldResolution(field_key=FieldKey.HABITAT, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal=first.interpreted_text,
            parsed=first.interpreted_text, normalized=first.interpreted_text,
            evidence_ids=list(first.evidence_ids), evidence_relations=dict.fromkeys(first.evidence_ids, "supports"),
            verbatim_by_observation={fragment.observation_id: fragment.observation_text},
            settled_observation_ids=[fragment.observation_id]), evidence_ids=first.evidence_ids,
        assembly_ids=(first.id,), event_id=first.event_id, reason="Selected only the first independent label")
    with pytest.raises(EvidenceError):
        validate_resolution(request, forged)


def test_raw_conflict_on_second_qualified_label_is_not_hidden_by_first_label_agreement():
    built = build((RegionSpec("habitat: oak woodland"),
        RegionSpec("habitat: oak woodland", raw="habitat: wet grassland")), keyed=True)
    request = collection_request(undecided(built, regions={1}))
    assert any(row.field_key == FieldKey.HABITAT for row in request.assemblies)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY
    assert result.value.parsed is None and not result.evidence_ids


@pytest.mark.parametrize(("text", "raw", "key"), (
    ("habitat: oak woodland", "habitat: oak woodland margin", FieldKey.HABITAT),
    ("habitat: beneath fallen log", "collection_method: beneath fallen log", FieldKey.HABITAT),
    ("collection_method: light trap", "habitat: light trap", FieldKey.COLLECTION_METHOD),
    ("fmnh_ins_number: FMNH INS 0012345", "fmnh_ins_number: FMNH INS 00123456", FieldKey.FMNH_INS_NUMBER),
))
@pytest.mark.parametrize("stale_graph", (None, "withdrawn_event", "accepted_event"))
def test_withdrawn_decision_cannot_settle_conflicting_readers_with_stale_graph(text, raw, key, stale_graph):
    built = build((RegionSpec(text, raw=raw),), keyed=True)
    selected = collection_request(built)
    assert any(row.field_key == key for row in selected.assemblies)
    assert collection_resolution(selected, key).work_state == WorkState.RESOLVED

    request = collection_request(undecided(built))
    assert not any(row.field_key == key for row in request.assemblies)
    originals = {row.observation_text for row in request.fragments}
    assert {text, raw} <= originals
    if stale_graph is not None:
        # Deliberately inconsistent input: the ordinary factory withdrew this
        # accepted assembly when its native reading decision was withdrawn.
        request = request.model_copy(update={"assemblies": selected.assemblies})
        assert any(row.field_key == key for row in request.assemblies)
        if stale_graph == "withdrawn_event":
            with pytest.raises(EvidenceError, match="Proposed/unknown event"):
                collection_resolution(request, key)
            return
        request = request.model_copy(update={"events": selected.events})
    result = collection_resolution(request, key)
    assert result.work_state == WorkState.WAITING_POLICY
    assert result.value.parsed is None and result.question is None
    assert not result.evidence_ids and not result.assembly_ids


@pytest.mark.parametrize("work_state", (WorkState.WAITING_POLICY, WorkState.WAITING_SOURCE, WorkState.OPERATIONAL_FAILED))
def test_supported_present_evidence_cannot_stop_as_unreasoned_model_hold(work_state):
    request = collection_request(retained("Habitat: oak woodland"))
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.RESOLVED
    held = FieldResolution(field_key=FieldKey.HABITAT, work_state=work_state,
        value=FieldValue(state=ValueState.UNRESOLVED), reason="missing_policy:unstructured_label_event_unqualified")
    with pytest.raises(EvidenceError):
        validate_resolution(request, held)


def test_altered_final_value_is_rejected_after_source_recovery():
    request = collection_request(retained("Habitat: oak woodland"))
    result = collection_resolution(request, FieldKey.HABITAT)
    forged = result.model_copy(update={"value": result.value.model_copy(update={
        "parsed": "wet grassland", "normalized": "wet grassland"})})
    with pytest.raises(EvidenceError):
        validate_resolution(request, forged)


def test_dts_definition_hold_keeps_verbatim_without_inventing_date_time_site_semantics():
    request = collection_request(retained("D/T/S: 12 June 1948, 9am, oak woodland"))
    value = "12 June 1948, 9am, oak woodland"
    held = dts_policy_resolution(value)
    assert validate_resolution(request, held) == held
    assert held.work_state == WorkState.WAITING_POLICY
    assert held.reason == "missing_policy:verbatim_dts_definition_examples"
    assert held.value.literal == value and held.value.parsed is None and held.value.normalized is None
    with pytest.raises(EvidenceError):
        collection_resolution(request, FieldKey.VERBATIM_DTS)
    with pytest.raises(EvidenceError, match="grounded"):
        validate_resolution(request, dts_policy_resolution("invented D/T/S"))


def continuation_request(*, status="accepted", event_kind=EventKind.COLLECTING,
                         second_text="woodland margin", second_literal=None):
    built = build((RegionSpec("Habitat: oak"), RegionSpec(second_text)),
        (FieldSpec("country", "Habitat: oak", regions=(0,)),
         FieldSpec("city", second_text, regions=(1,))))
    request = collection_request(built)
    first = next(row for row in request.fragments if row.observation_id == built.first_reading[0].id)
    first_data = first.model_dump(mode="json")
    first_data.update(id="continuation-first", start=len("Habitat: "), end=len("Habitat: oak"),
        literal="oak", granularity="span")
    first = SourceFragment.model_validate(first_data)
    second = next(row for row in request.fragments if row.observation_id == built.first_reading[1].id)
    if second_literal:
        second_data = second.model_dump(mode="json")
        start = second_text.index(second_literal)
        second_data.update(id="continuation-second", start=start, end=start + len(second_literal),
            literal=second_literal, granularity="span")
        second = SourceFragment.model_validate(second_data)
    event = EventHypothesis(id="continuation-event", scope=request.scope, kind=event_kind,
        fragment_ids=(first.id, second.id), evidence_ids=tuple(row.id for row in request.evidence),
        reason="Explicit fixture event attribution", status="accepted", validator_version="fixture-event/v1")
    relation = FragmentRelation(id="continuation-relation", scope=request.scope,
        fragment_ids=(first.id, second.id), kind=RelationKind.CONTINUATION, event_id=event.id,
        evidence_ids=event.evidence_ids, reason="Explicit fixture cross-label continuation",
        proposer_version="fixture/v1", validator_version="fixture/v1" if status == "accepted" else None,
        status=status)
    return request, first, second, event, relation


def test_only_an_accepted_continuation_can_join_two_label_assertion_parts():
    request, first, second, event, relation = continuation_request()
    assembly = assemble_field(assembly_id="continued-habitat", scope=request.scope, field_key=FieldKey.HABITAT,
        fragments=(first, second), event=event, relations=(relation,), assertion_kind="complementary")
    data = request.model_dump(mode="json")
    data.update(fragments=[row.model_dump(mode="json") for row in (*request.fragments, first)],
        events=[event.model_dump(mode="json")], relations=[relation.model_dump(mode="json")],
        assemblies=[assembly.model_dump(mode="json")], organiser_candidates=[])
    request = SpecialistRequest.model_validate(data)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED and result.value.parsed == "oak woodland margin"
    assert set(result.value.verbatim_by_observation.values()) == {"Habitat: oak", "woodland margin"}
    assert validate_resolution(request, result) == result


def test_accepted_continuation_does_not_override_later_fragment_marked_as_locality():
    request, first, second, event, relation = continuation_request(
        second_text="Locality: woodland margin", second_literal="woodland margin")
    assembly = assemble_field(assembly_id="wrong-kind-habitat", scope=request.scope, field_key=FieldKey.HABITAT,
        fragments=(first, second), event=event, relations=(relation,), assertion_kind="complementary")
    data = request.model_dump(mode="json")
    data.update(fragments=[row.model_dump(mode="json") for row in (*request.fragments, first, second)],
        events=[event.model_dump(mode="json")], relations=[relation.model_dump(mode="json")],
        assemblies=[assembly.model_dump(mode="json")], organiser_candidates=[])
    result = collection_resolution(SpecialistRequest.model_validate(data), FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY
    assert result.value.parsed is None and not result.evidence_ids


@pytest.mark.parametrize("kind", ("missing", "proposed", "different_event"))
def test_cross_label_continuation_is_never_inferred_from_adjacent_text(kind):
    request, first, second, event, relation = continuation_request(status="proposed" if kind == "proposed" else "accepted")
    relations = () if kind == "missing" else (relation,)
    if kind == "different_event":
        relations = (relation.model_copy(update={"event_id": "another-event"}),)
    with pytest.raises(EvidenceError, match="continuation"):
        assemble_field(assembly_id="unsupported-join", scope=request.scope, field_key=FieldKey.HABITAT,
            fragments=(first, second), event=event, relations=relations, assertion_kind="complementary")


def test_preparation_event_does_not_authorize_collecting_method():
    request = collection_request(retained("Collection method: light trap"))
    data = request.model_dump(mode="json")
    data["events"] = [dict(row, kind="preparation") for row in data["events"]]
    request = SpecialistRequest.model_validate(data)
    assert collection_resolution(request, FieldKey.COLLECTION_METHOD).work_state == WorkState.WAITING_POLICY


@pytest.mark.parametrize(("key", "text", "expected"), (
    (FieldKey.FMNH_INS_NUMBER, "FMNH INS 0012345", "0012345"),
    (FieldKey.HABITAT, "Habitat: oak woodland", "oak woodland"),
    (FieldKey.COLLECTION_METHOD, "Collection method: light trap", "light trap"),
    (FieldKey.COLLECTION_CODE, "Collection code: INSECTS", "INSECTS"),
))
def test_scoped_collection_utility_returns_one_exact_replayable_resolution(key, text, expected):
    request = collection_request(retained(text))
    result = invoke(request, "settle_collection", {"field_key": str(key)})
    payload = json.loads(result.candidate_json[0])
    assert set(payload) == {"resolutions"} and len(payload["resolutions"]) == 1
    resolution = FieldResolution.model_validate(payload["resolutions"][0])
    assert resolution == collection_resolution(request, key)
    assert resolution.value.parsed == expected and resolution.reason == COLLECTION_RULE
    assert result.receipt is None and not result.evidence
    proof = verify_local_utility_v2(request, result)
    assert proof.field_key == str(key) and proof.arguments == {"field_key": str(key)}


def test_narrowed_reloaded_request_keeps_other_collection_evidence_without_reprocessing_siblings():
    request = collection_request(retained("FMNH INS 0012345\nHabitat: oak woodland\nCollection method: light trap"))
    data = request.model_dump(mode="json")
    data.update(field_keys=["habitat"], field_revisions={"habitat": 3})
    restored = SpecialistRequest.model_validate_json(json.dumps(data))
    first = invoke(restored, "settle_collection", {"field_key": "habitat"})
    second = invoke(restored, "settle_collection", {"field_key": "habitat"})
    assert second == first and second.receipt is None
    payload = json.loads(second.candidate_json[0])
    assert [row["field_key"] for row in payload["resolutions"]] == ["habitat"]
    assert restored.field_revisions == {FieldKey.HABITAT: 3}
    assert {row.field_key for row in restored.assemblies} == {
        FieldKey.FMNH_INS_NUMBER, FieldKey.HABITAT, FieldKey.COLLECTION_METHOD}
    assert verify_local_utility_v2(restored, second).arguments == {"field_key": "habitat"}
    with pytest.raises((UtilityInputError, EvidenceError)):
        invoke(restored, "settle_collection", {"field_key": "collection_method"})


@pytest.mark.parametrize("wrong_key", ("collection_code", "habitat", "collection_method"))
def test_catalogue_utility_cannot_borrow_catalogue_assembly_for_another_owned_field(wrong_key):
    request = collection_request(retained("FMNH INS 0012345", claimed_key="fmnh_ins_number"))
    with pytest.raises((UtilityInputError, EvidenceError)):
        invoke(request, "catalog_number", {"text": "FMNH INS 0012345", "field_key": wrong_key})


@pytest.mark.parametrize("arguments", (
    {"field_key": "collectors"}, {"field_key": "verbatim_dts"},
    {"field_key": "habitat", "text": "oak woodland"},
))
def test_collection_settlement_rejects_foreign_fields_definition_hold_and_untyped_arguments(arguments):
    request = collection_request(retained("Habitat: oak woodland"))
    with pytest.raises((UtilityInputError, EvidenceError)):
        invoke(request, "settle_collection", arguments)
