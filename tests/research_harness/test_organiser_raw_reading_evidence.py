"""Evidence quoted from a RAW reading (either reader, any label), not only from the decided transcript.

The hand-over (#265) places an extractor value only in the decided reading. After the organiser (#262) the
stored rows quote ONE named reading each, and on four of the nine recorded specimens (1, 4, 6, 9) the decided
label holds 15 characters while nearly every field sits on a label the first pass never decided. What these
tests pin, with the real ordinary rule (``harness.apply_candidates``), the real graph builder
(``initial_requests._build_graph``), the real contracts and the real validator (``evidence.validate_resolution``,
unchanged), on abstract synthetic labels:

- a literal several readers state identically on a label with no decided transcript becomes ONE accepted event
  and assembly on the first reader's span, and the other readers' rows are cited by that event as evidence;
- when the readers differ, or one of them is silent, the field has no value (the organiser rule, G19/G27/G32)
  and trusted code builds NO assembly: every reader's row is a located candidate with its own span and quote,
  and the validator refuses a resolution that names none;
- the span is a verbatim substring of ONE line of the reading the row names, found by trusted code in that
  reading only (never in the other reader's, never in another label's), and the contract re-reads it;
- an ungrounded hint is never a value; the decided transcript stays the value of a decided label.

``SpecialistRequest`` is the real contract; the extraction is the real ``apply_candidates`` fed scripted
candidates (not a model). Date and elevation settlements use evidence.py's deterministic validators.
"""
from __future__ import annotations

import unicodedata
import asyncio
import json
from dataclasses import dataclass

import pytest

from specimen_digitization.application import field_resolution
from specimen_digitization.application.domain import (
    Asset, FieldValue, Observation, ReaderHandoff, Region, Run, Scope, Specimen, Transcript, ValueState,
)
from specimen_digitization.application.field_harness import labelled
from specimen_digitization.application.harness import ExtractionCandidate, ExtractionOutput, apply_candidates
from specimen_digitization.application.organiser import extraction_readings
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, EventKind, FieldKey, FieldResolution, ResearchScope, SpecialistRequest, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, elevation_resolutions, settle_elevation, temporal_resolutions,
    validate_assembly, validate_resolution,
)
from specimen_digitization.research_harness.initial_requests import (
    ASSEMBLY_FIELDS, ELEVATION_FIELDS, ORGANISER_RULE, NativeGenerationRequestFactory,
)
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry
from specimen_digitization.research_harness.compatibility import PublicationUnavailable


@dataclass
class Label:
    a: str                      # reader A's text
    b: str | None = None        # reader B's text; default: the same
    decided: str | None = None  # "a", "b" or None: which reading the first pass selected (None: undecided)
    unreadable: tuple = ()      # unreadable spans reader A's reading carries


@dataclass
class Built:
    specimen: Specimen
    scope: ResearchScope
    graph: tuple
    names: dict                 # "1A" ... -> organiser Reading
    readings: dict              # label name -> Observation


def build(labels, answers=(), *, keyed=False):
    """A specimen of ``labels`` and the organiser's stored rows for ``answers``.

    ``answers`` are (field_key, reading name such as "1A", literal, quote) tuples: what a scripted extraction
    call returns. Names follow the organiser's own order (a decided reading first, then the others)."""
    asset = Asset(sha256="a" * 64, blob_ref="a" * 64 + ":1", media_type="image/jpeg", size_bytes=10, width=100,
        height=100, filename="fixture.jpeg", uploader="fixture", sensitive=False)
    regions, observations, transcripts = [], [], []
    for index, label in enumerate(labels):
        region = Region(asset_id=asset.id, x=0, y=0, width=100, height=100, order=index, method="fixture", version="fixture")
        second = label.b if label.b is not None else label.a
        first_reading = Observation(region_id=region.id, route_id="handwriting-qwen", model_id="fixture-model-a",
            provider="fixture", prompt_version="b" * 64, input_sha256="c" * 64, input_asset_id=asset.id,
            literal_text=label.a, raw_ref="fixture-response", raw_sha256="d" * 64, unreadable_spans=list(label.unreadable))
        second_reading = Observation(region_id=region.id, route_id="handwriting-muse", model_id="fixture-model-b",
            provider="fixture", prompt_version="b" * 64, input_sha256="c" * 64, input_asset_id=asset.id,
            literal_text=second, raw_ref="fixture-response", raw_sha256="d" * 64)
        chosen = {"a": first_reading, "b": second_reading, None: None}[label.decided]
        roles = {first_reading.id: "raw_reading", second_reading.id: "raw_reading"}
        if chosen is not None:
            roles[chosen.id] = "decided_transcript"
        transcripts.append(Transcript(region_id=region.id, text=chosen.literal_text if chosen else None,
            observation_ids=[first_reading.id, second_reading.id], alternatives=sorted({label.a, second}),
            resolved=chosen is not None, decision_kind="first_pass",
            selected_observation_id=chosen.id if chosen else None,
            handoffs=[ReaderHandoff(observation_id=item.id, role=roles[item.id], handed_text=item.literal_text)
                for item in (first_reading, second_reading)]))
        regions.append(region)
        observations += [first_reading, second_reading]
    run = Run(regions=regions, observations=observations, transcripts=transcripts)
    run.fields = {str(key): FieldValue() for key in FieldKey}
    specimen = Specimen(scope=Scope(organization_id="org", collection_id="collection"), asset=asset, run=run)
    if keyed:
        from specimen_digitization.application.workflow import Workflow
        Workflow.parse(run, asset.id)
    names = labelled(extraction_readings(run))
    candidates = [ExtractionCandidate(field_key=key, reading=name, literal=literal, source_excerpt=quote)
        for key, name, literal, quote in answers]
    apply_candidates(run, asset.id, ExtractionOutput(candidates=candidates), "fixture-response", "d" * 64)
    scope = ResearchScope(organization_id="org", collection_id="collection", specimen_id=specimen.id,
        job_id="opaque-fixture-job", generation=1, input_digest="e" * 64, profile_digest="f" * 64, sensitive=False)
    by_id = {item.id: item for item in observations}
    return Built(specimen, scope, NativeGenerationRequestFactory._build_graph(specimen, scope), names,
        {name: by_id[reading.observation_id] for name, reading in names.items()})


def candidates(built, key=None):
    found = built.graph[5]
    return [item for item in found if key is None or item.field_key == FieldKey(key)]


def request_for(built, role, **changes):
    fragments, events, assemblies, evidence, decisions, found = built.graph
    keys = ROLE_FIELDS[role]
    prompt = resolve_prompt(role, profile_digest=built.scope.profile_digest, source_registry_digest="a" * 64,
        toolset_digest="b" * 64, model_route="harness-deepseek", output_schema_digest="c" * 64)
    return SpecialistRequest(**{**dict(scope=built.scope, role=role, field_keys=keys, prompt=prompt, fragments=fragments,
        events=events, assemblies=assemblies, evidence=evidence, accepted_decisions=decisions,
        organiser_candidates=tuple(item for item in found if item.field_key in keys),
        field_revisions={key: 0 for key in keys}), **changes})


def resolution_from(request, candidate, text=None):
    """What a specialist that follows the hand-over block returns for a grounded candidate."""
    assembly = next(item for item in request.assemblies if item.id == candidate.assembly_id)
    fragment = next(item for item in request.fragments if item.id == candidate.fragment_id)
    written = text if text is not None else assembly.interpreted_text
    return FieldResolution(field_key=candidate.field_key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal=written, parsed=written, normalized=written,
            evidence_ids=list(assembly.evidence_ids), evidence_relations=dict.fromkeys(assembly.evidence_ids, "supports"),
            verbatim_by_observation={fragment.observation_id: fragment.observation_text},
            settled_observation_ids=[fragment.observation_id]),
        evidence_ids=assembly.evidence_ids, assembly_ids=(assembly.id,), event_id=assembly.event_id,
        reason="The readings support the extractor's value")


# A decided 15-character label and an undecided one: the shape of specimens 1, 4, 6 and 9.
SHORT = "FMNH INS 99999"
BODY = "Synthetic Collector\noak woodland margin\nlight trap"


def two_labels(a=BODY, b=None, **extra):
    return (Label(SHORT, decided="a"), Label(a, b, **extra))


# ---------------------------------------------------------------------------- agreeing readers, no decided label
def test_a_literal_both_readers_state_on_an_undecided_label_is_one_accepted_assembly_with_both_readers_evidence():
    quote = "Synthetic Collector"
    built = build(two_labels(), [("collectors", "2A", "Synthetic Collector", quote),
                                 ("collectors", "2B", "Synthetic Collector", quote)])
    fields = built.specimen.run.fields
    assert fields["collectors"].state == "supported" and fields["collectors"].literal == "Synthetic Collector"
    fragments, events, assemblies, evidence, _, found = built.graph
    grounded = [item for item in found if item.status == "grounded"]
    located = [item for item in found if item.status == "located"]
    assert len(grounded) == 1 and len(located) == 1
    [item], [other] = grounded, located
    # The first reader's reading carries the assembly; the second reader's row is evidence for the same event.
    reader_a, reader_b = built.readings["2A"], built.readings["2B"]
    assert (item.observation_id, other.observation_id) == (reader_a.id, reader_b.id)
    assert item.region_id == other.region_id == reader_a.region_id != built.readings["1A"].region_id
    fragment = next(row for row in fragments if row.id == item.fragment_id)
    assert fragment.input_source == "raw_reading" and fragment.granularity == "span"
    assert fragment.observation_text[fragment.start:fragment.end] == "Synthetic Collector" == item.literal
    assert (fragment.reader, fragment.observation_id) == (reader_a.route_id, reader_a.id)
    event = next(row for row in events if row.id == item.event_id)
    assert event.status == "accepted" and event.validator_version == event.rule_version == ORGANISER_RULE
    assert event.kind == EventKind.COLLECTING and event.fragment_ids == (fragment.id,)
    assembly = next(row for row in assemblies if row.id == item.assembly_id)
    assert assembly.fragment_ids == (fragment.id,) and assembly.interpreted_text == "Synthetic Collector"
    assert len(event.evidence_ids) == 2 and item.evidence_ids == assembly.evidence_ids == event.evidence_ids
    assert other.reason == "states_the_literal_the_grounded_reading_states" and other.evidence_ids[0] in event.evidence_ids
    assert reader_b.literal_text[other.start:other.end] == "Synthetic Collector"
    assert {row.id for row in evidence} >= set(event.evidence_ids)
    # The real validator accepts the value equal to the assembly, and refuses any other and any without one.
    request = request_for(built, SpecialistRole.PARTIES)
    resolution = resolution_from(request, item)
    assert validate_resolution(request, resolution) == resolution
    validate_assembly(request, assembly)
    with pytest.raises(EvidenceError, match="differs from immutable assembly"):
        validate_resolution(request, resolution_from(request, item, text="Synthetic Collecter"))
    with pytest.raises(EvidenceError, match="lacks qualified deciding authority"):
        validate_resolution(request, resolution.model_copy(update={"assembly_ids": (), "event_id": None}))


def test_the_decided_label_alone_still_grounds_exactly_as_before_and_names_the_decided_reading():
    built = build((Label(BODY, decided="a"),), [("collectors", "1A", "Synthetic Collector", "Synthetic Collector")])
    [item] = candidates(built, "collectors")
    assert item.status == "grounded" and item.observation_id == built.readings["1A"].id
    fragment = next(row for row in built.graph[0] if row.id == item.fragment_id)
    assert fragment.input_source == "decided_transcript"


# ---------------------------------------------------------------------------- the readers disagree or one is silent
@pytest.mark.parametrize(("label", "answers", "reason"), (
    ("the readers differ", [("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
                            ("collectors", "2B", "Synthetic Collecter", "Synthetic Collecter")],
     "readings_differ_no_value_chosen"),
    ("one reader is silent", [("collectors", "2A", "Synthetic Collector", "Synthetic Collector")],
     "readings_differ_no_value_chosen"),
))
def test_when_the_readers_differ_or_one_is_silent_no_value_is_chosen_and_no_assembly_exists(label, answers, reason):
    built = build(two_labels(b=BODY.replace("Collector", "Collecter")), answers)
    fields = built.specimen.run.fields
    assert fields["collectors"].state == "ambiguous" and fields["collectors"].literal is None, label
    fragments, events, assemblies, _, _, found = built.graph
    assert assemblies == () and not [row for row in events if row.status == "accepted"], label
    assert found and {item.status for item in found} == {"located"} and {item.reason for item in found} == {reason}
    # Every reader's row is carried with its own span, quote and native row.
    for item in found:
        reading = next(row for row in built.readings.values() if row.id == item.observation_id)
        assert reading.literal_text[item.start:item.end] == item.literal and len(item.evidence_ids) == 1
    request = request_for(built, SpecialistRole.PARTIES)
    forged = FieldResolution(field_key=FieldKey.COLLECTORS, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="Synthetic Collector", parsed="Synthetic Collector",
            normalized="Synthetic Collector"), evidence_ids=("e",), assembly_ids=("assembly:invented",),
        event_id="event:invented", reason="the first reader wrote it")
    with pytest.raises(EvidenceError, match="Unknown literal assembly"):
        validate_resolution(request, forged)
    with pytest.raises(EvidenceError, match="lacks qualified deciding authority"):
        validate_resolution(request, forged.model_copy(update={"assembly_ids": (), "event_id": None}))


def test_a_reader_that_stated_a_different_literal_blocks_the_assembly_even_if_the_first_reader_agrees_with_a_third():
    """Three labels: the first two undecided labels' readers agree on one literal, the third label (decided) differs.
    Across labels that differ the field is ambiguous and nothing is grounded."""
    labels = (Label("Synthetic Collector", decided=None), Label("Other Person", decided="a"))
    built = build(labels, [("collectors", "1A", "Synthetic Collector", "Synthetic Collector"),
                           ("collectors", "1B", "Synthetic Collector", "Synthetic Collector"),
                           ("collectors", "2A", "Other Person", "Other Person")])
    assert built.specimen.run.fields["collectors"].state == "ambiguous"
    assert built.graph[2] == () and {item.status for item in candidates(built)} == {"located"}


@pytest.mark.parametrize("answers", (
    [("collectors", "2A", "Synthetic Collector", "Synthetic Collector")],                                  # reader B silent
    [("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
     ("collectors", "2B", "Synthetic Collecter", "Synthetic Collecter")],                                  # readers differ
))
def test_the_assembly_does_not_trust_the_stored_field_state_alone(answers):
    """The stored field is SUPPORTED here on purpose (a stale or edited state): trusted code re-derives from the rows that
    every reading of the undecided label states the literal, finds it does not, and builds no assembly."""
    built = build(two_labels(b=BODY.replace("Collector", "Collecter")), answers)
    run = built.specimen.run
    assert run.fields["collectors"].state == "ambiguous"
    run.fields["collectors"] = FieldValue(state=ValueState.SUPPORTED, literal="Synthetic Collector",
        parsed="Synthetic Collector", evidence_ids=list(run.fields["collectors"].evidence_ids))
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert graph[2] == () and not [row for row in graph[1] if row.status == "accepted"]
    found = [item for item in graph[5] if item.field_key == FieldKey.COLLECTORS]
    assert {item.status for item in found} == {"located"} and {item.reason for item in found} == {
        "not_every_reading_of_the_label_states_it"}


def test_the_decided_labels_own_rows_must_state_the_literal_alone_even_if_the_stored_state_says_supported():
    """Two different literals in the ONE decided reading are no value (the organiser rule); with a stale SUPPORTED state the
    re-derivation still finds the decided reading does not state one literal alone, so no assembly is built."""
    text = "Synthetic Collector\nlight trap"
    built = build((Label(text, decided="a"),), [("collectors", "1A", "Synthetic Collector", "Synthetic Collector"),
                                                ("collectors", "1A", "light trap", "light trap")])
    run = built.specimen.run
    assert run.fields["collectors"].state == "ambiguous"
    run.fields["collectors"] = FieldValue(state=ValueState.SUPPORTED, literal="Synthetic Collector",
        parsed="Synthetic Collector", evidence_ids=list(run.fields["collectors"].evidence_ids))
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert graph[2] == ()
    assert {item.reason for item in graph[5] if item.field_key == FieldKey.COLLECTORS} == {"not_every_reading_of_the_label_states_it"}


def test_a_row_of_only_the_other_reader_of_a_decided_label_is_never_the_value_even_with_a_stale_supported_state():
    built = build((Label("Synthetic Collector\nlight trap", decided="a"),),
        [("collectors", "1B", "Synthetic Collector", "Synthetic Collector")])
    run = built.specimen.run
    run.fields["collectors"] = FieldValue(state=ValueState.SUPPORTED, literal="Synthetic Collector",
        parsed="Synthetic Collector", evidence_ids=list(run.fields["collectors"].evidence_ids))
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert graph[2] == ()
    assert {item.reason for item in graph[5]} == {"other_reader_of_a_decided_label_is_not_the_value"}


@pytest.mark.parametrize("tamper", ("asset", "region"))
def test_a_row_that_does_not_belong_to_the_reading_it_names_is_a_hint_and_blocks_an_assembly_it_could_have_shared(tamper):
    """The other reader's row of a decided label disagrees with the decided one; its native row is then made to name another
    asset or another label. Trusted code cannot place it in the request's reading: a hint (no span, no evidence), and because
    a row it cannot classify is a row it cannot rule out, no assembly is built for the field (conservative)."""
    base = "Synthetic Collector\nlight trap"
    built = build((Label(base, base.replace("Collector", "Collecter"), decided="a"), Label("Other\nlabel", decided="a")),
        [("collectors", "1A", "Synthetic Collector", "Synthetic Collector"),
         ("collectors", "1B", "Synthetic Collecter", "Synthetic Collecter")])
    assert len([item for item in built.graph[5] if item.status == "grounded"]) == 1
    row = next(item for item in built.specimen.run.evidence if "Collecter" in item.excerpt)
    if tamper == "asset":
        row.asset_id = "another-asset"
    else:
        row.region_id = built.readings["2A"].region_id
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    found = [item for item in graph[5] if item.field_key == FieldKey.COLLECTORS]
    assert graph[2] == () and {item.status for item in found} == {"located", "ungrounded"}
    [hint] = [item for item in found if item.status == "ungrounded"]
    assert hint.reason == "reading_not_in_the_request" and not hint.evidence_ids and hint.observation_id is None


def test_handover_refuses_a_stored_quote_that_the_named_reading_does_not_hold():
    """A changed quote cannot become a span or an accepted assembly."""
    built = build((Label("Synthetic Collector\nlight trap", decided=None),),
        [("collectors", "1A", "Synthetic Collector", "Synthetic Collector"),
         ("collectors", "1B", "Synthetic Collector", "Synthetic Collector")])
    run = built.specimen.run
    reading = built.readings["1A"]
    row = next(item for item in run.evidence if item.observation_ids == [reading.id])
    assert any(item.status == "grounded" for item in candidates(built, "collectors"))
    row.excerpt = "Another Collector"
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert graph[2] == ()
    assert all(item.status != "grounded" for item in graph[5] if item.field_key == FieldKey.COLLECTORS)


# ---------------------------------------------------------------------------- a decided label keeps its value
def test_on_a_decided_label_the_other_reader_is_evidence_and_never_the_value():
    base = "Synthetic Collector\nlight trap"
    differing = build((Label(base, base.replace("Collector", "Collecter"), decided="a"),),
        [("collectors", "1A", "Synthetic Collector", "Synthetic Collector"),
         ("collectors", "1B", "Synthetic Collecter", "Synthetic Collecter")])
    assert differing.specimen.run.fields["collectors"].literal == "Synthetic Collector"
    rows = {item.observation_id: item for item in candidates(differing, "collectors")}
    decided, raw = rows[differing.readings["1A"].id], rows[differing.readings["1B"].id]
    assert (decided.status, raw.status) == ("grounded", "located") and raw.reason == "other_reader_states_another_literal"
    [assembly] = differing.graph[2]
    assert assembly.interpreted_text == "Synthetic Collector" and assembly.evidence_ids == decided.evidence_ids
    assert len(assembly.evidence_ids) == 1 and raw.evidence_ids[0] not in assembly.evidence_ids   # a differing row is not cited
    agreeing = build((Label(base, decided="a"),), [("collectors", "1A", "Synthetic Collector", "Synthetic Collector"),
                                                  ("collectors", "1B", "Synthetic Collector", "Synthetic Collector")])
    rows = {item.observation_id: item for item in candidates(agreeing, "collectors")}
    assert rows[agreeing.readings["1B"].id].reason == "states_the_literal_the_grounded_reading_states"
    assert len(agreeing.graph[1][0].evidence_ids) == 2   # the other reader's agreeing row is evidence of the same event


def test_only_the_other_reader_stating_a_value_is_a_lead_with_a_span_and_no_assembly():
    built = build((Label("Synthetic Collector\nlight trap", decided="a"),),
        [("habitat", "1B", "light trap", "light trap")])
    assert built.specimen.run.fields["habitat"].state == "unknown"
    [item] = candidates(built, "habitat")
    assert item.status == "located" and item.reason == "only_the_other_reader_states_it"
    assert built.graph[1] == () and built.graph[2] == ()


# ---------------------------------------------------------------------------- the span is the row's reading, never another
def test_the_same_literal_in_two_labels_is_tied_to_the_label_each_row_names():
    labels = (Label("Synthetic Collector", decided=None), Label("Synthetic Collector", decided=None))
    built = build(labels, [(  "collectors", name, "Synthetic Collector", "Synthetic Collector")
        for name in ("1A", "1B", "2A", "2B")])
    assert built.specimen.run.fields["collectors"].state == "supported"
    found = {item.observation_id: item for item in candidates(built, "collectors")}
    assert set(found) == {reading.id for reading in built.readings.values()}
    for name, reading in built.readings.items():
        item = found[reading.id]
        assert item.region_id == reading.region_id and reading.literal_text[item.start:item.end] == item.literal, name
    assert sorted(item.status for item in found.values()) == ["grounded", "located", "located", "located"]
    [grounded] = [item for item in found.values() if item.status == "grounded"]
    assert grounded.observation_id == built.readings["1A"].id


def test_a_row_that_names_the_other_reading_is_not_read_and_gives_no_span():
    """A stored row whose locator names a reading whose text does not hold its quote is skipped by the read
    contract: the field keeps its value and no candidate, event or assembly stands on the tampered row."""
    built = build(two_labels(), [("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
                                 ("collectors", "2B", "Synthetic Collector", "Synthetic Collector")])
    run = built.specimen.run
    other = built.readings["1A"]
    for row in run.evidence:
        head, _, rest = row.locator.partition("#")
        row.locator = f"reading:1A:{other.id}#{rest}"
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert graph[2] == ()
    assert len(graph[5]) == 1 and graph[5][0].status == "ungrounded"


def test_the_span_is_searched_in_the_named_reading_only_a_literal_found_only_elsewhere_is_a_hint():
    labels = (Label("Synthetic Collector", decided=None), Label("Nothing Here", decided=None))
    built = build(labels, [("collectors", "1A", "Synthetic Collector", "Synthetic Collector")])
    run = built.specimen.run
    # Re-point the stored row at label 2's reading while its quote stays label 1's: not readable, not a candidate.
    row = run.evidence[0]
    other = built.readings["2A"]
    row.locator = f"reading:2A:{other.id}#" + row.locator.partition("#")[2]
    row.region_id, row.observation_ids = other.region_id, [other.id]
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert graph[5] == () and graph[2] == ()


def test_a_literal_that_occurs_more_than_once_in_the_reading_is_a_hint_even_when_the_readers_agree():
    text = "Synthetic Locality 7\nSynthetic Collector\nSynthetic Locality 7 verso"
    built = build((Label(text, decided=None),), [("collection_code", "1A", "Locality 7", "Synthetic Locality 7"),
                                                 ("collection_code", "1B", "Locality 7", "Synthetic Locality 7")])
    found = candidates(built, "collection_code")
    assert {item.status for item in found} == {"ungrounded"} and {item.reason for item in found} == {
        "literal_occurs_2_times_in_the_reading"}
    assert len(found) == 2 and len({item.id for item in found}) == 2    # two hints, two identities
    assert built.graph[2] == () and built.graph[1] == ()
    request = request_for(built, SpecialistRole.COLLECTION)
    assert len(request.organiser_candidates) == 2 and request.assemblies == ()


def test_a_literal_over_two_lines_or_across_a_line_separator_is_a_hint():
    built = build((Label("Synthetic Collector\nlight trap", decided=None),),
        [("habitat", "1A", "Collector\nlight trap", "Synthetic Collector\nlight trap")])
    [item] = candidates(built, "habitat")
    assert item.status == "ungrounded" and item.reason == "literal_spans_more_than_one_line"
    separated = "oak\u2028margin"
    built = build((Label(separated, decided=None),), [("habitat", "1A", separated, separated), ("habitat", "1B", separated, separated)])
    assert {item.reason for item in candidates(built, "habitat")} == {"literal_spans_more_than_one_line"}


# ---------------------------------------------------------------------------- unicode
def test_a_nfd_reading_and_a_nfc_literal_never_become_a_candidate_and_nfd_on_both_sides_does():
    nfd, nfc = unicodedata.normalize("NFD", "Mu\u0308ller Collector"), unicodedata.normalize("NFC", "Mu\u0308ller Collector")
    assert nfd != nfc
    built = build((Label(nfd, decided=None),), [("collectors", "1A", nfc, nfc), ("collectors", "1B", nfc, nfc)])
    assert built.specimen.run.fields["collectors"].state == "unknown" and built.graph[5] == ()
    built = build((Label(nfd, decided=None),), [("collectors", "1A", nfd, nfd), ("collectors", "1B", nfd, nfd)])
    [grounded] = [item for item in candidates(built, "collectors") if item.status == "grounded"]
    assert grounded.literal == nfd


def test_astral_characters_and_sex_signs_keep_exact_offsets_and_the_native_row_identity():
    text = "FMNH INS 99999\nSynthetic Coll\u00e9ctor \u2642 \U0001f33f"
    built = build((Label(text, decided=None),), [("collectors", "1A", "Synthetic Coll\u00e9ctor", "Synthetic Coll\u00e9ctor \u2642"),
                                                 ("collectors", "1B", "Synthetic Coll\u00e9ctor", "Synthetic Coll\u00e9ctor \u2642")])
    [item] = [row for row in candidates(built, "collectors") if row.status == "grounded"]
    reading = built.readings["1A"]
    assert reading.literal_text[item.start:item.end] == "Synthetic Coll\u00e9ctor"
    from specimen_digitization.research_harness.contracts import digest
    by_id = {row.id: row for row in built.specimen.run.evidence}
    for row in built.graph[3]:
        assert row.publisher_assertion_id == digest(by_id[row.id])


# ---------------------------------------------------------------------------- fields without an assembly path
def test_a_raw_reading_span_of_a_lookup_field_is_located_with_its_own_row_and_no_assembly():
    built = build(two_labels("Syntheticland\nSynthetic Collector"),
        [("country", "2A", "Syntheticland", "Syntheticland"), ("country", "2B", "Syntheticland", "Syntheticland"),
         ("date_visited_from", "2A", "12 June 1948", "12 June 1948")])
    # (the dates and the country are not in ASSEMBLY_FIELDS: located, no assembly, whatever the readers say)
    found = candidates(built)
    assert {item.status for item in found} <= {"located", "ungrounded"} and not [i for i in found if i.status == "grounded"]
    assert built.graph[2] == () and ASSEMBLY_FIELDS >= {FieldKey.COLLECTORS}
    country = candidates(built, "country")
    assert {item.reason for item in country} == {"hand_over_builds_no_assembly_for_the_field"}
    assert all(item.evidence_ids for item in country)


# ---------------------------------------------------------------------------- other guards that must hold on a raw reading
def test_an_unreadable_raw_reading_gets_a_span_and_no_assembly():
    built = build((Label("Synthetic Collector", decided=None, unreadable=("?",)),),
        [("collectors", "1A", "Synthetic Collector", "Synthetic Collector"),
         ("collectors", "1B", "Synthetic Collector", "Synthetic Collector")])
    found = candidates(built, "collectors")
    assert {item.status for item in found} == {"located"} and {item.reason for item in found} == {"reading_has_unreadable_spans"}
    assert built.graph[2] == ()


def test_an_empty_second_reading_is_not_a_reader_that_stays_silent():
    """A reading with no text is not part of the label (the organiser's own rule): the one reader that has text decides."""
    built = build((Label("Synthetic Collector", "  ", decided=None),),
        [("collectors", "1A", "Synthetic Collector", "Synthetic Collector")])
    assert built.specimen.run.fields["collectors"].state == "supported"
    [item] = [row for row in candidates(built, "collectors") if row.status == "grounded"]
    assert item.observation_id == built.readings["1A"].id


def test_a_keyed_assembly_for_the_field_stops_the_organiser_assembly_on_a_raw_reading_too():
    keyed = "collectors: Synthetic Collector"
    built = build((Label(keyed, keyed, decided="a"), Label("Synthetic Collector", decided=None)),
        [("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
         ("collectors", "2B", "Synthetic Collector", "Synthetic Collector")], keyed=True)
    assert [row.interpreted_text for row in built.graph[2] if row.field_key == FieldKey.COLLECTORS] == ["Synthetic Collector"]
    assert not [row for row in built.graph[1] if row.rule_version == ORGANISER_RULE]


# ---------------------------------------------------------------------------- the contract re-reads every span
def test_the_contract_accepts_a_raw_reading_span_and_refuses_a_claimed_span_that_is_not_verbatim():
    built = build(two_labels(), [("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
                                 ("collectors", "2B", "Synthetic Collector", "Synthetic Collector")])
    request = request_for(built, SpecialistRole.PARTIES)
    assert {row.status for row in request.organiser_candidates} == {"grounded", "located"}
    for victim in request.organiser_candidates:
        for tampered in (
            victim.model_copy(update={"start": victim.start + 1, "end": victim.end + 1}),
            victim.model_copy(update={"literal": "Synthetic Collecter"}),
            victim.model_copy(update={"observation_id": built.readings["1A"].id}),         # a reading of another label
            victim.model_copy(update={"region_id": built.readings["1A"].region_id}),       # the right reading, another label
            victim.model_copy(update={"evidence_ids": ("native-evidence:invented",)}),
        ):
            with pytest.raises(ValueError, match="verbatim substring|accepted assembly of its own span|native evidence"):
                SpecialistRequest(**{**dict(request), "organiser_candidates": (tampered, *[
                    row for row in request.organiser_candidates if row is not victim])})


def test_a_span_fragment_of_a_raw_reading_cannot_be_offered_as_the_decided_transcripts():
    """One reading has one input source: a request in which a grounded candidate's fragment says the decided
    transcript while the reading's own lines say raw (or the reverse) cannot be constructed."""
    built = build(two_labels(), [("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
                                 ("collectors", "2B", "Synthetic Collector", "Synthetic Collector")])
    request = request_for(built, SpecialistRole.PARTIES)
    grounded = next(item for item in request.organiser_candidates if item.status == "grounded")
    flipped = tuple(row.model_copy(update={"input_source": "decided_transcript"}) if row.id == grounded.fragment_id
        else row for row in request.fragments)
    with pytest.raises(ValueError, match="exactly one input source"):
        SpecialistRequest(**{**dict(request), "fragments": flipped})


def test_a_located_candidate_may_not_cite_a_native_row_that_does_not_hold_its_literal():
    built = build(two_labels(b=BODY.replace("Collector", "Collecter")),
        [("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
         ("collectors", "2B", "Synthetic Collecter", "Synthetic Collecter")])
    request = request_for(built, SpecialistRole.PARTIES)
    first, second = request.organiser_candidates
    swapped = first.model_copy(update={"evidence_ids": second.evidence_ids})
    with pytest.raises(ValueError, match="native evidence that holds its literal"):
        SpecialistRequest(**{**dict(request), "organiser_candidates": (swapped, second)})


# ---------------------------------------------------------------------------- idempotence
def test_the_graph_is_the_same_twice_and_each_candidate_identity_is_unique():
    answers = [("collectors", "2A", "Synthetic Collector", "Synthetic Collector"),
               ("collectors", "2B", "Synthetic Collector", "Synthetic Collector"),
               ("habitat", "2A", "oak woodland margin", "oak woodland margin"),
               ("habitat", "2B", "oak woodland marsh", "oak woodland marsh")]
    first = build(two_labels(b=BODY.replace("margin", "marsh")), answers)
    second = NativeGenerationRequestFactory._build_graph(first.specimen, first.scope)
    assert first.graph == second
    ids = [item.id for item in first.graph[5]]
    assert len(ids) == len(set(ids)) == len(first.graph[5])


def test_the_validator_source_still_matches_its_committed_pin():
    import hashlib
    from pathlib import Path
    from specimen_digitization.research_harness import evidence
    from specimen_digitization.research_harness.accepted_output import VALIDATOR_SOURCE_SHA256
    assert hashlib.sha256(Path(evidence.__file__).read_bytes()).hexdigest() == VALIDATOR_SOURCE_SHA256


def test_explicit_collecting_date_in_both_raw_readers_has_a_publishable_g44_settlement():
    line = "Collection date: 12.V.1948"
    literal = "12.V.1948"
    built = build(two_labels(a=line), [("date_visited_from", "2A", literal, line),
                                       ("date_visited_from", "2B", literal, line)])
    rows = candidates(built, "date_visited_from")
    assert [item.status for item in rows] == ["grounded", "located"]
    request = request_for(built, SpecialistRole.TEMPORAL)
    written, copied = temporal_resolutions(request, event_id=rows[0].event_id)
    assert (written.field_key, written.value.normalized, written.value.precision) == (
        FieldKey.DATE_VISITED_FROM, "1948-05-12", "day")
    assert (copied.field_key, copied.value_layer, copied.value.normalized) == (
        FieldKey.DATE_VISITED_TO, "derived", "1948-05-12")
    assert set(written.evidence_ids) == set(copied.evidence_ids) == {
        evidence_id for row in rows for evidence_id in row.evidence_ids}
    assert validate_resolution(request, written) == written
    assert validate_resolution(request, copied) == copied


def test_a_decided_date_still_requires_the_other_reader_to_quote_the_same_event():
    line = "Collection date: 12.V.1948"
    answers = [("date_visited_from", "2A", "12.V.1948", line),
               ("date_visited_from", "2B", "12.V.1948", line)]
    agreed = build(two_labels(a=line, decided="a"), answers)
    assert [item.status for item in candidates(agreed, "date_visited_from")] == ["grounded", "located"]
    silent = build(two_labels(a=line, decided="a"), answers[:1])
    assert {item.status for item in candidates(silent, "date_visited_from")} == {"located"}
    assert not [item for item in silent.graph[2] if item.field_key == FieldKey.DATE_VISITED_FROM]


def test_explicit_determination_date_never_uses_a_collecting_event():
    line = "Collection date: 12.V.1948"
    literal = "12.V.1948"
    built = build(two_labels(a=line), [("date_identified", "2A", literal, line),
                                       ("date_identified", "2B", literal, line)])
    assert {item.status for item in candidates(built, "date_identified")} == {"located"}
    assert not [item for item in built.graph[2] if item.field_key == FieldKey.DATE_IDENTIFIED]
    determination = "Determination date: 17.V.1948"
    dated = build(two_labels(a=determination), [("date_identified", "2A", "17.V.1948", determination),
                                                ("date_identified", "2B", "17.V.1948", determination)])
    grounded = next(item for item in candidates(dated, "date_identified") if item.status == "grounded")
    request = request_for(dated, SpecialistRole.TEMPORAL)
    [resolution] = temporal_resolutions(request, event_id=grounded.event_id)
    assert resolution.field_key == FieldKey.DATE_IDENTIFIED
    assert resolution.value.normalized == "1948-05-17"
    assert validate_resolution(request, resolution) == resolution


def test_explicit_single_elevation_in_both_readers_has_four_publishable_endpoints():
    line = "Elev. 1200 ft"
    literal = "1200 ft"
    built = build(two_labels(a=line), [("elevation_from_ft", "2A", literal, line),
                                       ("elevation_from_ft", "2B", literal, line)])
    grounded = next(item for item in candidates(built, "elevation_from_ft") if item.status == "grounded")
    request = request_for(built, SpecialistRole.MEASUREMENT)
    settled = settle_elevation(request, assembly_ids=(grounded.assembly_id,))
    resolutions = elevation_resolutions(settled)
    assert {item.field_key for item in resolutions} == {
        FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT,
        FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M}
    assert {item.value.normalized for item in resolutions if str(item.field_key).endswith("_m")} == {"365.76"}
    assert {item.value.normalized for item in resolutions if str(item.field_key).endswith("_ft")} == {"1200.00"}
    assert sum(item.value_layer == "settled" for item in resolutions) == 1
    assert all(validate_resolution(request, item) == item for item in resolutions)


@pytest.mark.parametrize(("line", "literal", "field", "other"), (
    ("12.V.1948", "12.V.1948", "date_visited_from", None),
    ("Collection date: 4-5-48", "4-5-48", "date_visited_from", None),
    ("Collection date: 12.V.1948", "12.V.1948", "date_visited_from", "Collection date: 13.V.1948"),
    ("Elev. 1200", "1200", "elevation_from_m", None),
    ("Elev. 1200 m", "1200 m", "elevation_from_ft", None),
    ("Elev. 1200 m", "1200 m", "elevation_from_m", "Elev. 1300 m"),
))
def test_unqualified_date_or_elevation_stays_for_review(line, literal, field, other):
    second = other or line
    second_literal = ("13.V.1948" if "13.V.1948" in second else "1300 m" if "1300 m" in second else literal)
    built = build(two_labels(a=line, b=second), [(field, "2A", literal, line),
                                                 (field, "2B", second_literal, second)])
    assert {item.status for item in candidates(built, field)} <= {"located", "ungrounded"}
    assert not [item for item in built.graph[2] if item.field_key == FieldKey(field)]


def test_a_silent_second_reader_or_a_competing_elevation_field_blocks_qualification():
    line = "Elev. 1200 m"
    one = build(two_labels(a=line), [("elevation_from_m", "2A", "1200 m", line)])
    assert {item.status for item in candidates(one, "elevation_from_m")} == {"located"}
    contested = build(two_labels(a="Elev. 1200 m\nElev. 1300 m"), [
        ("elevation_from_m", "2A", "1200 m", "Elev. 1200 m"),
        ("elevation_from_m", "2B", "1200 m", "Elev. 1200 m"),
        ("elevation_to_m", "2A", "1300 m", "Elev. 1300 m"),
        ("elevation_to_m", "2B", "1300 m", "Elev. 1300 m")])
    assert not [item for item in contested.graph[2] if item.field_key in {
        FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M}]


@pytest.mark.parametrize("line", (
    "6,400 ft",
    "Camp, 6,400 ft, cloud forest",
    "Collected at 6,400 ft above sea level.",
))
def test_unit_bearing_elevation_on_a_narrative_line_retains_exact_spans_and_fills_four_endpoints(line):
    literal = "6,400 ft"
    built = build(two_labels(a=line), [("elevation_from_ft", "2A", literal, line),
                                       ("elevation_from_ft", "2B", literal, line)])
    rows = candidates(built, "elevation_from_ft")
    [grounded] = [item for item in rows if item.status == "grounded"]
    request = request_for(built, SpecialistRole.MEASUREMENT)
    for item in rows:
        reading = next(row for row in built.readings.values() if row.id == item.observation_id)
        assert reading.literal_text[item.start:item.end] == item.literal == literal
    assembly = next(item for item in request.assemblies if item.id == grounded.assembly_id)
    assert assembly.interpreted_text == literal and len(assembly.evidence_ids) == 2
    resolutions = elevation_resolutions(settle_elevation(request, assembly_ids=(assembly.id,)))
    assert {item.value.normalized for item in resolutions if str(item.field_key).endswith("_ft")} == {"6400.00"}
    assert {item.value.normalized for item in resolutions if str(item.field_key).endswith("_m")} == {"1950.72"}
    assert all(validate_resolution(request, item) == item for item in resolutions)


@pytest.mark.parametrize(("literal", "to_value", "qualifiers", "uncertainty"), (
    ("1200-1300 m", "1300.00", (), None),
    ("ca. 1200 m", "1200.00", ("ca.",), None),
    ("1200 m ± 5 m", "1200.00", (), "5"),
))
def test_parser_supported_elevation_range_qualifier_and_uncertainty_keep_the_written_metadata(
        literal, to_value, qualifiers, uncertainty):
    line = "Camp at " + literal + " above sea level"
    built = build(two_labels(a=line), [("elevation_from_m", "2A", literal, line),
                                       ("elevation_from_m", "2B", literal, line)])
    grounded = next(item for item in candidates(built) if item.status == "grounded")
    request = request_for(built, SpecialistRole.MEASUREMENT)
    settled = settle_elevation(request, assembly_ids=(grounded.assembly_id,))
    assert settled.assertions[0].literal == literal
    assert settled.assertions[0].qualifiers == qualifiers and settled.assertions[0].uncertainty == uncertainty
    resolutions = elevation_resolutions(settled)
    assert next(item for item in resolutions if item.field_key == FieldKey.ELEVATION_FROM_M).value.normalized == "1200.00"
    assert next(item for item in resolutions if item.field_key == FieldKey.ELEVATION_TO_M).value.normalized == to_value
    assert all(item.measurement.qualifiers == qualifiers and item.measurement.uncertainty == uncertainty for item in resolutions)
    assert all(validate_resolution(request, item) == item for item in resolutions)


def test_formatting_only_elevation_disagreement_grounds_supported_agreement_without_rewriting_either_reading():
    first, second = "Camp, 6,400 ft, forest", "Camp, 6400 feet, forest"
    built = build(two_labels(a=first, b=second), [
        ("elevation_from_ft", "2A", "6,400 ft", first),
        ("elevation_from_ft", "2B", "6400 feet", second)])
    assert built.specimen.run.fields["elevation_from_ft"].state == ValueState.AMBIGUOUS
    rows = candidates(built, "elevation_from_ft")
    assert {item.literal for item in rows} == {"6,400 ft", "6400 feet"}
    [grounded] = [item for item in rows if item.status == "grounded"]
    request = request_for(built, SpecialistRole.MEASUREMENT)
    assert {fragment.observation_text for fragment in request.fragments} >= {first, second}
    assembly = next(item for item in request.assemblies if item.id == grounded.assembly_id)
    assert assembly.evidence_ids == grounded.evidence_ids
    assert len(assembly.evidence_ids) == 1
    assert {item.id for item in request.evidence} >= {item.evidence_ids[0] for item in rows}
    assert assembly.interpreted_text == "6,400 ft"
    resolutions = elevation_resolutions(settle_elevation(request, assembly_ids=(assembly.id,)))
    assert {item.value.normalized for item in resolutions if str(item.field_key).endswith("_m")} == {"1950.72"}
    assert all(validate_resolution(request, item) == item for item in resolutions)


@pytest.mark.parametrize("decided", ("a", None))
def test_silent_reader_allows_only_a_verified_decided_elevation_transcript(decided):
    line, other = "Camp at 1200 m", "Camp altitude illegible"
    built = build(two_labels(a=line, b=other, decided=decided), [
        ("elevation_from_m", "2A", "1200 m", line)])
    [candidate] = candidates(built, "elevation_from_m")
    assert candidate.status == ("grounded" if decided else "located")
    assert any(fragment.observation_text == other for fragment in built.graph[0])
    if decided:
        request = request_for(built, SpecialistRole.MEASUREMENT)
        [fragment] = [item for item in request.fragments if item.id == candidate.fragment_id]
        assert fragment.input_source == "decided_transcript"
        assert all(validate_resolution(request, item) == item for item in elevation_resolutions(
            settle_elevation(request, assembly_ids=(candidate.assembly_id,))))
    # A decided transcript is not permission to erase a contrary numeric reading.
    contrary = "Camp at 1300 m"
    contested = build(two_labels(a=line, b=contrary, decided=decided), [
        ("elevation_from_m", "2A", "1200 m", line),
        ("elevation_from_m", "2B", "1300 m", contrary)])
    assert {item.literal for item in candidates(contested)} == {"1200 m", "1300 m"}
    assert {item.status for item in candidates(contested)} == {"located"}
    unreadable = build(two_labels(a=line, decided=decided, unreadable=("?",)), [
        ("elevation_from_m", "2A", "1200 m", line),
        ("elevation_from_m", "2B", "1200 m", line)])
    assert {item.status for item in candidates(unreadable)} == {"located"}


@pytest.mark.parametrize(("line", "literal"), (
    ("Camp at ca. 1200 m", "1200 m"),
    ("Camp at -1200 m", "1200 m"),
    ("Camp at 1200-1300 m", "1300 m"),
    ("Camp at -6,400 - -6,300 m", "-6,300 m"),
    ("Camp at 1,200 m", "200 m"),
    ("Camp at 1200 m ± 5 m", "1200 m"),
))
def test_a_partial_elevation_span_never_discards_written_qualifiers_signs_ranges_or_uncertainty(line, literal):
    built = build(two_labels(a=line), [("elevation_from_m", "2A", literal, line),
                                       ("elevation_from_m", "2B", literal, line)])
    assert {item.status for item in candidates(built)} <= {"located", "ungrounded"}
    assert not [item for item in built.graph[2] if item.field_key in {
        FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M}]


@pytest.mark.parametrize("other", (
    "Camp at 1200 m; ridge 1300 m",
    "Camp at 1200 m\nRidge 1300 meters",
    "Camp at 1200 m; ridge ca. 1300 m",
    "Camp at 1200 m; ridge 1200-1300 m",
    "Camp at 1200 m; ridge 1300 m ± 5 m",
))
@pytest.mark.parametrize("decided", ("a", None))
def test_unclaimed_competing_elevation_in_retained_reading_prevents_grounding(other, decided):
    # Extraction omitted the second assertion. The raw reading remains evidence.
    built = build(two_labels(a=other, decided=decided), [
        ("elevation_from_m", "2A", "1200 m", other),
        ("elevation_from_m", "2B", "1200 m", other),
    ])
    assert {item.status for item in candidates(built)} == {"located"}
    assert not [item for item in built.graph[2] if item.field_key in ELEVATION_FIELDS]


@pytest.mark.parametrize("other", ("Camp at 1300 m", "Camp at 1,300 metres", "Camp at 1200 ft"))
def test_unclaimed_contrary_peer_reading_prevents_decided_elevation_grounding(other):
    line = "Camp at 1200 m"
    built = build(two_labels(a=line, b=other, decided="a"), [
        ("elevation_from_m", "2A", "1200 m", line),
    ])
    assert {item.status for item in candidates(built)} == {"located"}
    assert not [item for item in built.graph[2] if item.field_key in ELEVATION_FIELDS]


def test_unclaimed_formatting_equivalent_peer_keeps_decided_elevation_grounding():
    line = "Camp at 1,200 m"
    built = build(two_labels(a=line, b="Camp at 1200 meters", decided="a"), [
        ("elevation_from_m", "2A", "1,200 m", line),
    ])
    assert {item.status for item in candidates(built)} == {"grounded"}


@pytest.mark.parametrize(("role", "tool_id", "field", "line", "literal"), (
    (SpecialistRole.TEMPORAL, "settle_temporal", "date_visited_from", "Collected: 12.V.1948", "12.V.1948"),
    (SpecialistRole.MEASUREMENT, "settle_elevation", "elevation_from_m", "Alt. 1200 m", "1200 m"),
))
def test_local_settlement_utility_replays_exact_accepted_output(role, tool_id, field, line, literal):
    built = build(two_labels(a=line), [(field, "2A", literal, line), (field, "2B", literal, line)])
    request = request_for(built, role)
    grounded = next(item for item in candidates(built, field) if item.status == "grounded")
    args = {"field_key": field, "event_id": grounded.event_id}
    if tool_id == "settle_elevation":
        args["assembly_ids"] = [grounded.assembly_id]
    broker = SourceBroker(SourceRegistry(()))
    result = asyncio.run(broker.invoke_utility(request, tool_id, args))
    rows = [FieldResolution.model_validate(item) for item in json.loads(result.candidate_json[0])["resolutions"]]
    assert len(rows) == (2 if tool_id == "settle_temporal" else 4)
    assert all(validate_resolution(request, item) == item for item in rows)
    replay = verify_local_utility_v2(request, result)
    assert replay.as_receipt()["arguments"] == args and replay.utility_version == "deterministic-settlement-v1"
    changed = json.loads(result.candidate_json[0])
    changed["resolutions"][0]["value"]["normalized"] = "fabricated"
    tampered = result.model_copy(update={"candidate_json": (json.dumps(changed),)})
    with pytest.raises(PublicationUnavailable, match="canonical_local_utility_unproved"):
        verify_local_utility_v2(request, tampered)
    wrong_version = result.model_copy(update={"coverage": result.coverage.model_copy(update={
        "source_version": "deterministic-settlement-old"})})
    with pytest.raises(PublicationUnavailable, match="canonical_local_utility_unproved"):
        verify_local_utility_v2(request, wrong_version)
    with pytest.raises(ValueError):
        asyncio.run(broker.invoke_utility(request, tool_id, {**args, "event_id": "invented"}))
