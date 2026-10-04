"""The hand-over: the ordinary extractor's field values reach the specialists as organiser candidates.

Today (J1, K1) a specialist sees every line of every reader's reading but not the values the
ordinary extractor stored, and on a real label no assembly exists, so no literal field can
resolve. The hand-over (initial_requests._organiser_pass, contracts.OrganiserCandidate) hands each
stored value over next to the raw readings and, for the five literal fields the validator accepts
from a complete literal assembly, builds an accepted event and assembly when trusted code finds the
literal as a verbatim substring of exactly one line of the decided reading.

What these tests pin, with the real validator (evidence.validate_resolution) and the real contract
classes, on abstract synthetic labels (only the shape comes from the ten recorded snapshots: a
two-line catalog region, a few one-line values, the extractor quoting the whole region):

- the span (reading, region, offsets) is computed from the reading text and re-checked when the
  request is built: a span that is not a verbatim substring cannot be constructed;
- a candidate that cannot be located exactly is an ungrounded hint: no span, no event, no
  assembly, and nothing in the request lets a model resolve a value from it;
- the dates, the elevations, taxon and the geography fields get no assembly from the hand-over
  (initial_requests.ASSEMBLY_FIELDS says why);
- what did not move: the SpecialistOutput schema digest, evidence.py and the files the projector
  pin hashes (application/domain.py among them).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from specimen_digitization.application import domain
from specimen_digitization.application.domain import (
    Asset, Evidence, FieldValue, Observation, ReaderHandoff, Region, Run, Scope, Specimen, Transcript, ValueState,
)
from specimen_digitization.research_harness import evidence as evidence_module
from specimen_digitization.research_harness.agents import specialist_output_schema_digest
from specimen_digitization.research_harness.contracts import (
    MAX_ORGANISER_CANDIDATES, ROLE_FIELDS, EventKind, FieldKey, FieldResolution, OrganiserCandidate,
    ResearchScope, SpecialistRequest, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import (
    EvidenceError, validate_assembly, validate_resolution,
)
from specimen_digitization.research_harness.initial_requests import (
    ASSEMBLY_FIELDS, ORGANISER_RULE, NativeGenerationRequestFactory,
)
from specimen_digitization.research_harness.prompts import resolve_prompt

# One region shaped like the recorded labels: a catalog line, then the values the extractor quotes.
DECIDED = "\n".join((
    "FMNH INS 0010001",
    "Syntheticland",
    "Synthetic Collector",
    "12 June 1948",
    "1200 ft",
    "oak woodland margin",
    "light trap",
))


@dataclass
class RegionSpec:
    decided: str
    raw: str | None = None          # the other reader's text; default: the same
    unreadable: tuple = ()          # unreadable spans the decided reading carries


@dataclass
class FieldSpec:
    key: str
    literal: str
    regions: tuple = (0,)           # the regions its evidence rows quote
    quote: str | None = None        # the evidence row's excerpt; default: the whole decided transcript
    state: ValueState = ValueState.SUPPORTED
    rows: bool = True               # False: the field cites no evidence row


@dataclass
class Built:
    specimen: Specimen
    scope: ResearchScope
    graph: tuple = field(default=())
    first_reading: dict = field(default_factory=dict)   # region index -> decided observation


def build(regions=(RegionSpec(DECIDED),), fields=(), *, keyed=False):
    asset = Asset(sha256="a" * 64, blob_ref="a" * 64 + ":1", media_type="image/jpeg", size_bytes=10, width=100,
        height=100, filename="fixture.jpeg", uploader="fixture", sensitive=False)
    run_regions, observations, transcripts, decided = [], [], [], {}
    for index, spec in enumerate(regions):
        region = Region(asset_id=asset.id, x=0, y=0, width=100, height=100, order=index, method="fixture",
            version="fixture")
        raw = spec.raw if spec.raw is not None else spec.decided
        first = Observation(region_id=region.id, route_id="handwriting-qwen", model_id="fixture-model",
            provider="fixture", prompt_version="b" * 64, input_sha256="c" * 64, input_asset_id=asset.id,
            literal_text=spec.decided, raw_ref="fixture-response", raw_sha256="d" * 64,
            unreadable_spans=list(spec.unreadable))
        second = Observation(region_id=region.id, route_id="handwriting-muse", model_id="fixture-model",
            provider="fixture", prompt_version="b" * 64, input_sha256="c" * 64, input_asset_id=asset.id,
            literal_text=raw, raw_ref="fixture-response", raw_sha256="d" * 64)
        transcripts.append(Transcript(region_id=region.id, text=spec.decided, observation_ids=[first.id, second.id],
            alternatives=sorted({spec.decided, raw}), resolved=True,
            decision_kind="identical_readings" if raw == spec.decided else "first_pass",
            selected_observation_id=first.id,
            handoffs=[ReaderHandoff(observation_id=first.id, role="decided_transcript", handed_text=spec.decided),
                ReaderHandoff(observation_id=second.id, role="raw_reading", handed_text=raw)]))
        run_regions.append(region)
        observations += [first, second]
        decided[index] = first
    run = Run(regions=run_regions, observations=observations, transcripts=transcripts)
    for spec in fields:
        ids = []
        if spec.rows:
            for index in spec.regions:
                transcript = transcripts[index]
                row = Evidence(kind="literal", asset_id=asset.id, region_id=transcript.region_id,
                    observation_ids=list(transcript.observation_ids), source="bounded_extraction_v1",
                    locator="region:" + transcript.region_id, excerpt=spec.quote or transcript.text,
                    raw_ref="fixture-response", digest="d" * 64)
                run.evidence.append(row)
                ids.append(row.id)
        run.fields[spec.key] = FieldValue(state=spec.state, literal=spec.literal, parsed=spec.literal,
            evidence_ids=ids, reason="Exact source-supported typed extraction")
    specimen = Specimen(scope=Scope(organization_id="org", collection_id="collection"), asset=asset, run=run)
    if keyed:
        from specimen_digitization.application.workflow import Workflow
        Workflow.parse(run, asset.id)
    scope = ResearchScope(organization_id="org", collection_id="collection", specimen_id=specimen.id,
        job_id="opaque-fixture-job", generation=1, input_digest="e" * 64, profile_digest="f" * 64, sensitive=False)
    built = Built(specimen, scope, first_reading=decided)
    built.graph = NativeGenerationRequestFactory._build_graph(specimen, scope)
    return built


def candidates(built):
    return built.graph[5]


def by_field(built, key):
    return [item for item in candidates(built) if item.field_key == FieldKey(key)]


def request_for(built, role):
    fragments, events, assemblies, evidence, decisions, found = built.graph
    keys = ROLE_FIELDS[role]
    prompt = resolve_prompt(role, profile_digest=built.scope.profile_digest, source_registry_digest="a" * 64,
        toolset_digest="b" * 64, model_route="harness-deepseek", output_schema_digest="c" * 64)
    return SpecialistRequest(scope=built.scope, role=role, field_keys=keys, prompt=prompt, fragments=fragments,
        events=events, assemblies=assemblies, evidence=evidence, accepted_decisions=decisions,
        organiser_candidates=tuple(item for item in found if item.field_key in keys),
        field_revisions={key: 0 for key in keys})


STORED = (
    FieldSpec("fmnh_ins_number", "0010001"),
    FieldSpec("collectors", "Synthetic Collector"),
    FieldSpec("habitat", "oak woodland margin"),
    FieldSpec("collection_method", "light trap"),
    FieldSpec("country", "Syntheticland"),
    FieldSpec("date_visited_from", "12 June 1948"),
    FieldSpec("elevation_from_ft", "1200"),
)


def literal_resolution(request, candidate, text=None, key=None):
    """What a specialist that follows the v5 block returns for a grounded candidate."""
    assembly = next(item for item in request.assemblies if item.id == candidate.assembly_id)
    fragment = next(item for item in request.fragments if item.id == candidate.fragment_id)
    written = text if text is not None else assembly.interpreted_text
    digits = evidence_module.catalog_literal(written) if candidate.field_key == FieldKey.FMNH_INS_NUMBER else written
    return FieldResolution(field_key=candidate.field_key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal=written, parsed=digits, normalized=digits,
            evidence_ids=list(assembly.evidence_ids), evidence_relations=dict.fromkeys(assembly.evidence_ids, "supports"),
            verbatim_by_observation={fragment.observation_id: fragment.observation_text},
            settled_observation_ids=[fragment.observation_id]),
        evidence_ids=assembly.evidence_ids, assembly_ids=(assembly.id,), event_id=assembly.event_id,
        reason="The readings support the extractor's value")


# ---------------------------------------------------------------------------- the grounded candidates
def test_a_stored_value_found_in_one_line_becomes_a_grounded_candidate_with_an_accepted_assembly():
    built = build(fields=STORED)
    fragments, events, assemblies, evidence, _, found = built.graph
    grounded = {item.field_key: item for item in found if item.status == "grounded"}
    assert set(grounded) == {FieldKey(key) for key in ("fmnh_ins_number", "collectors", "habitat", "collection_method")}
    reading = built.first_reading[0]
    for key, item in grounded.items():
        assert item.source == "extractor" and item.region_id == reading.region_id and item.observation_id == reading.id
        # The offsets are those of the literal in the decided reading, computed from its text.
        assert reading.literal_text[item.start:item.end] == item.literal
        assert reading.literal_text.count(item.literal) == 1
        fragment = next(row for row in fragments if row.id == item.fragment_id)
        assert (fragment.start, fragment.end, fragment.literal, fragment.input_source, fragment.granularity) == (
            item.start, item.end, item.literal, "decided_transcript", "span")
        assert fragment.observation_text == reading.literal_text
        event = next(row for row in events if row.id == item.event_id)
        assert event.status == "accepted" and event.validator_version == ORGANISER_RULE == event.rule_version
        assert event.kind == (EventKind.COLLECTING if key == FieldKey.COLLECTORS else EventKind.UNKNOWN)
        assembly = next(row for row in assemblies if row.id == item.assembly_id)
        assert assembly.interpreted_text == item.literal and assembly.field_key == key
        assert assembly.fragment_ids == (fragment.id,) and assembly.event_id == event.id
        # The evidence is the extractor's own native row, not an invented one.
        assert item.evidence_ids == assembly.evidence_ids == event.evidence_ids
        assert set(item.evidence_ids) <= {row.id for row in built.specimen.run.evidence}
        assert set(item.evidence_ids) <= {row.id for row in evidence}


def test_the_validator_accepts_a_value_equal_to_the_assembly_and_refuses_any_other():
    """The real validate_resolution: catalog number and collectors resolve from the organiser assembly
    exactly as from a keyed line; a value the assembly does not hold, and a resolution that names no
    assembly, are refused."""
    built = build(fields=STORED)
    for role, key in ((SpecialistRole.COLLECTION, "fmnh_ins_number"), (SpecialistRole.PARTIES, "collectors"),
                      (SpecialistRole.COLLECTION, "habitat"), (SpecialistRole.COLLECTION, "collection_method")):
        request = request_for(built, role)
        [candidate] = [item for item in request.organiser_candidates if item.field_key == FieldKey(key)]
        resolution = literal_resolution(request, candidate)
        assert validate_resolution(request, resolution) == resolution
        validate_assembly(request, next(item for item in request.assemblies if item.id == candidate.assembly_id))
        other = "0010002" if key == "fmnh_ins_number" else candidate.literal + " x"
        with pytest.raises(EvidenceError, match="differs from immutable assembly"):
            validate_resolution(request, literal_resolution(request, candidate, text=other))
        bare = resolution.model_copy(update={"assembly_ids": (), "event_id": None})
        with pytest.raises(EvidenceError, match="lacks qualified deciding authority"):
            validate_resolution(request, bare)


def test_the_extractor_quote_does_not_decide_the_offsets():
    """The ordinary extractor quotes the whole region; a narrower quote that still holds the literal
    gives the same span, because trusted code searches the reading and reads no offset from the row."""
    whole = build(fields=STORED)
    narrow = build(fields=(FieldSpec("collectors", "Synthetic Collector", quote="Synthetic Collector"),))
    [a] = [item for item in candidates(whole) if item.field_key == FieldKey.COLLECTORS]
    [b] = [item for item in candidates(narrow) if item.field_key == FieldKey.COLLECTORS]
    assert (a.start, a.end) == (b.start, b.end) and a.status == b.status == "grounded"


def test_a_literal_inside_a_longer_line_is_a_span_and_the_assembly_is_only_that_span():
    built = build(fields=(FieldSpec("fmnh_ins_number", "0010001"),))
    [item] = candidates(built)
    reading = built.first_reading[0]
    assert reading.literal_text.splitlines()[0] == "FMNH INS 0010001" and (item.start, item.end) == (9, 16)
    request = request_for(built, SpecialistRole.COLLECTION)
    [assembly] = request.assemblies
    assert assembly.interpreted_text == "0010001"
    # The whole line is a fragment too (every line is), and is not the assembly's.
    assert any(row.literal == "FMNH INS 0010001" and row.granularity == "line" for row in request.fragments)
    assert assembly.fragment_ids == (item.fragment_id,)


# ---------------------------------------------------------------------------- the ungrounded hints
@pytest.mark.parametrize(("label", "spec", "reason"), (
    ("a value the extractor altered (not in the reading)", FieldSpec("collectors", "Collector, Synthetic",
        quote=DECIDED), "extractor_quote_does_not_hold_the_literal"),
    ("a literal over two lines", FieldSpec("habitat", "Synthetic Collector\n12 June 1948"),
        "literal_spans_more_than_one_line"),
    ("a quote that does not hold the literal", FieldSpec("collectors", "Synthetic Collector",
        quote="Syntheticland"), "extractor_quote_does_not_hold_the_literal"),
    ("a quote from outside the decided reading", FieldSpec("collectors", "Synthetic Collector",
        quote="Synthetic Collector, elsewhere"), "extractor_quote_does_not_hold_the_literal"),
    ("a field with no evidence row", FieldSpec("collectors", "Synthetic Collector", rows=False),
        "no_extractor_evidence_row_for_the_literal"),
))
def test_a_value_that_cannot_be_located_exactly_is_an_ungrounded_hint_that_never_becomes_an_assembly(label, spec, reason):
    built = build(fields=(spec,))
    fragments, events, assemblies, _, _, found = built.graph
    [item] = found
    assert item.status == "ungrounded" and item.reason == reason, label
    assert item.literal == spec.literal and item.source == "extractor"
    assert (item.observation_id, item.start, item.end, item.fragment_id, item.event_id, item.assembly_id) == (
        None, None, None, None, None, None)
    assert item.evidence_ids == ()
    # (The keyed-line pass may make a proposed event for a line a quote equals; it never makes an accepted one.)
    assert assemblies == () and not [row for row in events if row.status == "accepted"]
    # The hint is carried to the specialist that owns the field, and nothing in the request grounds it.
    role = next(role for role, keys in ROLE_FIELDS.items() if item.field_key in keys)
    request = request_for(built, role)
    assert request.organiser_candidates == (item,) and request.assemblies == ()
    assert not [row for row in request.events if row.status == "accepted"]
    # A model that resolves the field anyway, with no assembly or a made-up one, is refused.
    forged = FieldResolution(field_key=item.field_key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal=item.literal, parsed=item.literal, normalized=item.literal),
        evidence_ids=("e",), assembly_ids=("assembly:invented",), event_id="event:invented", reason="invented")
    with pytest.raises(EvidenceError, match="Unknown literal assembly"):
        validate_resolution(request, forged)
    with pytest.raises(EvidenceError, match="lacks qualified deciding authority"):
        validate_resolution(request, forged.model_copy(update={"assembly_ids": (), "event_id": None}))


def test_a_literal_that_occurs_more_than_once_is_not_placed_by_guesswork():
    """A short literal in two lines has no one place (K1/F5: 1 of 28 real values): the offsets are not
    guessed, the candidate is a hint. A single line holding it twice is no better."""
    twice = "\n".join(("SL 7", "Synthetic Locality", "SL 7 verso"))
    built = build((RegionSpec(twice),), (FieldSpec("collection_code", "SL 7"),))
    [item] = candidates(built)
    assert item.status == "ungrounded" and item.reason == "literal_occurs_2_times_in_the_decided_reading"
    assert built.graph[1] == () and built.graph[2] == ()
    built = build((RegionSpec("ab ab"),), (FieldSpec("collection_code", "ab"),))
    assert candidates(built)[0].reason == "literal_occurs_2_times_in_the_decided_reading"


def test_a_region_with_no_decided_reading_gives_a_hint_and_never_an_assembly():
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector"),))
    built.specimen.run.transcripts[0].resolved = False
    fragments, events, assemblies, _, _, found = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert events == () and assemblies == ()
    [item] = found
    assert item.status == "ungrounded" and item.reason == "no_decided_reading_for_the_region"
    assert item.region_id == built.specimen.run.regions[0].id and item.observation_id is None


def test_an_unreadable_decided_reading_gets_a_located_span_and_no_assembly():
    built = build((RegionSpec(DECIDED, unreadable=("?",)),), (FieldSpec("collectors", "Synthetic Collector"),))
    [item] = candidates(built)
    assert item.status == "located" and item.reason == "decided_reading_has_unreadable_spans"
    assert built.first_reading[0].literal_text[item.start:item.end] == item.literal
    assert built.graph[1] == () and built.graph[2] == ()


# ---------------------------------------------------------------------------- the fields without an assembly
def test_the_dates_elevations_taxon_and_geography_are_located_and_get_no_assembly():
    """The validator accepts a date or an elevation only as the exact object of its deterministic
    settlement (no tool returns it) and the record holds that value back; taxon and the geography
    fields resolve from a lookup. For each the candidate carries its span and nothing else."""
    built = build(fields=(*STORED, FieldSpec("taxon", "Syntheticland"), FieldSpec("verbatim_dts", "12 June 1948")))
    found = {item.field_key: item for item in candidates(built)}
    reading = built.first_reading[0]
    for key in ("country", "date_visited_from", "elevation_from_ft", "taxon", "verbatim_dts"):
        item = found[FieldKey(key)]
        assert item.status == "located" and item.reason == "field_has_no_literal_assembly_path", key
        assert reading.literal_text[item.start:item.end] == item.literal
        assert (item.fragment_id, item.event_id, item.assembly_id) == (None, None, None)
        assert key not in {str(row.field_key) for row in built.graph[2]}
    assert {row.field_key for row in built.graph[2]} <= set(ASSEMBLY_FIELDS)
    assert ASSEMBLY_FIELDS == {FieldKey(key) for key in
        ("fmnh_ins_number", "collection_code", "habitat", "collection_method", "collectors")}
    # No fragment, event or assembly was added for them: the five literal fields' only.
    assert len(built.graph[2]) == 4 and len(built.graph[1]) == 4


def test_a_field_the_extractor_did_not_resolve_hands_over_nothing():
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector", state=ValueState.AMBIGUOUS),
        FieldSpec("habitat", "oak woodland margin", state=ValueState.UNKNOWN)))
    assert candidates(built) == () and built.graph[1] == () and built.graph[2] == ()


def test_several_candidates_for_one_field_are_carried_each_with_its_own_assembly():
    """The same literal quoted in two regions: two candidates, two events, two assemblies. A resolution
    names one event's assemblies (evidence.py reads the field and event), and the validator accepts it."""
    built = build((RegionSpec(DECIDED), RegionSpec("Syntheticland\nSynthetic Collector")),
        (FieldSpec("collectors", "Synthetic Collector", regions=(0, 1)),))
    found = by_field(built, "collectors")
    assert len(found) == 2
    assert len({item.id for item in found}) == len({item.assembly_id for item in found}) == 2
    assert {item.status for item in found} == {"grounded"} and found[0].region_id != found[1].region_id
    request = request_for(built, SpecialistRole.PARTIES)
    for item in found:
        resolution = literal_resolution(request, item)
        assert validate_resolution(request, resolution) == resolution


def test_the_cap_and_the_literal_bound_are_the_contracts():
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector"),))
    [item] = candidates(built)
    request = request_for(built, SpecialistRole.PARTIES)
    assert MAX_ORGANISER_CANDIDATES == 100
    many = tuple(item.model_copy(update={"id": f"organiser:{index}"}) for index in range(MAX_ORGANISER_CANDIDATES + 1))
    with pytest.raises(ValueError, match="at most 100"):
        rebuilt(request, organiser_candidates=many)
    with pytest.raises(ValueError):
        OrganiserCandidate(id="x", field_key=FieldKey.HABITAT, literal="x" * 2001, source="extractor",
            status="ungrounded", reason="no_extractor_evidence_row_for_the_literal")


# ---------------------------------------------------------------------------- the contract refuses a claimed span
def rebuilt(request, **changes):
    return SpecialistRequest(**{**dict(request), **changes})


def test_a_claimed_span_that_is_not_a_verbatim_substring_cannot_be_constructed():
    built = build(fields=STORED)
    request = request_for(built, SpecialistRole.PARTIES)
    [item] = request.organiser_candidates
    assert item.status == "grounded"
    for tampered in (
        item.model_copy(update={"start": item.start + 1, "end": item.end + 1}),   # shifted
        item.model_copy(update={"end": item.end + 3}),                            # longer than the literal
        item.model_copy(update={"literal": "Synthetic Collecter"}),               # a different literal
        item.model_copy(update={"observation_id": "not-a-reading"}),              # a reading the request lacks
    ):
        with pytest.raises(ValueError, match="verbatim substring of the decided reading|names an accepted assembly"):
            rebuilt(request, organiser_candidates=(tampered,))
    # The same candidate, untouched, is accepted.
    assert rebuilt(request, organiser_candidates=(item,)).organiser_candidates == (item,)


def test_a_span_in_the_raw_readers_text_is_not_a_decided_span():
    """The second reader's reading is raw: a candidate cannot cite it, whatever its text says."""
    built = build((RegionSpec(DECIDED, raw=DECIDED.replace("Collector", "Collecter")),),
        (FieldSpec("collectors", "Synthetic Collector"),))
    request = request_for(built, SpecialistRole.PARTIES)
    [item] = request.organiser_candidates
    raw = next(row for row in request.fragments if row.input_source == "raw_reading")
    start = raw.observation_text.find("Synthetic Collecter")
    moved = item.model_copy(update={"observation_id": raw.observation_id, "start": start, "end": start + len(item.literal) - 1,
        "literal": "Synthetic Collecte"})
    with pytest.raises(ValueError, match="decided reading"):
        rebuilt(request, organiser_candidates=(moved,))


def test_a_grounded_candidate_must_name_an_accepted_assembly_of_its_own_span():
    built = build(fields=STORED)
    request = request_for(built, SpecialistRole.COLLECTION)
    candidate = next(item for item in request.organiser_candidates if item.field_key == FieldKey.HABITAT)
    other = next(item for item in request.organiser_candidates if item.field_key == FieldKey.COLLECTION_METHOD)
    for tampered in (
        candidate.model_copy(update={"assembly_id": other.assembly_id}),
        candidate.model_copy(update={"event_id": other.event_id}),
        candidate.model_copy(update={"fragment_id": other.fragment_id}),
        candidate.model_copy(update={"assembly_id": "assembly:invented"}),
        candidate.model_copy(update={"evidence_ids": ("native-evidence:invented",)}),
    ):
        with pytest.raises(ValueError, match="accepted assembly of its own span"):
            rebuilt(request, organiser_candidates=(tampered,))
    proposed = [item.model_copy(update={"status": "proposed", "validator_version": None}) if item.id == candidate.event_id
                else item for item in request.events]
    with pytest.raises(ValueError, match="accepted assembly of its own span"):
        rebuilt(request, events=tuple(proposed))


def test_the_status_fields_of_a_candidate_are_consistent():
    common = dict(id="organiser:x", field_key=FieldKey.HABITAT, literal="oak", source="extractor")
    with pytest.raises(ValueError, match="no span"):
        OrganiserCandidate(**common, status="ungrounded", reason="literal_spans_more_than_one_line", start=0, end=3,
            region_id="r", observation_id="o")
    with pytest.raises(ValueError, match="names its region, reading and span"):
        OrganiserCandidate(**common, status="located", reason="field_has_no_literal_assembly_path")
    with pytest.raises(ValueError, match="no event or assembly"):
        OrganiserCandidate(**common, status="located", reason="field_has_no_literal_assembly_path", region_id="r",
            observation_id="o", start=0, end=3, assembly_id="a")
    with pytest.raises(ValueError, match="names its fragment, event, assembly and evidence"):
        OrganiserCandidate(**common, status="grounded", reason="verbatim_in_one_line_of_the_decided_reading",
            region_id="r", observation_id="o", start=0, end=3)
    with pytest.raises(ValueError):
        OrganiserCandidate(**common, status="invented", reason="x")
    with pytest.raises(ValueError):
        OrganiserCandidate(**{**common, "source": "Extractor!"}, status="ungrounded", reason="x")


def test_a_request_carries_only_the_candidates_of_its_own_fields_and_unique_ids():
    built = build(fields=STORED)
    for role in SpecialistRole:
        request = request_for(built, role)
        assert {item.field_key for item in request.organiser_candidates} <= set(ROLE_FIELDS[role])
    request = request_for(built, SpecialistRole.PARTIES)
    foreign = next(item for item in candidates(built) if item.field_key == FieldKey.HABITAT)
    with pytest.raises(ValueError, match="requested owned field"):
        rebuilt(request, organiser_candidates=(foreign,))
    [mine] = request.organiser_candidates
    with pytest.raises(ValueError, match="must be unique"):
        rebuilt(request, organiser_candidates=(mine, mine))


# ---------------------------------------------------------------------------- the keyed-line path
KEYED = "\n".join(("collectors: Synthetic Collector", "habitat: oak woodland margin", "country: Syntheticland"))


def test_a_keyed_label_keeps_its_assemblies_and_the_candidates_name_them_instead_of_duplicating():
    """`field_key: value` lines still make their own events and assemblies (the keyed e2e fixtures);
    the hand-over adds none for the same span, and names the keyed assembly in the candidate."""
    built = build((RegionSpec(KEYED),), (), keyed=True)
    # The graph without any extractor value: the keyed lines alone.
    alone = built.specimen.model_copy(deep=True)
    alone.run.fields = {key: FieldValue() for key in alone.run.fields}
    keyed_only = NativeGenerationRequestFactory._build_graph(alone, built.scope)
    assert keyed_only[5] == () and len(keyed_only[2]) == 3
    # Every record of the keyed pass is unchanged and none was added.
    assert built.graph[:5] == keyed_only[:5]
    found = {item.field_key: item for item in candidates(built)}
    assert set(found) == {FieldKey.COLLECTORS, FieldKey.HABITAT, FieldKey.COUNTRY}
    assert {item.status for item in found.values()} == {"grounded"}
    assert all(item.reason == "keyed_line_assembly_holds_the_span" for item in found.values())
    assert {item.assembly_id for item in found.values()} == {item.id for item in built.graph[2]}
    accepted = [item for item in built.graph[1] if item.status == "accepted"]
    assert {item.event_id for item in found.values()} == {item.id for item in accepted}
    assert all(row.rule_version == "exact-field-key-line/v1" for row in built.graph[1])


def test_a_keyed_field_the_extractor_gave_another_value_for_is_located_and_adds_no_second_assembly():
    built = build((RegionSpec(KEYED + "\nSecond Collector"),), (), keyed=True)
    run = built.specimen.run
    transcript = run.transcripts[0]
    quote = Evidence(kind="literal", asset_id=built.specimen.asset.id, region_id=transcript.region_id,
        observation_ids=list(transcript.observation_ids), source="bounded_extraction_v1",
        locator="region:" + transcript.region_id, excerpt=transcript.text, raw_ref="fixture-response", digest="d" * 64)
    run.evidence.append(quote)
    run.fields["collectors"] = FieldValue(state=ValueState.SUPPORTED, literal="Second Collector",
        parsed="Second Collector", evidence_ids=[quote.id])
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    [item] = [row for row in graph[5] if row.field_key == FieldKey.COLLECTORS]
    assert item.status == "located" and item.reason == "keyed_line_assembly_for_the_field_exists"
    assert [row.interpreted_text for row in graph[2] if row.field_key == FieldKey.COLLECTORS] == ["Synthetic Collector"]


# ---------------------------------------------------------------------------- what did not move
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_the_output_schema_and_the_pinned_files_did_not_move():
    """A typed field on FieldValue, Evidence or Run would move the projector pin (application/domain.py) and
    SpecialistOutput's schema digest, and re-digest every prompt pin. The hand-over adds none."""
    from specimen_digitization.application import active_graph, projection, storage
    from specimen_digitization.research_harness.accepted_output import VALIDATOR_SOURCE_SHA256
    assert specialist_output_schema_digest() == (
        "79c8fd8dcd1c707745025db3970a82db9082787017e922c3eecba0e09199da24")  # pragma: allowlist secret
    assert sha(evidence_module.__file__) == VALIDATOR_SOURCE_SHA256
    assert sha(projection.__file__) == "2c37115f0542da507b7102454211d57f9cacb5ae6eafa6698e292b9c9a9aba6a"  # pragma: allowlist secret
    assert sha(domain.__file__) == "688b93cd47a8a7df577734c67bbb17f434dc492fc29e269c873d46901aa5c67f"  # pragma: allowlist secret
    assert sha(storage.__file__) == "3c9511b52160da2ae7b529b5262431f3b5a76b8fb228f98e34689a833f41be88"  # pragma: allowlist secret
    assert sha(active_graph.__file__) == "9f22032c3443a564f034d92fc41eda616bbee6f36de6002653bd14aacc892d47"  # pragma: allowlist secret
    for model in (FieldValue, Evidence, Run):
        assert not [name for name in model.model_fields if "organiser" in name]
