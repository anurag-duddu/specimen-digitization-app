"""Exact occurrence/native quote custody and collector role boundaries, offline."""

import hashlib

import pytest

from specimen_digitization.application.domain import Evidence
from specimen_digitization.application.organiser import CandidateLocation, SOURCE, format_locator
from specimen_digitization.research_harness.collection import collection_resolution, recover_collection_graph
from specimen_digitization.research_harness.contracts import (
    EvidenceItem, FieldKey, ROLE_FIELDS, ResearchScope, SourceFragment, SpecialistRequest,
    SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.prompts import resolve_prompt


TEXT = "Locality: forest\nHabitat: forest"


def recover(text=TEXT, *, shape="modern", quote="forest", occurrence="habitat", source=None, edit=None,
            raw=None, decided="a", unreadable=(), region="region", scope=None):
    scope = scope or ResearchScope(organization_id="org", collection_id="insects", specimen_id="fixture",
        job_id="fixture", generation=1, input_digest=digest(text), profile_digest=digest("profile"), sensitive=False)
    fragments = [SourceFragment(id="original:" + observation, scope=scope,
        asset_id="asset", asset_generation="1", asset_digest=digest("asset"),
        label_id=region, region_id=region, observation_id=observation, reader=reader,
        model_id="fixture", prompt_digest=digest("reader"), observation_text=reading,
        observation_digest=hashlib.sha256(reading.encode()).hexdigest(), start=0, end=len(reading), literal=reading,
        order=0, granularity="label", unreadable=short in unreadable,
        input_source="decided_transcript" if decided in {short, "both"} else "raw_reading")
        for short, observation, reader, reading in (("a", "a" if region == "region" else region + ":a", "qwen", text),
            ("b", "b" if region == "region" else region + ":b", "muse", text if raw is None else raw))]
    quote = text if quote is None else quote
    start = text.rfind(quote) if occurrence == "habitat" else text.find(quote)
    if shape == "modern":
        locator = format_locator(CandidateLocation("1A", fragments[0].observation_id, start,
            start + len(quote), start, start + len(quote)))
        observations = [fragments[0].observation_id]
    else:
        locator, observations = "region:" + region, [item.observation_id for item in fragments]
    row = Evidence(kind="literal", asset_id="asset", region_id=region, observation_ids=observations,
        source=source or SOURCE, locator=locator, excerpt=quote, raw_ref="offline-fixture", digest=digest(quote))
    row = edit(row) if edit else row
    events, assemblies = [], []
    recover_collection_graph(scope, fragments, events, assemblies, native_rows=(row,))
    role = SpecialistRole.COLLECTION
    evidence = EvidenceItem(id=row.id, kind=row.kind, source_id=row.source, locator=row.locator or "",
        response_digest=digest(row), source_version="native-evidence-adapter/v1",
        publisher_assertion_id=digest(row), excerpt=row.excerpt)
    request = SpecialistRequest(scope=scope, role=role, field_keys=ROLE_FIELDS[role],
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest, source_registry_digest=digest("registry"),
            toolset_digest=digest("tools"), model_route="harness-deepseek", output_schema_digest=digest("schema")),
        fragments=tuple(fragments), events=tuple(events), assemblies=tuple(assemblies), evidence=(evidence,),
        field_revisions={key: 0 for key in ROLE_FIELDS[role]})
    return request, row


@pytest.mark.parametrize("shape", ("modern", "legacy"))
def test_wrong_identical_literal_occurrence_does_not_supply_habitat_quote(shape):
    request, row = recover(shape=shape, quote="forest" if shape == "modern" else "Locality: forest",
        occurrence="locality")
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY
    assert not result.evidence_ids and not result.assembly_ids


def test_precise_modern_locator_can_disambiguate_identical_quote_text():
    request, row = recover()
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED and result.value.parsed == "forest"
    assert result.evidence_ids == (row.id,)
    span = next(item for item in request.fragments if item.id == request.assemblies[0].fragment_ids[0])
    assert span.start == TEXT.rfind("forest")


@pytest.mark.parametrize("quote", ("Habitat: forest", None))
def test_unique_legacy_quote_containing_the_exact_span_remains_admitted(quote):
    request, row = recover(shape="legacy", quote=quote)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED and result.value.parsed == "forest"
    assert result.evidence_ids == (row.id,)


def test_legacy_repeated_bare_quote_has_no_exact_occurrence_authority():
    request, _ = recover(shape="legacy", quote="forest")
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY


@pytest.mark.parametrize(("shape", "source", "allowed"), (
    ("modern", SOURCE, True), ("modern", "label", False),
    ("modern", "public_biography", False), ("modern", "memory", False),
    ("legacy", SOURCE, True), ("legacy", "label", True),
    ("legacy", "public_biography", False), ("legacy", "memory", False),
))
def test_only_existing_native_source_routes_supply_recovered_evidence(shape, source, allowed):
    request, _ = recover(shape=shape, quote="Habitat: forest", source=source)
    outcome = collection_resolution(request, FieldKey.HABITAT)
    assert (outcome.work_state == WorkState.RESOLVED) is allowed


@pytest.mark.parametrize("marker", ("leg.", "Leg.", "LEG."))
def test_empty_habitat_header_cannot_consume_a_collector_role_line(marker):
    text = f"Habitat:\n{marker} A. Smith\nMethod: light trap"
    request, _ = recover(text, shape="legacy", quote=None)
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY
    method = collection_resolution(request, FieldKey.COLLECTION_METHOD)
    assert method.work_state == WorkState.RESOLVED and method.value.parsed == "light trap"


def test_indented_collector_line_ends_a_valid_habitat_continuation():
    request, _ = recover("Habitat: forest\n  leg. A. Smith", shape="legacy", quote=None)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED and result.value.parsed == "forest"


def test_inline_collector_notation_is_not_habitat():
    request, _ = recover("Habitat: leg. A. Smith", shape="legacy", quote=None)
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY


@pytest.mark.parametrize("mutation", ("locator_reader", "row_reader", "extra_reader", "duplicate_reader", "bounds"))
def test_modern_capture_cannot_rebind_the_exact_quote_to_another_reading_or_extent(mutation):
    start = TEXT.rfind("forest")
    def corrupt(row):
        updates = {
            "locator_reader": {"locator": format_locator(CandidateLocation("1A", "foreign", start, len(TEXT), start, len(TEXT)))},
            "row_reader": {"observation_ids": ["foreign"]},
            "extra_reader": {"observation_ids": ["a", "b"]},
            "duplicate_reader": {"observation_ids": ["a", "a"]},
            "bounds": {"locator": format_locator(CandidateLocation("1A", "a", start, len(TEXT) + 40, start, len(TEXT)))},
        }[mutation]
        return row.model_copy(update=updates)
    request, _ = recover(edit=corrupt)
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY


def test_exact_modern_quote_for_only_the_other_raw_reader_remains_usable():
    start = TEXT.rfind("forest")
    def raw_row(row):
        return row.model_copy(update={"observation_ids": ["b"],
            "locator": format_locator(CandidateLocation("1B", "b", start, len(TEXT), start, len(TEXT)))})
    request, row = recover(edit=raw_row)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.RESOLVED
    assert result.evidence_ids == (row.id,)
    assert result.value.input_source_by_observation == {"b": "raw_reading"}


@pytest.mark.parametrize(("key", "text", "raw", "expected"), (
    (FieldKey.HABITAT, "Habitat: forest", "Habitat: meadow", "forest"),
    (FieldKey.HABITAT, "Habitat: forest", "Locality: forest", "forest"),
    (FieldKey.COLLECTION_METHOD, "Method: light trap", "Method: sweep net", "light trap"),
))
def test_exact_decided_literal_settles_without_discarding_a_misread_raw_peer(key, text, raw, expected):
    request, row = recover(text, raw=raw, quote=None)
    before = request.model_dump_json()
    result = collection_resolution(request, key)
    assert result.work_state == WorkState.RESOLVED and result.value.parsed == expected
    assert result.evidence_ids == (row.id,)
    assert result.value.input_source_by_observation == {"a": "decided_transcript"}
    assert {item.observation_text for item in request.fragments} == {text, raw}
    assert request.model_dump_json() == before


def test_unreadable_unselected_peer_does_not_override_a_valid_decided_quote():
    request, _ = recover("Habitat: forest", raw="Habitat: garbled", quote=None, unreadable=("b",))
    assert collection_resolution(request, FieldKey.HABITAT).value.parsed == "forest"


@pytest.mark.parametrize(("text", "raw", "unreadable"), (
    ("Habitat: forest", "Habitat: forest", ("a",)),
    ("Habitat: light trap", "Habitat: forest", ()),
    ("Locality: forest", "Habitat: forest", ()),
))
def test_invalid_or_role_wrong_decided_reading_cannot_be_replaced_by_its_raw_peer(text, raw, unreadable):
    request, _ = recover(text, raw=raw, quote=None, unreadable=unreadable)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY and result.value.parsed is None


def test_disagreeing_readers_without_a_decision_remain_unresolved():
    request, _ = recover("Habitat: forest", raw="Habitat: meadow", quote=None, decided=None)
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY


def test_two_selected_readings_do_not_create_deciding_authority():
    request, _ = recover("Habitat: forest", quote=None, decided="both")
    assert collection_resolution(request, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY


def test_decisions_are_label_local_and_do_not_erase_a_cross_label_conflict():
    first, _ = recover("Habitat: forest", quote=None)
    other, _ = recover("Habitat: meadow", quote=None, region="other", scope=first.scope)
    combined = first.model_copy(update={name: (*getattr(first, name), *getattr(other, name))
        for name in ("fragments", "events", "assemblies", "evidence")})
    assert collection_resolution(combined, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY


def test_an_independent_decided_label_without_a_qualified_quote_is_not_dropped():
    first, _ = recover("Habitat: forest", quote=None)
    other, _ = recover("Habitat: meadow", quote=None, source="public_biography",
        region="other", scope=first.scope)
    assert not other.assemblies
    combined = first.model_copy(update={name: (*getattr(first, name), *getattr(other, name))
        for name in ("fragments", "events", "assemblies", "evidence")})
    assert collection_resolution(combined, FieldKey.HABITAT).work_state == WorkState.WAITING_POLICY


def test_a_quote_for_a_conflicting_raw_peer_cannot_substitute_for_missing_decided_evidence():
    raw = "Habitat: meadow"
    start = raw.index("meadow")
    def raw_quote(row):
        return row.model_copy(update={"observation_ids": ["b"], "excerpt": "meadow",
            "locator": format_locator(CandidateLocation("1B", "b", start, len(raw), start, len(raw)))})
    request, _ = recover("Habitat: forest", raw=raw, quote=None, edit=raw_quote)
    result = collection_resolution(request, FieldKey.HABITAT)
    assert result.work_state == WorkState.WAITING_POLICY and not result.evidence_ids
