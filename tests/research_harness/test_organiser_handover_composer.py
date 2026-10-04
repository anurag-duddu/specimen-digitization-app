"""The hand-over through the production composer: a real-shaped UNKEYED label, an ordinary extractor
that stored field values, and a specialist that follows the pinned v5 text.

Before the hand-over (the stack head, #252's v4 prompts) the specialists saw every reading line and not
the values the ordinary extractor had stored, the request held no assembly on an unkeyed label, and so
the catalog number and the collectors could only end waiting_policy (needs human review with
mandatory_unresolved). With it, the extractor's values are handed over as organiser candidates, the five
literal fields whose value trusted code finds verbatim in one line of the decided reading come with an
accepted assembly, and a specialist that verifies the candidate against the raw readings and cites that
assembly resolves the field with evidence, through the real validator and the real publication.

The label is abstract synthetic text; only its shape comes from the ten recorded snapshots (counts and
lengths): two regions, two readers each; a short catalog region; the other lines one value each; the
extractor quotes the whole region transcript, as it does in all 48 recorded rows. The ordinary extractor
here is the real ``apply_candidates`` (verbatim check, #256's guard, one native evidence row per candidate)
fed scripted candidates: not a model.

What this proves and what it does not: with the real validators and publication, a scripted specialist that
does what the v5 text says is accepted; a specialist that resolves a hint, or omits a field the text asks
for, is refused. It does not show that a real model follows the text (the canary does).

The specialist is the base specialist of test_unkeyed_label_review (geography through GEOLocate, taxon,
dates, elevations and verbatim_dts as the v4 text says) with one overlay: it reads the hand-over sentences
out of its pinned prompt text (``followed``) and applies them to the candidates in its request.
"""
from __future__ import annotations

import hashlib
import json
from types import MappingProxyType, SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
import test_unkeyed_label_review as review
from specimen_digitization.application.domain import FieldValue, Observation, Region, ValueState
from specimen_digitization.application.harness import ExtractionCandidate, ExtractionOutput, apply_candidates
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.workflow import OperationalBlock, SyntheticAdapters, Workflow
from specimen_digitization.research_harness import native_canonical_v2, native_worker, prompts
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, ResearchScope, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import catalog_literal
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
from specimen_digitization.research_harness.persistence import (
    DurabilityScope, ImmutableFileBlobs, SqliteStateBackend,
)

from production_e2e_support import (
    COLLECTION, ORG, WORKER, FakeDataConnect, GenerationBlobs, research_state, specimen_before_adjudication,
    worker_principal,
)

# Region 0 is decided by the first pass (the second reader misreads one letter of the habitat line);
# region 1 is two agreeing readers. Both hold plain lines, no `field_key:` prefix. The collector's line
# ends with a sex sign (U+2642, which the recorded labels carry) and its name has an accented letter: the
# extractor quotes the whole region, so its evidence row holds non-ASCII text, and the value that cites that
# row, itself non-ASCII, must still publish.
REGION_TEXTS = (
    "Chicago, Cook County\nIllinois, United States\ngrassland margin",
    "FMNH INS\n0010001\nSynthetic Coll\u00e9ctor \u2642\n12 June 1948\n1200 ft\nlight trap",
)
# (field, literal, region): what the scripted ordinary extractor stores. Each literal is inside its own
# region's decided text, and the quote is the whole transcript, as the real extractor's is.
STORED = (
    ("country", "United States", 0), ("province_state", "Illinois", 0), ("county", "Cook", 0),
    ("city", "Chicago", 0), ("habitat", "grassland margin", 0),
    ("fmnh_ins_number", "0010001", 1), ("collectors", "Synthetic Coll\u00e9ctor", 1),
    ("date_visited_from", "12 June 1948", 1), ("elevation_from_ft", "1200", 1),
    ("collection_method", "light trap", 1),
    # Two lines: the extractor's own quote allows it, trusted code cannot place it in one line.
    ("collection_code", "1200 ft\nlight trap", 1),
)
GROUNDED = ("fmnh_ins_number", "collectors", "collection_method", "habitat")
RESOLVED_FROM_ASSEMBLY = ("fmnh_ins_number", "collectors", "collection_method")  # habitat: the readers disagree
ELIGIBLE = {"fmnh_ins_number", "collection_code", "habitat", "collection_method", "collectors"}


class ExtractorAdapters(SyntheticAdapters):
    """The ordinary chain's extract step, with scripted candidates through the real apply_candidates.

    ``extract`` is hidden from the step's first ``hasattr`` (so the step is not metered as an external,
    billable one: the program ledger and the provider circuit are not modelled here) and visible at the
    call, as the rehearsal rig's FakeAdapters does."""

    def __init__(self, blobs, text, stored):
        super().__init__(blobs, text)
        self.stored, self._seen = stored, 0

    def __getattr__(self, name):
        if name != "extract":
            raise AttributeError(name)
        self._seen += 1
        if self._seen < 2:
            raise AttributeError(name)
        return self._extract

    def _extract(self, specimen):
        run = specimen.run
        decided = {item.region_id: item.text for item in run.transcripts if item.resolved and item.text}
        candidates = [ExtractionCandidate(field_key=key, region_id=run.regions[region].id, literal=literal,
            source_excerpt=decided[run.regions[region].id]) for key, literal, region in self.stored]
        raw = json.dumps({"scripted_extraction": True}).encode()
        apply_candidates(run, specimen.asset.id, ExtractionOutput(candidates=candidates), self.blobs.put(raw),
            hashlib.sha256(raw).hexdigest())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("the offline test performs no HTTP")
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


@pytest.fixture
def refusals(monkeypatch):
    """The exceptions a publication raises (the worker turns each into native_publication_requires_reconciliation)."""
    caught = []
    original_prepare = native_worker.prepare_native_publication
    original_publish = native_canonical_v2.SqlConnectCanonicalResearchWriterV2.publish_checkpoint

    async def prepare(*args, **kwargs):
        try:
            return await original_prepare(*args, **kwargs)
        except Exception as error:
            caught.append(str(error))
            raise

    async def publish(self, *args, **kwargs):
        try:
            return await original_publish(self, *args, **kwargs)
        except Exception as error:
            caught.append(str(error))
            raise
    monkeypatch.setattr(native_worker, "prepare_native_publication", prepare)
    monkeypatch.setattr(native_canonical_v2.SqlConnectCanonicalResearchWriterV2, "publish_checkpoint", publish)
    return caught


def build_rig(tmp_path, monkeypatch, stored=STORED, texts=REGION_TEXTS):
    # specimen_before_adjudication reads the module's LABEL_TEXT for region 0's readings and, with first_pass,
    # has the second reader misread 'grassland' and the first pass decide for the first reader.
    monkeypatch.setattr(support, "LABEL_TEXT", texts[0])
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    members = {WORKER: [{"organization_id": ORG, "collection_id": COLLECTION, "role": "operator",
        "can_view_sensitive": False}]}
    backend.grant(DurabilityScope(ORG, COLLECTION, "membership", "membership", 1, WORKER, False))
    fake = FakeDataConnect(backend, members=members)
    blobs = GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    ordinary = Workflow(repository, blobs, ExtractorAdapters(blobs, texts[0], stored))
    token = actor_uid.set(WORKER)
    principal = worker_principal()
    specimen = specimen_before_adjudication(blobs, first_pass=True)
    run, first = specimen.run, specimen.run.regions[0]
    for order, text in enumerate(texts[1:], start=1):
        region = Region(asset_id=specimen.asset.id, x=0, y=0, width=first.width, height=first.height, order=order,
            method="synthetic_fixture_region", version="1", crop_ref=first.crop_ref)
        run.regions.append(region)
        for route in run.profile.routes:
            raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
            run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
                provider="synthetic", prompt_version=hashlib.sha256(("prompt:" + route).encode()).hexdigest(),
                input_sha256=run.observations[0].input_sha256, input_asset_id=specimen.asset.id,
                input_crop_ref=region.crop_ref, literal_text=text, raw_ref=blobs.put(raw),
                raw_sha256=hashlib.sha256(raw).hexdigest()))
        run.completed_steps += [f"transcribe:{region.id}:{route}" for route in run.profile.routes]
    created = repository.create(principal, specimen, "e2e-intake", "e2e-intake")
    rig = SimpleNamespace(fake=fake, backend=backend, repository=repository, ordinary=ordinary,
        principal=principal, specimen_id=created.id, research_blobs=ImmutableFileBlobs(tmp_path / "research"),
        model_calls=[], source_urls=[])
    return rig, token


@pytest.fixture
def rig(tmp_path, monkeypatch):
    made, token = build_rig(tmp_path, monkeypatch)
    yield made
    actor_uid.reset(token)


# ---------------------------------------------------------------------------- the specialist's overlay
# The sentences of the pinned v5 hand-over block the specialist acts on. A specialist does what a sentence
# says and, when the sentence is absent, what a plausible model does instead: it leaves the field out.
SENTENCES = {
    "verifies": "reject it if the readings do not support it as the value of that field",
    "assembly": "assembly_ids = [its assembly_id], event_id = its event_id",
    "evidence": "evidence_ids = the assembly's evidence_ids",
    "literal": "value.literal = the assembly's interpreted_text copied exactly",
    "relations": 'value.evidence_relations mapping each evidence id to "supports"',
    "verbatim": "value.verbatim_by_observation = {the candidate's observation_id: that reading's observation_text, "
                "copied character for character}",
    "settled": "value.settled_observation_ids = [that observation_id]",
}


def followed(request):
    text = " ".join(request.prompt.text.split())
    return {name: sentence in text for name, sentence in SENTENCES.items()}


def candidates_of(request):
    return getattr(request, "organiser_candidates", ())


def supported(request, candidate):
    """The scripted verification: every reader's reading of the region prints the literal."""
    readings = {row.observation_id: row.observation_text for row in request.fragments
        if row.region_id == candidate.region_id}
    return all(candidate.literal in text for text in readings.values())


def from_assembly(request, candidate, rules, *, omit=()):
    assembly = next(item for item in request.assemblies if item.id == candidate.assembly_id)
    fragment = next(item for item in request.fragments if item.id == candidate.fragment_id)
    written = assembly.interpreted_text
    settled = catalog_literal(written) if candidate.field_key == FieldKey.FMNH_INS_NUMBER else written
    value = dict(state=ValueState.SUPPORTED, parsed=settled, normalized=settled)
    if rules["literal"]:
        value["literal"] = written
    if rules["evidence"]:
        value["evidence_ids"] = list(assembly.evidence_ids)
    if rules["relations"]:
        value["evidence_relations"] = dict.fromkeys(assembly.evidence_ids, "supports")
    if rules["verbatim"] and "verbatim" not in omit:
        value["verbatim_by_observation"] = {fragment.observation_id: fragment.observation_text}
    if rules["settled"] and "settled" not in omit:
        value["settled_observation_ids"] = [fragment.observation_id]
    return FieldResolution(field_key=candidate.field_key, work_state=WorkState.RESOLVED,
        value=FieldValue(**value), evidence_ids=assembly.evidence_ids if rules["evidence"] else (),
        assembly_ids=(assembly.id,) if rules["assembly"] else (),
        event_id=assembly.event_id if rules["assembly"] else None,
        reason="The extractor's value is in the readings and the other reader prints it too")


def rejected(candidate, why):
    return FieldResolution(field_key=candidate.field_key, work_state=WorkState.WAITING_POLICY,
        value=FieldValue(state=ValueState.UNRESOLVED),
        reason=f"missing_policy:{review.POLICY} the readings do not support the candidate: {why}")


def hand_over(base_factory, *, follow=True, omit=(), resolve_hints=False, decisions=None, drop=()):
    """The base specialist, with the v5 hand-over applied to the candidates in its request.

    ``drop`` names sentences of the text the specialist does not act on (as if the text lacked them)."""
    def factory(request, binding):
        model = base_factory(request, binding)
        rules = {**followed(request), **dict.fromkeys(drop, False)}

        def respond(messages, info):
            response = model.function(messages, info)
            part = response.parts[-1]
            if not (isinstance(part, ToolCallPart) and part.tool_name == info.output_tools[0].name):
                return response  # a lookup turn
            output = SpecialistOutput.model_validate(part.args)
            resolutions = []
            for resolution in output.resolutions:
                mine = [item for item in candidates_of(request) if item.field_key == resolution.field_key]
                grounded = [item for item in mine if item.status == "grounded"]
                hints = [item for item in mine if item.status == "ungrounded"]
                if follow and rules["verifies"] and grounded and resolution.work_state == WorkState.WAITING_POLICY:
                    [candidate] = grounded
                    if supported(request, candidate):
                        resolution = from_assembly(request, candidate, rules, omit=omit)
                        (decisions if decisions is not None else []).append((str(candidate.field_key), "resolved"))
                    else:
                        resolution = rejected(candidate, "the other reader prints a different line")
                        (decisions if decisions is not None else []).append((str(candidate.field_key), "rejected"))
                elif resolve_hints and hints and resolution.work_state == WorkState.WAITING_POLICY:
                    # A specialist that treats a hint as a value: no assembly exists to cite.
                    hint = hints[0]
                    resolution = FieldResolution(field_key=hint.field_key, work_state=WorkState.RESOLVED,
                        value=FieldValue(state=ValueState.SUPPORTED, literal=hint.literal, parsed=hint.literal,
                            normalized=hint.literal), evidence_ids=("native-evidence:none",),
                        reason="the extractor wrote it")
                resolutions.append(resolution)
            new = SpecialistOutput(role=output.role, resolutions=tuple(resolutions))
            return ModelResponse(parts=[ToolCallPart(part.tool_name, new.model_dump(mode="json"),
                tool_call_id=part.tool_call_id)], usage=response.usage)
        return FunctionModel(respond)
    return factory


def to_plan(workflow, rig):
    """The ordinary chain to the plan step: adjudicate (the first pass decides region 0), then parse."""
    with review.supervised():
        for _ in range(6):
            parsed = workflow.step(rig.principal, rig.specimen_id)
            if rig.ordinary.next_step(parsed.run) == "plan":
                break
    assert rig.ordinary.next_step(parsed.run) == "plan" and len(parsed.run.fields) == 20
    return parsed


def run(rig, factory, source_transport=None):
    """Plan to research: (parsed specimen, specimen as the plan tick leaves it, the hold it raised or None)."""
    workflow = review.compose(rig, factory, source_transport or review.transport(rig.source_urls))
    parsed = to_plan(workflow, rig)
    try:
        with review.supervised():
            return parsed, workflow.step(rig.principal, rig.specimen_id), None
    except OperationalBlock as hold:
        return parsed, rig.repository.get(rig.principal.scope, rig.specimen_id), hold


def reasons_of(specimen):
    return set(specimen.run.reasons)


# ---------------------------------------------------------------------------- the premise
def test_the_ordinary_extractor_stored_the_values_and_the_request_graph_now_holds_their_assemblies(rig):
    """The shape of a recorded unkeyed label: every stored value quotes its whole region, no line is keyed.
    FAILS on the stack head: the graph has no event and no assembly for any of them."""
    parsed = to_plan(review.compose(rig, review.specialist_factory([]), review.transport([])), rig)
    stored = {key: value for key, value in parsed.run.fields.items() if value.state == "supported"}
    assert set(stored) == {key for key, _, _ in STORED}
    assert {row.excerpt for row in parsed.run.evidence} == {item.text for item in parsed.run.transcripts}
    scope = ResearchScope(organization_id=ORG, collection_id=COLLECTION, specimen_id=rig.specimen_id,
        job_id="job", generation=1, input_digest="e" * 64, profile_digest="f" * 64, sensitive=False)
    fragments, events, assemblies, _, _ = NativeGenerationRequestFactory._graph(parsed, scope)
    accepted = [row for row in events if row.status == "accepted"]
    assert {str(row.field_key) for row in assemblies} == set(GROUNDED)
    assert len(accepted) == len(assemblies) == len(GROUNDED)
    texts = {str(row.field_key): row.interpreted_text for row in assemblies}
    assert texts == {"fmnh_ins_number": "0010001", "collectors": "Synthetic Coll\u00e9ctor",
        "collection_method": "light trap", "habitat": "grassland margin"}


# ---------------------------------------------------------------------------- with the hand-over
def test_a_specialist_following_the_v5_text_resolves_the_grounded_candidates_with_evidence(rig, refusals):
    """FAILS on the stack head: the request has no candidate and no assembly, so fmnh_ins_number, collectors
    and collection_method end waiting_policy (mandatory_unresolved), as every literal field did."""
    decisions = []
    parsed, specimen, hold = run(rig, hand_over(review.specialist_factory(rig.model_calls), decisions=decisions))
    assert refusals == [], f"a publication was refused: {refusals}"
    assert hold is None, hold
    assert (specimen.run.stage, specimen.run.disposition) == ("finalized", "needs_human_review")
    # The scripted specialist verified each candidate against both readers: the catalog number, the collector
    # and the method are printed by both; the habitat line is not (reader 2 misread it), so it is rejected.
    assert sorted(decisions) == [("collection_method", "resolved"), ("collectors", "resolved"),
        ("fmnh_ins_number", "resolved"), ("habitat", "rejected")]
    reasons = reasons_of(specimen)
    held = {reason.split(":", 1)[1] for reason in reasons if reason.startswith("mandatory_unresolved:")}
    assert held == {"date_visited_from", "date_visited_to", "date_identified", "elevation_from_m", "elevation_to_m",
        "elevation_from_ft", "elevation_to_ft", "collection_code", "habitat", "taxon", "verbatim_dts"}
    assert not [reason for reason in reasons if reason.startswith(("research_work:", "canonical_"))]
    # The three published values are the extractor's literals, now with research evidence behind them.
    receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    published = [row["causal_proof"]["changed_field"] for row in receipts]
    assert {"fmnh_ins_number", "collectors", "collection_method"} <= set(published)
    assert "habitat" not in published and "collection_code" not in published
    assert published[-1] == "identified_by_irn"
    fields = specimen.run.fields
    assert (fields["fmnh_ins_number"].literal, fields["fmnh_ins_number"].normalized) == ("0010001", "0010001")
    assert fields["collectors"].literal == "Synthetic Coll\u00e9ctor" and fields["collection_method"].literal == "light trap"
    for key in RESOLVED_FROM_ASSEMBLY:
        assert fields[key].state == "supported" and fields[key].evidence_relations
    _, state = research_state(rig.fake, rig.specimen_id)
    job = list(state["jobs"].values())[0]
    assert {key: job["fields"][key]["work_state"] for key in (*GROUNDED, "collection_code", "date_visited_from",
        "elevation_from_ft")} == {"fmnh_ins_number": "resolved", "collectors": "resolved",
        "collection_method": "resolved", "habitat": "waiting_policy", "collection_code": "waiting_policy",
        "date_visited_from": "waiting_policy", "elevation_from_ft": "waiting_policy"}
    # The lineage of each published value names the decided transcript it was read from.
    sources = {row["researchFieldKey"]: row["readingSources"]
        for row in rig.fake.tables["canonical_value_lineage_v2"].values() if row["readingSources"]}
    assert set(RESOLVED_FROM_ASSEMBLY) <= set(sources)
    assert all(item["inputSource"] == "decided_transcript" for key in RESOLVED_FROM_ASSEMBLY for item in sources[key])
    assert not rig.fake.duplicates


def test_what_the_specialist_saw_is_the_extractors_pairs_and_the_raw_readings(rig):
    """The request of each role carries only its own fields' candidates, each with the span trusted code
    computed, and the raw readings of both readers; the ungrounded one is marked and has no assembly."""
    seen = {}

    def spy(base):
        def factory(request, binding):
            seen[request.role] = request
            return base(request, binding)
        return factory
    run(rig, spy(hand_over(review.specialist_factory(rig.model_calls))))
    assert set(seen) == set(SpecialistRole)
    for role, request in seen.items():
        assert {item.field_key for item in candidates_of(request)} <= set(request.field_keys)
        assert {row.input_source for row in request.fragments} == {"decided_transcript", "raw_reading"}
    collection = {str(item.field_key): item for item in candidates_of(seen[SpecialistRole.COLLECTION])}
    assert set(collection) == {"fmnh_ins_number", "collection_code", "habitat", "collection_method"}
    assert {key: item.status for key, item in collection.items()} == {"fmnh_ins_number": "grounded",
        "collection_method": "grounded", "habitat": "grounded", "collection_code": "ungrounded"}
    hint = collection["collection_code"]
    assert hint.reason == "literal_spans_more_than_one_line" and hint.assembly_id is None and hint.start is None
    assert not [row for row in seen[SpecialistRole.COLLECTION].assemblies if row.field_key == FieldKey.COLLECTION_CODE]
    got = collection["fmnh_ins_number"]
    reading = next(row for row in seen[SpecialistRole.COLLECTION].fragments if row.observation_id == got.observation_id)
    assert reading.input_source == "decided_transcript" and reading.observation_text[got.start:got.end] == "0010001"
    # Dates and elevations: located, no assembly.
    temporal = {str(item.field_key): item for item in candidates_of(seen[SpecialistRole.TEMPORAL])}
    measurement = {str(item.field_key): item for item in candidates_of(seen[SpecialistRole.MEASUREMENT])}
    assert temporal["date_visited_from"].status == measurement["elevation_from_ft"].status == "located"
    # (Every role gets the same graph, so the other roles' assemblies are in each request; none is for its own fields.)
    for role in (SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT, SpecialistRole.GEOGRAPHY, SpecialistRole.TAXONOMY):
        assert not [row for row in seen[role].assemblies if row.field_key in seen[role].field_keys], role
    geography = {str(item.field_key): item for item in candidates_of(seen[SpecialistRole.GEOGRAPHY])}
    assert {item.status for item in geography.values()} == {"located"}


def test_a_specialist_reading_the_v4_text_ignores_the_candidates_and_the_fields_stay_held(rig, monkeypatch):
    """Control: the request carries the candidates and assemblies either way; it is the v5 text that tells a
    specialist what to do with them. A specialist reading #252's v4 text alone is what #252 alone gives."""
    v4 = MappingProxyType({role: (f"{role.value}-v4.txt", prompts.MISSING_POLICY_PROMPT_VERSION)
        for role in SpecialistRole})
    monkeypatch.setattr(prompts, "ROLE_PROMPTS", v4)
    parsed, specimen, hold = run(rig, hand_over(review.specialist_factory(rig.model_calls)))
    assert hold is None and (specimen.run.stage, specimen.run.disposition) == ("finalized", "needs_human_review")
    held = {reason.split(":", 1)[1] for reason in reasons_of(specimen) if reason.startswith("mandatory_unresolved:")}
    assert {"fmnh_ins_number", "collectors", "collection_method", "habitat", "collection_code"} <= held
    receipts = rig.fake.receipts.values()
    assert not {row["causal_proof"]["changed_field"] for row in receipts} & {"fmnh_ins_number", "collectors"}


def test_the_sentences_the_specialist_acts_on_are_in_the_v5_text_of_the_two_roles_that_resolve_and_not_in_v4():
    pins = {role: review.pinned(role) for role in SpecialistRole}
    for role in (SpecialistRole.PARTIES, SpecialistRole.COLLECTION):
        assert all(followed(pins[role]).values()), role
        old = review.pinned(role, f"{role.value}-v4.txt")
        assert not any(followed(old).values()), role
    for role in (SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY, SpecialistRole.TEMPORAL, SpecialistRole.MEASUREMENT):
        assert followed(pins[role])["verifies"] and not followed(pins[role])["assembly"], role


@pytest.mark.parametrize("sentence", ["assembly", "reading"])
def test_a_specialist_that_leaves_out_what_the_v5_text_asks_is_refused(rig, refusals, sentence):
    """Why these two sentences are in the text. Without the assembly the validator finds no deciding authority (the
    role fails); without the reading the publication cannot ground the literal (canonical_lineage_literal_unproved).
    (Setting settled_observation_ids without verbatim_by_observation is refused too: canonical_lineage_selected_reading_unproved.)"""
    drop = ("verbatim", "settled") if sentence == "reading" else (sentence,)
    parsed, specimen, hold = run(rig, hand_over(review.specialist_factory(rig.model_calls), drop=drop))
    if sentence == "assembly":
        # The validator refuses a resolved literal with no assembly: the whole collection role fails (the
        # engine commits operational_failed for each of its fields) and the record holds.
        assert refusals == [] and isinstance(hold, OperationalBlock) and str(hold) == "native_research_operational_hold"
        _, state = research_state(rig.fake, rig.specimen_id)
        fields = list(state["jobs"].values())[0]["fields"]
        assert fields["fmnh_ins_number"]["work_state"] == "operational_failed"
        assert "fmnh_ins_number" not in {row["causal_proof"]["changed_field"] for row in rig.fake.receipts.values()}
    else:
        assert refusals == ["canonical_lineage_literal_unproved"]
        assert str(hold) == "native_publication_requires_reconciliation"


def test_a_hint_is_never_a_value_even_for_a_specialist_that_resolves_it(rig, refusals):
    """collection_code was stored as a two-line literal: an ungrounded hint, no assembly. A specialist that resolves
    it anyway is refused by the validator and the record holds: no path from a hint to a value."""
    parsed, specimen, hold = run(rig, hand_over(review.specialist_factory(rig.model_calls), resolve_hints=True))
    assert isinstance(hold, OperationalBlock) and str(hold) == "native_research_operational_hold"
    assert specimen.run.stage == "processing_blocked" and specimen.run.disposition is None
    assert "research_work:collection_code:operational_failed" in reasons_of(specimen)
    _, state = research_state(rig.fake, rig.specimen_id)
    job = list(state["jobs"].values())[0]
    assert job["fields"]["collection_code"]["work_state"] == "operational_failed"
    assert "collection_code" not in {row["causal_proof"]["changed_field"] for row in rig.fake.receipts.values()}
