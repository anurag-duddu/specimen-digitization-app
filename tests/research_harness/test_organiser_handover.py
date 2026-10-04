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
import re
from dataclasses import dataclass, field, replace
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


SAME = object()


@dataclass
class FieldSpec:
    """A field the ordinary extractor stored, and the evidence rows it cites.

    ``shape="legacy"``: one row per region as the extractor writes them today (locator ``region:<id>``, the
    whole region transcript as the excerpt unless ``quote`` narrows it, every reader's observation id).
    ``shape="reading"``: rows exactly as #262 (the organiser, application/organiser.py) stores them: locator
    ``reading:<label>:<observation id>#quote=a-b;literal=c-d``, ONE observation id, the narrow quote (default:
    the literal) as the excerpt, one row per reader in ``readers`` (0: the decided reading, 1: the other reader's)."""

    key: str
    literal: str
    regions: tuple = (0,)           # the regions its evidence rows quote
    quote: str | None = None        # the evidence row's excerpt; default: the whole decided transcript / the literal
    state: ValueState = ValueState.SUPPORTED
    rows: bool = True               # False: the field cites no evidence row
    shape: str = "legacy"
    readers: tuple = (0,)           # reading shape: which readers' rows
    reader_literals: dict = field(default_factory=dict)   # reading shape: the literal a reader's row claims
    value_literal: object = SAME    # the field's own stored literal (None: an AMBIGUOUS field has none)
    offsets: tuple | None = None    # reading shape: stored (quote start, quote end, literal start, literal end)
    source: str = "bounded_extraction_v1"
    edit: object = None             # a function applied to each row before it is stored


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
                made = []
                if spec.shape == "legacy":
                    made.append(Evidence(kind="literal", asset_id=asset.id, region_id=transcript.region_id,
                        observation_ids=list(transcript.observation_ids), source=spec.source,
                        locator="region:" + transcript.region_id, excerpt=spec.quote or transcript.text,
                        raw_ref="fixture-response", digest="d" * 64))
                else:
                    for reader in spec.readers:
                        reading = observations[2 * index + reader]
                        claimed = spec.reader_literals.get(reader, spec.literal)
                        quote = spec.quote or claimed
                        qs = reading.literal_text.index(quote)
                        ls = qs + quote.index(claimed)
                        stored = spec.offsets or (qs, qs + len(quote), ls, ls + len(claimed))
                        made.append(Evidence(kind="literal", asset_id=asset.id, region_id=transcript.region_id,
                            observation_ids=[reading.id], source=spec.source, excerpt=quote,
                            locator="reading:%d%s:%s#quote=%d-%d;literal=%d-%d" % (
                                index + 1, "AB"[reader], reading.id, stored[0], stored[1], stored[2], stored[3]),
                            raw_ref="fixture-response", digest="d" * 64))
                for row in made:
                    row = spec.edit(row) if spec.edit else row
                    run.evidence.append(row)
                    ids.append(row.id)
        stored_literal = spec.literal if spec.value_literal is SAME else spec.value_literal
        run.fields[spec.key] = FieldValue(state=spec.state, literal=stored_literal, parsed=stored_literal,
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


SHAPES = ("legacy", "reading")


def shaped(specs, shape):
    """The same stored fields, their rows in the given shape (see FieldSpec)."""
    return tuple(replace(spec, shape=shape) for spec in specs)


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
@pytest.mark.parametrize("shape", SHAPES)
def test_a_stored_value_found_in_one_line_becomes_a_grounded_candidate_with_an_accepted_assembly(shape):
    built = build(fields=shaped(STORED, shape))
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


@pytest.mark.parametrize("shape", SHAPES)
def test_the_validator_accepts_a_value_equal_to_the_assembly_and_refuses_any_other(shape):
    """The real validate_resolution: catalog number and collectors resolve from the organiser assembly
    exactly as from a keyed line; a value the assembly does not hold, and a resolution that names no
    assembly, are refused."""
    built = build(fields=shaped(STORED, shape))
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


@pytest.mark.parametrize("shape", SHAPES)
def test_a_literal_inside_a_longer_line_is_a_span_and_the_assembly_is_only_that_span(shape):
    built = build(fields=(FieldSpec("fmnh_ins_number", "0010001", shape=shape),))
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
        "no_usable_extractor_row_for_the_literal"),
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


@pytest.mark.parametrize("shape", SHAPES)
def test_a_literal_that_occurs_more_than_once_is_not_placed_by_guesswork(shape):
    """A short literal in two lines has no one place (K1/F5: 1 of 28 real values): the offsets are not
    guessed, the candidate is a hint. A single line holding it twice is no better."""
    twice = "\n".join(("SL 7", "Synthetic Locality", "SL 7 verso"))
    built = build((RegionSpec(twice),), (FieldSpec("collection_code", "SL 7", shape=shape),))
    [item] = candidates(built)
    assert item.status == "ungrounded" and item.reason == "literal_occurs_2_times_in_the_cited_reading"
    assert built.graph[1] == () and built.graph[2] == ()
    built = build((RegionSpec("ab ab"),), (FieldSpec("collection_code", "ab", shape=shape),))
    assert candidates(built)[0].reason == "literal_occurs_2_times_in_the_cited_reading"


def test_a_region_with_no_decided_reading_gives_a_hint_and_never_an_assembly():
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector"),))
    built.specimen.run.transcripts[0].resolved = False
    fragments, events, assemblies, _, _, found = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert events == () and assemblies == ()
    [item] = found
    assert item.status == "ungrounded" and item.reason == "no_decided_reading_for_the_region"
    assert item.region_id == built.specimen.run.regions[0].id and item.observation_id is None


@pytest.mark.parametrize("shape", SHAPES)
def test_an_unreadable_decided_reading_gets_a_located_span_and_no_assembly(shape):
    built = build((RegionSpec(DECIDED, unreadable=("?",)),),
        (FieldSpec("collectors", "Synthetic Collector", shape=shape),))
    [item] = candidates(built)
    assert item.status == "located" and item.reason == "decided_reading_has_unreadable_spans"
    assert built.first_reading[0].literal_text[item.start:item.end] == item.literal
    assert built.graph[1] == () and built.graph[2] == ()


# ---------------------------------------------------------------------------- the fields without an assembly
@pytest.mark.parametrize("shape", SHAPES)
def test_the_dates_elevations_taxon_and_geography_are_located_and_get_no_assembly(shape):
    """The validator accepts a date or an elevation only as the exact object of its deterministic
    settlement (no tool returns it) and the record holds that value back; taxon and the geography
    fields resolve from a lookup. For each the candidate carries its span and nothing else."""
    built = build(fields=shaped((*STORED, FieldSpec("taxon", "Syntheticland"),
        FieldSpec("verbatim_dts", "12 June 1948")), shape))
    found = {item.field_key: item for item in candidates(built)}
    reading = built.first_reading[0]
    for key in ("country", "date_visited_from", "elevation_from_ft", "taxon", "verbatim_dts"):
        item = found[FieldKey(key)]
        assert item.status == "located" and item.reason == "hand_over_builds_no_assembly_for_the_field", key
        assert reading.literal_text[item.start:item.end] == item.literal
        assert (item.fragment_id, item.event_id, item.assembly_id) == (None, None, None)
        assert key not in {str(row.field_key) for row in built.graph[2]}
    assert {row.field_key for row in built.graph[2]} <= set(ASSEMBLY_FIELDS)
    assert ASSEMBLY_FIELDS == {FieldKey(key) for key in
        ("fmnh_ins_number", "collection_code", "habitat", "collection_method", "collectors")}
    # No fragment, event or assembly was added for them: the five literal fields' only.
    assert len(built.graph[2]) == 4 and len(built.graph[1]) == 4


def test_a_field_the_extractor_did_not_settle_has_located_candidates_and_no_assembly():
    """An AMBIGUOUS field (competing candidates) or an UNKNOWN one (a lead) carries what its rows quote, located,
    so the harness sees it; only the field's own stored value of a SUPPORTED field can be grounded."""
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector", state=ValueState.AMBIGUOUS),
        FieldSpec("habitat", "oak woodland margin", state=ValueState.UNKNOWN)))
    found = {item.field_key: item for item in candidates(built)}
    assert {item.status for item in found.values()} == {"located"}
    assert {item.reason for item in found.values()} == {"not_the_stored_field_value"}
    assert built.graph[1] == () and built.graph[2] == ()


def test_several_candidates_for_one_field_are_carried_and_only_the_stored_value_is_grounded():
    """#262 stores one row per candidate: the same literal quoted on two labels is two candidates. Only the
    first row that carries the field's own stored value is grounded (one event, one assembly); the other is
    located, so the specialist cannot resolve the field from a second independent assertion the extractor
    did not settle on."""
    built = build((RegionSpec(DECIDED), RegionSpec("Syntheticland\nSynthetic Collector")),
        (FieldSpec("collectors", "Synthetic Collector", regions=(0, 1), shape="reading"),))
    found = by_field(built, "collectors")
    assert len(found) == 2 and found[0].region_id != found[1].region_id
    assert [item.status for item in found] == ["grounded", "located"]
    assert found[1].reason == "not_the_stored_field_value" and found[1].assembly_id is None
    assert len(built.graph[2]) == 1
    request = request_for(built, SpecialistRole.PARTIES)
    resolution = literal_resolution(request, found[0])
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
            status="ungrounded", reason="no_usable_extractor_row_for_the_literal")


def test_the_pass_stops_at_the_cap_the_contract_sets():
    """Twenty fields quoted in seven regions would be 140 candidates; the contract bounds a request at 100."""
    keys = [str(key) for key in FieldKey]
    text = "\n".join(f"tok{index:02d}" for index in range(len(keys)))
    built = build(tuple(RegionSpec(text) for _ in range(7)),
        tuple(FieldSpec(key, f"tok{index:02d}", regions=tuple(range(7)), shape="reading")
              for index, key in enumerate(keys)))
    assert len(candidates(built)) == MAX_ORGANISER_CANDIDATES
    for role in SpecialistRole:
        assert len(request_for(built, role).organiser_candidates) <= MAX_ORGANISER_CANDIDATES


@pytest.mark.parametrize("shape", SHAPES)
def test_a_native_evidence_row_with_non_ascii_text_has_the_identity_the_publication_rederives(shape):
    """A value read from an organiser assembly cites the extractor's native evidence row, and the publication's
    evidence provider (canonical_evidence_provider_v2._capture_contexts) finds the row again by re-deriving its
    identity digests with contracts.digest. The application's storage digest escapes non-ASCII text, so a quote
    with a sex sign (recorded labels carry one) got another identity and the value was refused with
    canonical_capture_missing_actual_evidence: on a recorded specimen, the record stopped."""
    from specimen_digitization.application.storage import digest as storage_digest
    from specimen_digitization.research_harness.contracts import digest
    text = "FMNH INS 0010001\nSynthetic Collector \u2642\n"
    quote = "Synthetic Collector " + chr(0x2642) if shape == "reading" else None
    built = build((RegionSpec(text),), (FieldSpec("collectors", "Synthetic Collector", shape=shape, quote=quote),))
    [row] = built.specimen.run.evidence
    assert not row.excerpt.isascii()
    assert storage_digest(row.model_dump(mode="json")) != digest(row)   # the two digests really differ here
    [item] = built.graph[3]
    assert item.id == row.id
    assert item.publisher_assertion_id == digest(row)
    assert (row.digest or digest(row)) == item.response_digest
    # With no digest of its own the fallback is the same function.
    row.digest = None
    [item] = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)[3]
    assert item.response_digest == digest(row) == item.publisher_assertion_id


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
        with pytest.raises(ValueError, match="verbatim substring of the reading it cites|names an accepted assembly"):
            rebuilt(request, organiser_candidates=(tampered,))
    # The same candidate, untouched, is accepted.
    assert rebuilt(request, organiser_candidates=(item,)).organiser_candidates == (item,)


def test_a_grounded_candidate_cannot_cite_the_raw_readers_text():
    """The second reader's reading is raw: a grounded candidate (one with an assembly) cannot cite it."""
    built = build((RegionSpec(DECIDED, raw=DECIDED.replace("Collector", "Collecter")),),
        (FieldSpec("collectors", "Synthetic Collector"),))
    request = request_for(built, SpecialistRole.PARTIES)
    [item] = request.organiser_candidates
    raw = next(row for row in request.fragments if row.input_source == "raw_reading")
    start = raw.observation_text.find("Synthetic Collecter")
    moved = item.model_copy(update={"observation_id": raw.observation_id, "start": start, "end": start + len(item.literal) - 1,
        "literal": "Synthetic Collecte"})
    with pytest.raises(ValueError, match="must cite the decided reading"):
        rebuilt(request, organiser_candidates=(moved,))
    # The same span as a LOCATED candidate (no assembly) is a span in the reading it cites, and is accepted.
    located = moved.model_copy(update={"status": "located", "fragment_id": None, "event_id": None,
        "assembly_id": None, "evidence_ids": (), "reason": "cited_reading_is_not_the_decided_transcript"})
    assert rebuilt(request, organiser_candidates=(located,)).organiser_candidates == (located,)


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
        OrganiserCandidate(**common, status="located", reason="hand_over_builds_no_assembly_for_the_field")
    with pytest.raises(ValueError, match="no event or assembly"):
        OrganiserCandidate(**common, status="located", reason="hand_over_builds_no_assembly_for_the_field", region_id="r",
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
    with pytest.raises(ValueError, match="owned field of the role"):
        rebuilt(request, organiser_candidates=(foreign,))
    [mine] = request.organiser_candidates
    with pytest.raises(ValueError, match="must be unique"):
        rebuilt(request, organiser_candidates=(mine, mine))


# ---------------------------------------------------------------------------- the keyed-line path
KEYED = "\n".join(("collectors: Synthetic Collector", "habitat: oak woodland margin", "country: Syntheticland"))


def with_extractor_rows(built, *keys):
    """The keyed fields, as the ordinary run holds them after the extraction call also quoted them: the extractor's
    whole-region row first, the keyed line's row after it."""
    run, transcript = built.specimen.run, built.specimen.run.transcripts[0]
    for key in keys:
        row = Evidence(kind="literal", asset_id=built.specimen.asset.id, region_id=transcript.region_id,
            observation_ids=list(transcript.observation_ids), source="bounded_extraction_v1",
            locator="region:" + transcript.region_id, excerpt=transcript.text, raw_ref="fixture-response",
            digest="d" * 64)
        run.evidence.append(row)
        run.fields[key] = run.fields[key].model_copy(update={"evidence_ids": [row.id, *run.fields[key].evidence_ids]})
    return NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)


def test_a_keyed_label_keeps_its_assemblies_and_its_fields_name_them_as_they_always_did():
    """`field_key: value` lines still make their own events and assemblies (the keyed e2e fixtures), and the
    keyed field's row (source `label`, the line as the excerpt) is read like a whole-region row: its candidate is
    grounded by naming the keyed assembly of that span, so no second event or assembly is added. (#262's own
    reader skips keyed rows; this one does not, so keyed fields are handed over exactly as before.)"""
    built = build((RegionSpec(KEYED),), (), keyed=True)
    alone = built.specimen.model_copy(deep=True)
    alone.run.fields = {key: FieldValue() for key in alone.run.fields}      # the keyed lines alone
    keyed_only = NativeGenerationRequestFactory._build_graph(alone, built.scope)
    assert keyed_only[5] == () and len(keyed_only[2]) == 3
    # Every record of the keyed pass is unchanged and none was added.
    assert (built.graph[0], built.graph[1], built.graph[2]) == (keyed_only[0], keyed_only[1], keyed_only[2])
    found = {item.field_key: item for item in candidates(built)}
    assert set(found) == {FieldKey.COLLECTORS, FieldKey.HABITAT, FieldKey.COUNTRY}
    assert {item.status for item in found.values()} == {"grounded"}
    assert all(item.reason == "keyed_line_assembly_holds_the_span" for item in found.values())
    assert {item.assembly_id for item in found.values()} == {item.id for item in built.graph[2]}
    accepted = [item for item in built.graph[1] if item.status == "accepted"]
    assert {item.event_id for item in found.values()} == {item.id for item in accepted}
    assert all(row.rule_version == "exact-field-key-line/v1" for row in built.graph[1])


def test_an_extractor_row_on_a_keyed_line_names_the_keyed_assembly_too():
    built = build((RegionSpec(KEYED),), (), keyed=True)
    keyed_only = built.graph
    graph = with_extractor_rows(built, "collectors", "habitat", "country")
    assert (graph[0], graph[1], graph[2]) == (keyed_only[0], keyed_only[1], keyed_only[2])
    found = {item.field_key: item for item in graph[5]}
    assert {item.status for item in found.values()} == {"grounded"} and len(graph[5]) == 3
    assert {item.assembly_id for item in found.values()} == {item.id for item in graph[2]}


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


# ---------------------------------------------------------------------------- both stored shapes (B2: #262)
# #262 (the organiser, application/organiser.py) stores one row per candidate with the locator
# `reading:<label>:<observation id>#quote=a-b;literal=c-d`, ONE observation id and the narrow quote as the
# excerpt, for every reading of the label (the other reader's and an undecided label's included). This
# branch must read those rows and today's whole-region rows alike, whichever merges first, and without
# importing #262. The FieldSpec shape "reading" builds rows exactly as #262's apply_candidates stores them.
def test_both_stored_shapes_give_the_same_candidates_and_assemblies():
    legacy = build(fields=STORED)
    narrow = build(fields=tuple(replace(spec, shape="reading") for spec in STORED))

    def summary(built):
        return (sorted((str(item.field_key), item.status, item.reason, item.literal, item.start, item.end)
            for item in candidates(built)), sorted((str(row.field_key), row.interpreted_text) for row in built.graph[2]))
    assert summary(legacy) == summary(narrow) and len(summary(narrow)[1]) == 4


def test_a_row_shaped_like_262s_is_grounded_by_trusted_code_and_cites_its_own_row():
    quote = "Syntheticland\nSynthetic Collector"
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector", shape="reading", quote=quote),))
    [row] = built.specimen.run.evidence
    reading = built.first_reading[0]
    assert re.fullmatch(r"reading:1A:[0-9a-f-]{36}#quote=\d+-\d+;literal=\d+-\d+", row.locator)
    assert row.observation_ids == [reading.id] and row.excerpt == quote and row.source == "bounded_extraction_v1"
    [item] = candidates(built)
    assert item.status == "grounded" and item.observation_id == reading.id
    assert reading.literal_text[item.start:item.end] == "Synthetic Collector"
    assert item.evidence_ids == (row.id,)
    request = request_for(built, SpecialistRole.PARTIES)
    resolution = literal_resolution(request, item)
    assert validate_resolution(request, resolution) == resolution


def test_stored_offsets_are_never_a_place():
    """The stored literal span only names the string the extractor claimed. A literal that occurs twice stays
    a hint although the stored span points at one occurrence; a stored span that does not fit the reading
    makes the row no candidate row (the stored value is then a hint, never placed)."""
    twice = "\n".join(("SL 7", "Synthetic Locality", "SL 7 verso"))
    built = build((RegionSpec(twice),), (FieldSpec("collection_code", "SL 7", shape="reading", quote="SL 7"),))
    [row] = built.specimen.run.evidence
    assert row.locator.endswith("#quote=0-4;literal=0-4")                      # it names the first occurrence
    [item] = candidates(built)
    assert item.status == "ungrounded" and item.reason == "literal_occurs_2_times_in_the_cited_reading"
    assert (item.start, item.end, item.assembly_id) == (None, None, None) and built.graph[2] == ()
    bad = build(fields=(FieldSpec("collectors", "Synthetic Collector", shape="reading", offsets=(1, 5, 2, 4)),))
    [item] = candidates(bad)
    assert item.status == "ungrounded" and item.reason == "no_usable_extractor_row_for_the_literal"
    assert bad.graph[2] == ()


@pytest.mark.parametrize("edit", (
    lambda row: row.model_copy(update={"observation_ids": [*row.observation_ids, "another-reading"]}),
    lambda row: row.model_copy(update={"region_id": "another-region"}),
    lambda row: row.model_copy(update={"locator": row.locator.replace(row.observation_ids[0], "unknown-reading")}),
    lambda row: row.model_copy(update={"excerpt": row.excerpt + " (edited)"}),
), ids=("two_readings", "other_region", "unknown_reading", "quote_is_not_the_text_at_the_span"))
def test_a_reading_row_that_does_not_name_one_reading_of_its_region_is_not_a_candidate_row(edit):
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector", shape="reading", edit=edit),))
    [item] = candidates(built)
    assert item.status == "ungrounded" and item.reason == "no_usable_extractor_row_for_the_literal"
    assert built.graph[2] == () and not [row for row in built.graph[1] if row.status == "accepted"]


def test_a_row_of_another_source_is_not_a_candidate_row():
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector", shape="reading", source="lookup_elsewhere"),
        FieldSpec("habitat", "oak woodland margin", source="lookup_elsewhere")))
    assert {item.status for item in candidates(built)} == {"ungrounded"} and built.graph[2] == ()
    assert {item.reason for item in candidates(built)} == {"no_usable_extractor_row_for_the_literal"}


def test_a_row_citing_the_other_reader_is_located_in_that_reading_and_never_an_assembly():
    raw = DECIDED.replace("Collector", "Collecter")
    spec = FieldSpec("collectors", "Synthetic Collector", shape="reading", readers=(0, 1),
        reader_literals={1: "Synthetic Collecter"})
    built = build((RegionSpec(DECIDED, raw=raw),), (spec,))
    decided_row, raw_row = (item for item in candidates(built))
    assert decided_row.status == "grounded"
    assert (raw_row.status, raw_row.reason) == ("located", "cited_reading_is_not_the_decided_transcript")
    other = built.specimen.run.observations[1]
    assert raw_row.observation_id == other.id and other.literal_text[raw_row.start:raw_row.end] == raw_row.literal
    assert raw_row.literal == "Synthetic Collecter" and raw_row.assembly_id is None
    assert len(built.graph[2]) == 1                       # the decided reading's value only
    request = request_for(built, SpecialistRole.PARTIES)  # the contract accepts a located span in a raw reading
    assert request.organiser_candidates == (decided_row, raw_row)


def test_an_ambiguous_field_of_262_has_located_candidates_and_no_assembly():
    """No literal is stored for a field the extractor could not settle (its readers differ): every candidate
    is carried so the harness checks it, none is grounded."""
    raw = DECIDED.replace("oak woodland margin", "oak woodland margen")
    spec = FieldSpec("habitat", "oak woodland margin", shape="reading", readers=(0, 1), state=ValueState.AMBIGUOUS,
        value_literal=None, reader_literals={1: "oak woodland margen"})
    built = build((RegionSpec(DECIDED, raw=raw),), (spec,))
    decided_row, raw_row = candidates(built)
    assert (decided_row.status, decided_row.reason) == ("located", "not_the_stored_field_value")
    assert (raw_row.status, raw_row.reason) == ("located", "cited_reading_is_not_the_decided_transcript")
    assert built.graph[2] == () and not [row for row in built.graph[1] if row.status == "accepted"]


def test_a_label_with_no_decided_reading_still_locates_its_readers_candidates():
    """#262 reads every reading of an undecided label: those rows cite raw readings of a region with no decided
    transcript. Each is located in the reading it cites (no event, no assembly can come from a raw reading)."""
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector", shape="reading", readers=(0, 1)),))
    run = built.specimen.run
    run.transcripts[0].resolved = False
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, built.scope)
    assert {item.status for item in graph[5]} == {"located"} and graph[2] == ()
    assert {item.reason for item in graph[5]} == {"cited_reading_is_not_the_decided_transcript"}


def test_the_reading_label_of_262s_rows_is_carried_and_a_whole_region_row_has_none():
    """A hint reaches the specialist marked with the reading it quotes: observation_id (a located one) and the
    organiser's label (1A, 1B ...), none for a whole-region row, which cites no one reading. The label is
    informational: nothing is placed or checked by it."""
    raw = DECIDED.replace("Collector", "Collecter")
    spec = FieldSpec("collectors", "Synthetic Collector", shape="reading", readers=(0, 1),
        reader_literals={1: "Synthetic Collecter"})
    built = build((RegionSpec(DECIDED, raw=raw),), (spec,))
    assert [item.label for item in candidates(built)] == ["1A", "1B"]
    old = build(fields=(FieldSpec("collectors", "Synthetic Collector"),))
    assert [item.label for item in candidates(old)] == [None]
    # A hint keeps the label too (it names the reading the extractor quoted, though nothing was placed).
    twice = build((RegionSpec("SL 7\nx\nSL 7 verso"),), (FieldSpec("collection_code", "SL 7", shape="reading"),))
    [item] = candidates(twice)
    assert (item.status, item.label, item.observation_id) == ("ungrounded", "1A", None)


def test_the_two_shapes_can_meet_in_one_specimen_and_the_stored_value_of_each_is_grounded():
    built = build(fields=(FieldSpec("collectors", "Synthetic Collector"),
        FieldSpec("habitat", "oak woodland margin", shape="reading")))
    assert {(str(item.field_key), item.status) for item in candidates(built)} == {
        ("collectors", "grounded"), ("habitat", "grounded")}


def test_the_candidates_do_not_depend_on_the_order_of_run_fields():
    """The request is re-derived on every open and compared downstream: the order of a jsonb object's keys must
    not change it. The pass reads fields in key order."""
    built = build(fields=STORED)
    built.specimen.run.fields = dict(reversed(list(built.specimen.run.fields.items())))
    assert NativeGenerationRequestFactory._build_graph(built.specimen, built.scope) == built.graph


# ---------------------------------------------------------------------------- S1: certain refusals are not assembled
# (field, literal, whether the validator is certain to refuse a resolution that equals the literal)
VALIDATOR_CASES = (
    ("fmnh_ins_number", "0010001", False), ("fmnh_ins_number", "FMNH INS", True), ("fmnh_ins_number", "123", True),
    ("collection_code", "FMNHINS", True), ("collection_code", "FMNH INS", True), ("collection_code", "FMNH-INS", True),
    ("collection_code", "AB 12", False),
    ("habitat", "x", True), ("habitat", "12-34", True), ("habitat", "AB-12", True), ("habitat", "oak", False),
    ("collection_method", "light trap", False), ("collection_method", "7", True),
    ("collectors", "J. Smith 2", True), ("collectors", "J", True), ("collectors", "Synthetic Collector", False),
)


@pytest.mark.parametrize(("key", "literal", "refused"), VALIDATOR_CASES)
def test_trusted_code_does_not_assemble_what_the_validator_is_certain_to_refuse(key, literal, refused, monkeypatch):
    """A real model that resolves an accepted assembly the validator refuses gets the generic retry message, one
    retry, then its whole role fails. The pass checks the shape rules itself; this test checks the pass against the
    validator, so the copy cannot drift."""
    from specimen_digitization.research_harness import initial_requests
    built = build((RegionSpec(literal + "\nSynthetic Locality"),), (FieldSpec(key, literal),))
    [item] = candidates(built)
    if refused:
        assert (item.status, item.reason) == ("located", "validator_would_refuse_the_literal")
        assert built.graph[2] == () and not [row for row in built.graph[1] if row.status == "accepted"]
    else:
        assert item.status == "grounded"
    # What the validator says about the same literal when an assembly exists anyway.
    monkeypatch.setattr(initial_requests, "_validator_refuses", lambda *args: False)
    forced = build((RegionSpec(literal + "\nSynthetic Locality"),), (FieldSpec(key, literal),))
    [candidate] = candidates(forced)
    assert candidate.status == "grounded"
    role = next(role for role, keys in ROLE_FIELDS.items() if FieldKey(key) in keys)
    request = request_for(forced, role)
    try:
        validate_resolution(request, literal_resolution(request, candidate))
        verdict = False
    except EvidenceError:
        verdict = True
    assert verdict is refused


# ---------------------------------------------------------------------------- S2: token boundaries
@pytest.mark.parametrize(("key", "literal", "text", "status"), (
    ("fmnh_ins_number", "0012345", "FMNH INS 0012345", "grounded"),
    ("fmnh_ins_number", "12345", "FMNH INS 0012345", "located"),        # the leading zeros dropped
    ("fmnh_ins_number", "00123", "00123456", "located"),                # a truncated catalog number
    ("collectors", "Smith", "Smithson", "located"),
    ("collectors", "J. Smith", "leg. J. Smith, 1948", "grounded"),     # punctuation is a boundary
    ("habitat", "oak", "oak woodland", "grounded"),
    ("habitat", "woodland", "oakwoodland", "located"),
    ("collectors", "Smith.", "Smith.x", "grounded"),                    # a literal edge that is not alphanumeric
))
def test_a_literal_must_start_and_end_on_a_token_boundary_to_be_assembled(key, literal, text, status):
    built = build((RegionSpec(text + "\nSynthetic Locality"),), (FieldSpec(key, literal),))
    [item] = candidates(built)
    assert item.status == status, item
    if status == "located":
        assert item.reason == "literal_starts_or_ends_inside_a_longer_token" and item.assembly_id is None
        assert built.graph[2] == ()
    else:
        assert len(built.graph[2]) == 1


# ---------------------------------------------------------------------------- S3: edge whitespace
@pytest.mark.parametrize("shape", ("legacy", "reading"))
@pytest.mark.parametrize(("stored", "placed"), (("J. Smith ", "J. Smith"), (" J. Smith", "J. Smith"),
    ("  J. Smith  ", "J. Smith")))
def test_edge_whitespace_is_stripped_before_placement_and_a_trimming_value_is_accepted(shape, stored, placed):
    text = "leg.  J. Smith  \nSynthetic Locality"
    built = build((RegionSpec(text),), (FieldSpec("collectors", stored, shape=shape),))
    [item] = candidates(built)
    assert (item.status, item.literal) == ("grounded", placed)
    assert built.first_reading[0].literal_text[item.start:item.end] == placed
    request = request_for(built, SpecialistRole.PARTIES)
    [assembly] = [row for row in request.assemblies if row.field_key == FieldKey.COLLECTORS]
    assert assembly.interpreted_text == placed
    resolution = literal_resolution(request, item)
    assert validate_resolution(request, resolution) == resolution


def test_a_literal_of_whitespace_only_is_no_candidate():
    built = build(fields=(FieldSpec("collectors", "   ", rows=True),))
    assert candidates(built) == ()


# ---------------------------------------------------------------------------- M1: the contract re-checks a located span
def test_the_contract_rechecks_every_non_ungrounded_span_not_only_a_grounded_one():
    """Mutation M1 of the review: with the re-check of the span deleted from the contract, every other test
    still passed, because a grounded candidate is also checked against its fragment. A LOCATED candidate has
    only this check."""
    built = build(fields=STORED)
    request = request_for(built, SpecialistRole.GEOGRAPHY)
    [item] = [row for row in request.organiser_candidates if row.field_key == FieldKey.COUNTRY]
    assert item.status == "located"
    for tampered in (
        item.model_copy(update={"start": item.start + 1, "end": item.end + 1}),
        item.model_copy(update={"end": item.end - 1}),
        item.model_copy(update={"literal": "Syntheticlanx"}),
    ):
        with pytest.raises(ValueError, match="verbatim substring of the reading it cites"):
            rebuilt(request, organiser_candidates=(tampered,))
    assert rebuilt(request, organiser_candidates=(item,)).organiser_candidates == (item,)


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
