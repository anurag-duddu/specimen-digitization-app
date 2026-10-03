"""What a specialist must cite on a real-shaped label, through the production composer.

On the ten recorded production specimens no reading line carries a field key, so the
request factory builds no event and no assembly (initial_requests._graph; Lane P E2).
The v2 prompts told a specialist to name the assemblies a lookup read; with none, a
resolved value that cites a lookup has no producer and publication refuses it
(application/projection.py lookup_evidence_producer_invalid). A human question that
also cites its evidence on the resolution or the value passes validate_resolution and
then blocks publication of the record (canonical_lineage_evidence_mapping_missing). The
v3 prompts say what to cite instead; this test runs the production composer
(compose_production_research_workflow, with production_e2e_support imported, not edited)
on a synthetic label of that shape and shows, with the real validators and producer logic:

- a scripted specialist that does what the pinned prompt text instructs is accepted
  (test_a_specialist_following_the_pinned_prompt_publishes_every_lookup_citing_value, and
  test_a_human_question_follows_the_pinned_prompts_rule_for_where_its_evidence_goes for the
  question rule alone). These two FAIL on origin/main, each for its own code, because their
  specialist reads its behaviour out of the pinned prompt text and the v2 text instructs neither
  the reading citation nor question-only evidence. The specialist also reads three sentences of the
  block (instructed()): "Cite only that one reading" (absent: it lists both readers), "character for
  character" (absent: it re-wraps the copy) and "leave literal null" (absent: a multi-line literal), so
  deleting one of them from a taxonomy or geography v3 file fails the first test, not only the byte
  freeze in test_prompt_reading_citation_v3.py. Parties and collection never cite a lookup in this
  rig, so their copy of the block is guarded by the freeze alone;
- the shapes the old prompts led to are refused, each for its own code, and the exact
  fields the citation needs are the ones the v3 text names. These tests exercise code
  the prompt change does not touch, so they pass on origin/main too: they pin the contract
  the prompt text states.

What none of this shows: that a real model follows the prompt. The scripted specialist is
not a model. One real-model run on a pilot slide tests that.

The label text is synthetic. Only its shape comes from the recorded snapshots (counts and
lengths only, read-only): two regions with two readers each, a short code line in the
first and, in the second, the locality, elevation, date and collector lines, each line 7
to 21 characters. Both regions reuse the one synthetic image's pixels.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from specimen_digitization.application.domain import FieldValue, LookupStatus, Observation, Region, ValueState
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import OperationalBlock, SyntheticAdapters, Workflow
from specimen_digitization.research_harness import native_canonical_v2, native_worker
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, HumanQuestion, ResearchScope, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.evidence import dts_policy_resolution, missing_irn_resolution
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
from specimen_digitization.research_harness.persistence import (
    DurabilityScope, ImmutableFileBlobs, SqliteStateBackend,
)
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

from production_e2e_support import (
    COLLECTION, ORG, WORKER, FakeDataConnect, GenerationBlobs, specimen_before_adjudication, worker_principal,
)

# Region 0 is a short code line; region 1 the locality, a genus, elevation, date and collector.
REGION_TEXTS = (
    "SYN-PREP-00001",
    "Chicago\nCook Co., Illinois\nUnited States\nDanaus plexippus\n600 ft.\n12 VI 1948\nA. Collector",
)
GENUS = "Danaus plexippus"
LOCALITY = {"country": "United States", "state": "Illinois", "county": "Cook", "locality": "Chicago",
    "place": "Chicago", **support.PLACEMENT}
VALUE = {FieldKey.COUNTRY: "United States", FieldKey.PROVINCE_STATE: "Illinois", FieldKey.COUNTY: "Cook",
    FieldKey.CITY: "Chicago", FieldKey.PRECISE_LOCATION: "Chicago, Cook Co., Illinois"}
GEOGRAPHY = tuple(VALUE)
# The province_state query places Chicago on the far side of the world, so the match is no_match
# and the specialist asks a person: the human question.
HUMAN = (FieldKey.PROVINCE_STATE,)
FAR = {"latitude": -33.0, "longitude": 151.0, "radius_km": 1}
CITATION_FIELDS = ("source_observation_id", "verbatim_by_observation", "settled_observation_ids",
    "input_source", "source_region_id")
# Publications, in the order the worker offers them (by field key), when every lookup-citing value is accepted.
ALL_PUBLISHED = ["taxon", "city", "country", "county", "precise_location", "province_state", "identified_by_irn"]
PRODUCER_REFUSED = "lookup_evidence_producer_invalid"


@dataclass(frozen=True)
class Behaviour:
    """What a scripted specialist puts on its resolutions."""
    fields: tuple = ()                 # the FieldValue citation fields it sets on a value that cites a lookup
    route: str = "decided_transcript"  # the input source of the fragment it takes its reading from
    question_extra: bool = False       # also cite a human question's evidence on the resolution and the value
    human_cites_reading: bool = False  # also put the reading citation on the human question's value
    literal: str | None = None         # value.literal on precise_location
    human_literal: str | None = None   # value.literal on the human question's value
    both_readers: bool = False         # also list the region's other reader (common-v1: "preserve each reader's verbatim")
    collapse_breaks: bool = False      # copy the text with its line breaks replaced by spaces


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("the offline test performs no HTTP")
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


@pytest.fixture
def refusals(monkeypatch):
    """The exceptions a publication raises. The worker turns each into
    native_publication_requires_reconciliation and logs nothing, so the codes are read here."""
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


def build_rig(tmp_path, monkeypatch, texts=REGION_TEXTS):
    # specimen_before_adjudication reads the module's LABEL_TEXT for its first region's readings.
    monkeypatch.setattr(support, "LABEL_TEXT", texts[0])
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    members = {WORKER: [{"organization_id": ORG, "collection_id": COLLECTION, "role": "operator",
        "can_view_sensitive": False}]}
    backend.grant(DurabilityScope(ORG, COLLECTION, "membership", "membership", 1, WORKER, False))
    fake = FakeDataConnect(backend, members=members)
    blobs = GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    ordinary = Workflow(repository, blobs, SyntheticAdapters(blobs, texts[0]))
    token = actor_uid.set(WORKER)
    principal = worker_principal()
    specimen = specimen_before_adjudication(blobs)
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
def unkeyed(tmp_path, monkeypatch):
    rig, token = build_rig(tmp_path, monkeypatch)
    yield rig
    actor_uid.reset(token)


@pytest.fixture
def keyed(tmp_path, monkeypatch):
    """The e2e's own label: every line is `field_key: value`, so assemblies exist."""
    rig, token = build_rig(tmp_path, monkeypatch, (support.LABEL_TEXT,))
    yield rig
    actor_uid.reset(token)


# ---------------------------------------------------------------------------- the scripted specialist
def fragment_of(request, route, containing):
    return next(item for item in request.fragments
        if item.input_source == route and containing in item.observation_text)


def citation(request, behaviour, containing):
    """The fields the behaviour sets, copied from the fragment it read, as the v3 text says to."""
    fragment = fragment_of(request, behaviour.route, containing)
    readings = [fragment]
    if behaviour.both_readers:
        readings += [item for item in request.fragments if item.region_id == fragment.region_id
            and item.observation_id != fragment.observation_id][:1]
    copied = {item.observation_id: item.observation_text.replace("\n", " ") if behaviour.collapse_breaks
        else item.observation_text for item in readings}
    full = dict(source_observation_id=fragment.observation_id, verbatim_by_observation=copied,
        settled_observation_ids=list(copied), input_source=fragment.input_source,
        source_region_id=fragment.region_id)
    return {name: full[name] for name in behaviour.fields}


def instructed(request):
    """What the pinned prompt text tells a specialist to do on a label with no assembly.

    The fields the producer block names (the text from its heading to the human question block),
    whether evidence is to go only on the question, and three sentences of the block. A specialist
    does what a sentence says and, when the sentence is absent, what a plausible model does instead:
    "Cite only that one reading" absent: it lists both readers (common-v1 says to preserve each
    reader's verbatim); "character for character" absent: it re-wraps the copy; "leave literal null"
    absent: it sets precise_location's literal to the whole multi-line locality (the geography text
    says "as written"). The v2 text has none of them."""
    text = " ".join(request.prompt.text.split())
    start = text.find("Producer and literal without an assembly (publication):")
    block = text[start:text.find("Human question evidence (publication):")] if start >= 0 else ""
    fields = tuple(name for name in CITATION_FIELDS if name in block)
    # The geography prompt asks for the written text as value.literal on a human question; the v3 block
    # grounds a one-line literal on the cited reading, so the specialist cites it when the block says so.
    return Behaviour(fields=fields, question_extra="only in question.evidence_ids" not in text,
        human_cites_reading=bool(fields), human_literal="Chicago",
        both_readers="Cite only that one reading" not in text, collapse_breaks="character for character" not in text,
        literal=None if "leave literal null" in text else "Chicago\nCook Co., Illinois")


def geography(request, key, results, behaviour):
    [result] = [item for item in results if item.coverage.source_id == "geolocate" and item.coverage.field_key == key]
    evidence = tuple(item.id for item in result.evidence)
    if result.status == LookupStatus.SUCCESS:
        [candidate] = [json.loads(raw) for raw in result.candidate_json]
        extra = {"literal": behaviour.literal} if key == FieldKey.PRECISE_LOCATION and behaviour.literal else {}
        return FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
            value_layer="verbatim" if key == FieldKey.PRECISE_LOCATION else "settled",
            value=FieldValue(state=ValueState.SUPPORTED, normalized=candidate["value"],
                authority_id=candidate["authority_id"], evidence_ids=list(evidence),
                evidence_relations=dict.fromkeys(evidence, "supports"),
                **citation(request, behaviour, "Chicago"), **extra),
            evidence_ids=evidence, reason=f"Label writes {candidate['value']}; GEOLocate confirms it")
    assert result.status == LookupStatus.NO_MATCH, result.status
    elsewhere = evidence if behaviour.question_extra else ()
    question = HumanQuestion(field_key=key, question="Which place does the label name?", reason="scoped_absence",
        coverage=(result.coverage,), evidence_ids=evidence)
    reading = citation(request, behaviour, "Chicago") if behaviour.human_cites_reading else {}
    return FieldResolution(field_key=key, work_state=WorkState.WAITING_HUMAN,
        value=FieldValue(state=ValueState.UNRESOLVED, evidence_ids=list(elsewhere), literal=behaviour.human_literal,
            **reading),
        question=question, evidence_ids=elsewhere, reason="GEOLocate no_match; a person decides")


def taxon(request, results, behaviour):
    [gbif] = [item for item in results if item.coverage.source_id == "gbif"]
    assert gbif.status == LookupStatus.SUCCESS
    candidate = json.loads(gbif.candidate_json[0])
    evidence = tuple(item.id for item in gbif.evidence)
    return FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.RESOLVED, value_layer="settled",
        value=FieldValue(state=ValueState.SUPPORTED, parsed=candidate["value"], normalized=candidate["value"],
            authority_id=candidate["authority_id"], evidence_ids=list(evidence),
            evidence_relations={item.id: item.role for item in gbif.evidence},
            **citation(request, behaviour, GENUS)),
        evidence_ids=evidence,
        source_coverage=tuple(item.coverage for item in results if item.coverage.field_key == FieldKey.TAXON),
        reason="GBIF COL XR exact match of the label's name")


def specialist_factory(log, behaviour=None):
    """A scripted specialist for the unkeyed label. ``behaviour`` None: it does what the pinned prompt
    instructs (instructed). A Behaviour: exactly that, whatever the prompt says. A callable: its result
    for the request, so a test can take one rule from the prompt and fix the other."""
    def factory(request, binding):
        role = request.role

        def respond(messages, info):
            log.append((str(role), 1 + sum(isinstance(message, ModelResponse) for message in messages)))
            chosen = (instructed(request) if behaviour is None else behaviour(request) if callable(behaviour)
                else behaviour)
            results, attempted = support._results(messages)
            if role == SpecialistRole.TAXONOMY and attempted < len(support.TAXONOMY_SOURCES):
                source = support.TAXONOMY_SOURCES[attempted]
                return ModelResponse(parts=[ToolCallPart("lookup_source", {"query": {
                    "source_id": source, "field_key": "taxon", "query_text": GENUS}},
                    tool_call_id=f"unkeyed-taxon-{source}")], usage=support.USAGE)
            if role == SpecialistRole.GEOGRAPHY and not attempted:
                calls = []
                for key in GEOGRAPHY:
                    query = {**LOCALITY, "value": VALUE[key], **(FAR if key in HUMAN else {})}
                    calls.append(ToolCallPart("lookup_source", {"query": {"source_id": "geolocate",
                        "field_key": str(key), "query_text": json.dumps(query)}},
                        tool_call_id=f"unkeyed-geolocate-{key}"))
                return ModelResponse(parts=calls, usage=support.USAGE)
            resolutions = []
            for key in request.field_keys:
                if key == FieldKey.IDENTIFIED_BY_IRN:
                    resolutions.append(missing_irn_resolution())
                elif key == FieldKey.VERBATIM_DTS:
                    resolutions.append(dts_policy_resolution(None))
                elif key == FieldKey.TAXON:
                    resolutions.append(taxon(request, results, chosen))
                elif key in GEOGRAPHY:
                    resolutions.append(geography(request, key, results, chosen))
                else:
                    resolutions.append(FieldResolution(field_key=key, work_state=WorkState.WAITING_SOURCE,
                        value=FieldValue(), reason="the label does not support a value for this field"))
            output = SpecialistOutput(role=role, resolutions=tuple(resolutions))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output.model_dump(mode="json"),
                tool_call_id=f"unkeyed-{role.value}-output")], usage=support.USAGE)

        return FunctionModel(respond)
    return factory


# ---------------------------------------------------------------------------- driving the composer
def supervised():
    return WorkerDeadline(time.monotonic() + 600).scope()


def run_research(rig, factory, source_transport=None):
    """Plan to research: the specimen as the worker's plan tick leaves it, or the hold it raised.
    Returns (parsed specimen, specimen, hold, published fields in publication order)."""
    workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=WORKER, state_backend=rig.backend,
        model_factory=factory, source_transport=source_transport or support.fixture_source_transport(rig.source_urls),
        blobs=rig.research_blobs)
    with supervised():
        workflow.step(rig.principal, rig.specimen_id)
        parsed = workflow.step(rig.principal, rig.specimen_id)
    assert rig.ordinary.next_step(parsed.run) == "plan" and len(parsed.run.fields) == 20
    hold = None
    try:
        with supervised():
            specimen = workflow.step(rig.principal, rig.specimen_id)
    except OperationalBlock as block:
        hold, specimen = block, rig.repository.get(rig.principal.scope, rig.specimen_id)
    receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    return parsed, specimen, hold, [row["causal_proof"]["changed_field"] for row in receipts]


def region_reading(parsed, containing):
    """(observation id, region id) of the decided reading in the region whose text holds ``containing``."""
    transcript = next(item for item in parsed.run.transcripts if containing in item.text)
    return transcript.selected_observation_id, transcript.region_id


# ---------------------------------------------------------------------------- the premise
def test_the_label_gives_the_request_readings_of_both_input_sources_and_no_event_or_assembly(unkeyed):
    workflow = compose_production_research_workflow(unkeyed.ordinary, repository=unkeyed.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=WORKER, state_backend=unkeyed.backend,
        model_factory=specialist_factory([]), source_transport=support.fixture_source_transport([]),
        blobs=unkeyed.research_blobs)
    with supervised():
        workflow.step(unkeyed.principal, unkeyed.specimen_id)
        parsed = workflow.step(unkeyed.principal, unkeyed.specimen_id)
    scope = ResearchScope(organization_id=ORG, collection_id=COLLECTION, specimen_id=unkeyed.specimen_id,
        job_id="job", generation=1, input_digest="e" * 64, profile_digest="f" * 64, sensitive=False)
    fragments, events, assemblies, _, _ = NativeGenerationRequestFactory._graph(parsed, scope)
    assert events == () and assemblies == ()
    # The decided transcript and the other reader's raw reading: two input sources, so a lookup's
    # producer cannot come from "the" source of the request (native_input_context_v2).
    assert {item.input_source for item in fragments} == {"decided_transcript", "raw_reading"}
    assert len({item.region_id for item in fragments}) == 2


# ---------------------------------------------------------------------------- the prompt-derived behaviour
def test_a_specialist_following_the_pinned_prompt_publishes_every_lookup_citing_value(unkeyed, refusals):
    """FAILS on origin/main: its v2 text names no citation, so the scripted specialist cites nothing
    and the first publication is refused with lookup_evidence_producer_invalid."""
    parsed, specimen, hold, published = run_research(unkeyed, specialist_factory(unkeyed.model_calls))
    assert refusals == [], f"a publication was refused: {refusals}"
    assert published == ALL_PUBLISHED
    # The literal fields wait on a source here (a separate, known state of unkeyed labels), so the
    # record is held for that and for nothing a publication did.
    assert hold is None or str(hold) == "native_research_operational_hold"
    # Each lookup a published value cites has a producer row of the decided input source, and its input
    # lineage names the reading the specialist cited. (A decided producer row in a request of several
    # regions carries no transcription or observation id of its own; the lineage row keeps the reading.)
    observation, _ = region_reading(parsed, "Chicago")
    producers = [row for row in unkeyed.fake.tables["tool_call"].values() if row["tool"] == "source_lookup"]
    lineages = list(unkeyed.fake.tables["tool_input_lineage_v2"].values())
    assert len(producers) == len(lineages) >= 5
    assert {row["inputSource"] for row in producers} == {"decided_transcript"}
    assert {row["selectedObservationId"] for row in lineages} == {observation}


# ---------------------------------------------------------------------------- the shapes the old prompts led to
def test_a_human_question_follows_the_pinned_prompts_rule_for_where_its_evidence_goes(unkeyed, refusals):
    """FAILS on origin/main, for the second reason: this specialist always cites the reading (so the
    lookups have producers) and takes only where a question's evidence goes from the prompt text. The
    v2 text does not say, the specialist cites it on the resolution and the value too, and the record's
    next publication after the question's field fails with canonical_lineage_evidence_mapping_missing."""
    fixed = Behaviour(fields=CITATION_FIELDS, human_cites_reading=True)
    parsed, specimen, hold, published = run_research(unkeyed, specialist_factory(unkeyed.model_calls,
        lambda request: replace(fixed, question_extra=instructed(request).question_extra)))
    assert refusals == [], f"a publication was refused: {refusals}"
    assert published == ALL_PUBLISHED


def test_a_resolution_citing_no_reading_has_no_producer_and_nothing_publishes(unkeyed, refusals):
    parsed, specimen, hold, published = run_research(unkeyed, specialist_factory(unkeyed.model_calls, Behaviour()))
    assert refusals == [PRODUCER_REFUSED]
    assert published == [] and str(hold) == "native_publication_requires_reconciliation"


@pytest.mark.parametrize(("missing", "refused"), [
    ("source_observation_id", PRODUCER_REFUSED),
    ("verbatim_by_observation", "canonical_lineage_selected_reading_unproved"),
    ("settled_observation_ids", "canonical_lineage_selected_reading_unproved"),
    ("source_region_id", "canonical_lineage_selected_transcription_unproved"),
])
def test_each_of_these_fields_is_needed_when_the_reading_is_a_decided_transcript(unkeyed, refusals, missing, refused):
    fields = tuple(name for name in CITATION_FIELDS if name != missing)
    parsed, specimen, hold, published = run_research(unkeyed,
        specialist_factory(unkeyed.model_calls, Behaviour(fields=fields)))
    assert refusals == [refused]
    assert published == [] and str(hold) == "native_publication_requires_reconciliation"


@pytest.mark.parametrize("breakage", [
    # common-v1 says to preserve each reader's verbatim: listing the other reader beside a decided input_source.
    {"both_readers": True},
    # A copy with its line breaks turned into spaces is not a substring of the reading.
    {"collapse_breaks": True},
], ids=["lists_the_other_reader", "copy_with_collapsed_line_breaks"])
def test_a_second_reader_or_a_changed_copy_is_refused_at_publication_with_no_retry(unkeyed, refusals, breakage):
    """The two sentences the v3 text adds after the review of #257. Validators do not look at the citation
    before publication, so the specialist's run ends cleanly and the first publication is the first refusal."""
    parsed, specimen, hold, published = run_research(unkeyed,
        specialist_factory(unkeyed.model_calls, Behaviour(fields=CITATION_FIELDS, **breakage)))
    assert refusals == ["canonical_lineage_reading_unproved"]
    assert published == [] and str(hold) == "native_publication_requires_reconciliation"


def test_the_input_source_is_optional_and_a_raw_reading_needs_only_three_fields(unkeyed, refusals):
    needed = ("source_observation_id", "verbatim_by_observation", "settled_observation_ids")
    parsed, specimen, hold, published = run_research(unkeyed,
        specialist_factory(unkeyed.model_calls, Behaviour(fields=needed, route="raw_reading")))
    assert refusals == [] and published == ALL_PUBLISHED


@pytest.mark.parametrize(("behaviour", "refused", "published_before"), [
    # The question's evidence also on the resolution and the value, no reading on the question's value: the
    # question's own lookup evidence has no producer.
    (Behaviour(fields=CITATION_FIELDS, question_extra=True), PRODUCER_REFUSED,
        ["city", "country", "county", "precise_location"]),
    # With the reading on it too, the field publishes and the next publication of the record fails: the
    # question's candidate-less field has no evidence mapping for the ids it cites.
    (Behaviour(fields=CITATION_FIELDS, question_extra=True, human_cites_reading=True),
        "canonical_lineage_evidence_mapping_missing", ["city", "country", "county", "precise_location",
        "province_state"]),
])
def test_a_human_question_citing_evidence_off_the_question_blocks_the_record(unkeyed, refusals, behaviour, refused,
        published_before):
    parsed, specimen, hold, published = run_research(unkeyed, specialist_factory(unkeyed.model_calls, behaviour))
    assert refusals == [refused]
    assert [item for item in published if item != "taxon"] == published_before
    assert "identified_by_irn" not in published and str(hold) == "native_publication_requires_reconciliation"


def test_a_literal_over_several_lines_is_unproved_without_an_assembly(unkeyed, refusals):
    """Why the v3 text says to leave value.literal null for text over several lines."""
    behaviour = Behaviour(fields=CITATION_FIELDS, literal="Chicago\nCook Co., Illinois")
    parsed, specimen, hold, published = run_research(unkeyed, specialist_factory(unkeyed.model_calls, behaviour))
    assert refusals == ["canonical_lineage_literal_unproved"]
    assert "precise_location" not in published and str(hold) == "native_publication_requires_reconciliation"


def test_a_literal_on_a_human_question_needs_the_reading_cited(unkeyed, refusals):
    behaviour = Behaviour(fields=CITATION_FIELDS, human_literal="Chicago")
    parsed, specimen, hold, published = run_research(unkeyed, specialist_factory(unkeyed.model_calls, behaviour))
    assert refusals == ["canonical_lineage_literal_unproved"]
    assert "province_state" not in published and str(hold) == "native_publication_requires_reconciliation"


# ---------------------------------------------------------------------------- a label with assemblies
def test_where_assemblies_exist_naming_them_is_the_producer_and_a_reading_of_another_source_breaks_it(keyed, refusals):
    """The keyed e2e label: the geography specialist names the assemblies (production_e2e_support), as
    the v2 text and the v3 text both say. Also citing a raw reading, a different input source from the
    assemblies' decided transcript, leaves two grounding sources and no producer: the v3 text says
    'not both'. (test_production_e2e covers the assemblies-only success.)"""
    base = support.scripted_model_factory(keyed.model_calls, geolocate=True)

    def factory(request, binding):
        model = base(request, binding)
        if request.role != SpecialistRole.GEOGRAPHY:
            return model

        def respond(messages, info):
            response = model.function(messages, info)
            for part in response.parts:
                if part.tool_name == info.output_tools[0].name:
                    for item in part.args["resolutions"]:
                        if item["work_state"] == "resolved":
                            fragment = next(row for row in request.fragments if row.input_source == "raw_reading")
                            item["value"].update(source_observation_id=fragment.observation_id,
                                verbatim_by_observation={fragment.observation_id: fragment.observation_text},
                                settled_observation_ids=[fragment.observation_id])
            return response
        return FunctionModel(respond)

    parsed, specimen, hold, published = run_research(keyed, factory)
    assert refusals == [PRODUCER_REFUSED]
    assert published == ["taxon"] and str(hold) == "native_publication_requires_reconciliation"
