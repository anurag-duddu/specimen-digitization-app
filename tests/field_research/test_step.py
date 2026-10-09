"""Field research's step: tasks, the accurate-read fast path, concurrency,
field values and evidence, derived values, the scientific rules and retry.

The resolver and the sources are scripted stand-ins for experts.make_resolver
and sources.ApprovedSources (contracts.FieldResolver, contracts.SourceTools);
the run is the ordinary workflow's own after adjudicate and parse.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import sys
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import (
    Asset, Disposition, Evidence, ExecutionPolicy, FieldValue, Lookup, LookupStatus, Observation,
    Profile, Region, Run, Specimen, ValueState,
)
from specimen_digitization.application.harness import ExtractionCandidate, ExtractionOutput, apply_candidates
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.application.policy import evaluate
from specimen_digitization.application.profile_runtime import bind_profile_rules, published_risk_registry
from specimen_digitization.application.region_pixels import region_png
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository, digest
from specimen_digitization.application.workflow import (
    FIELD_RESEARCH, OperationalBlock, SyntheticAdapters, Workflow,
)
from specimen_digitization.field_research import agreement
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS, Candidate, FieldAnswer, FieldOutcome, FieldTask, PlaceRef, Reading, SourceAnswer, SourceCandidate,
)
from specimen_digitization.field_research.step import (
    FieldResearchStep, apply_outcomes, build_tasks, finalize_fields, research_fields,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_harness"))
from production_e2e_support import COLLECTION, ORG, WORKER, worker_principal  # noqa: E402

GBIF_NAME = "Danaus plexippus (Linnaeus, 1758)"
GBIF_KEY = "5133088"
LABEL = {
    "fmnh_ins_number": "FMNH-INS 0010001",
    "collection_code": "SYNTHETIC",
    "country": "United States",
    "province_state": "Illinois",
    "county": "Cook",
    "city": "Chicago",
    "precise_location": "Synthetic teaching garden",
    "elevation_from_ft": "1500 ft",
    "habitat": "Synthetic grassland",
    "collection_method": "Synthetic net",
    "date_visited_from": "2020-06-01",
    "verbatim_dts": "Synthetic D/T/S",
    "taxon": "Danaus plexippus",
    "identified_by_irn": "synthetic:eparties:1",
    "date_identified": "2020-06-02",
}
# The collectors line is not keyed: the organiser finds it (apply_candidates).
TEXT = "\n".join(f"{key}: {value}" for key, value in LABEL.items()) + "\nleg. J. Smith"
NO_TOOLS = {key for key, tools in FIELD_TOOLS.items() if not tools} - {"identified_by_irn"}
RESEARCHED = {key for key, tools in FIELD_TOOLS.items() if tools}
TODAY = date(2026, 10, 8)


def make_specimen(blobs, text=TEXT, other=None):
    """A non-sensitive specimen at adjudicate: one label, two readers, which agree
    unless `other` is the second reader's text."""
    published = published_registry().profiles[0]
    output = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="JPEG", quality=95)
    image = output.getvalue()
    ref = blobs.put(image)
    asset = Asset(sha256=hashlib.sha256(image).hexdigest(), blob_ref=ref, media_type="image/jpeg",
        size_bytes=len(image), width=100, height=100, filename="field-research.jpeg", uploader=WORKER,
        sensitive=False)
    region = Region(asset_id=asset.id, x=0, y=0, width=100, height=100, order=0,
        method="synthetic_fixture_region", version="1")
    crop_png = region_png(Image.open(io.BytesIO(image)), region)
    region.crop_ref = blobs.put(crop_png)
    specimen = Specimen(scope=worker_principal().scope, asset=asset, run=Run(regions=[region]))
    run = specimen.run
    language = bind_profile_rules(specimen, published, published_risk_registry())
    run.profile_snapshot = published.model_dump(mode="json")
    run.profile_registry_version = published_registry().version
    run.profile = Profile(language_handling=language, id=published.id, version=published.version,
        schema_version=published.schema_version, policy_version=published.clearance_policy,
        mandatory_fields=published.mandatory_fields, routes=published.model_routes,
        first_pass_route=published.first_pass_route, synthetic=published.synthetic,
        institutional_policy_approved=published.institutional_policy_approved,
        semantics_confirmed=published.semantics_confirmed,
        execution=ExecutionPolicy(approved_cost_limit_micros=published.processing.run_cost_limit_micros,
            price_list=published.processing.price_list.model_dump(mode="json")))
    groups = {key: "mandatory" for key in published.mandatory_fields} | {
        key: "optional" for key in published.optional_fields}
    run.fields = {key: FieldValue() for key in groups}
    run.field_groups = groups
    run.coverage_confirmed = True
    run.dependencies = {"adapter": "FieldResearchTest", "synthetic": False,
        "profile_snapshot_sha256": digest(run.profile_snapshot)}
    crop = hashlib.sha256(crop_png).hexdigest()
    texts = [text] + [other or text] * (len(run.profile.routes) - 1)
    for route, written in zip(run.profile.routes, texts, strict=True):
        raw = ("SYNTHETIC FIXTURE " + route + "\n" + written).encode()
        run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
            provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop, input_asset_id=asset.id,
            input_crop_ref=region.crop_ref, literal_text=written, raw_ref=blobs.put(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest()))
    run.completed_steps = ["pin_dependencies", "classify", "quality_check", "segment"] + [
        f"transcribe:{region.id}:{route}" for route in run.profile.routes]
    if len(set(texts)) > 1:
        # The first pass picked no reading (its synthetic fixture never does).
        run.completed_steps.append(f"first_pass:{region.id}")
    run.stage = "running"
    return specimen


# The organiser's candidate for the unkeyed collectors line, in both readings.
COLLECTORS = [("collectors", name, "J. Smith", "leg. J. Smith") for name in ("1A", "1B")]


def every_field(*candidates):
    """The organiser's candidates for every keyed line both readers write, as
    the organiser gives them where no reading is decided (the keyed-line
    parser reads only a decided transcript), with `candidates` in place of
    those for their fields."""
    given = {key for key, *_ in candidates}
    keyed = [(key, name, value, f"{key}: {value}") for key, value in LABEL.items()
        if key not in given and key != "identified_by_irn" for name in ("1A", "1B")]
    return [*keyed, *(COLLECTORS if "collectors" not in given else ()), *candidates]


def build_rig(tmp_path, text=TEXT, other=None, *, decided=False, candidates=COLLECTORS):
    """The run at the plan handover after adjudicate, parse and the organiser's
    `candidates` ((field, reading, literal, quote)). With `other` the second
    reader differs; `decided` then has the first pass pick reader 1A, whose
    text becomes the label's transcript (G19); otherwise no reading is picked."""
    blobs = LocalBlobs(tmp_path / "blobs")
    repository = SQLiteRepository(tmp_path / "records.sqlite")
    clock = SimpleNamespace(now=datetime(2026, 10, 8, 12, tzinfo=timezone.utc))
    workflow = Workflow(repository, blobs, SyntheticAdapters(blobs, TEXT), clock=lambda: clock.now)
    principal = worker_principal()
    created = repository.create(principal, make_specimen(blobs, text, other), "intake", "intake")
    adjudicated = workflow.step(principal, created.id)  # adjudicate
    if decided:
        [transcript] = adjudicated.run.transcripts
        first = adjudicated.run.observations[0]
        transcript.text, transcript.resolved = first.literal_text, True
        transcript.selected_observation_id = first.id
        repository.save(principal, adjudicated, adjudicated.version, "first-pass", "first-pass")
    parsed = workflow.step(principal, created.id)  # parse
    assert workflow.next_step(parsed.run) == "plan"
    run = parsed.run
    raw = b"organiser response"
    apply_candidates(run, parsed.asset.id, ExtractionOutput(candidates=[
        ExtractionCandidate(field_key=key, reading=name, literal=literal, source_excerpt=quote)
        for key, name, literal, quote in candidates]), blobs.put(raw), hashlib.sha256(raw).hexdigest())
    parsed = repository.save(principal, parsed, parsed.version, "organiser", "organiser")
    return SimpleNamespace(blobs=blobs, repository=repository, workflow=workflow, principal=principal,
        specimen=parsed, clock=clock)


@pytest.fixture
def rig(tmp_path):
    return build_rig(tmp_path)


# The synthetic label's places as Getty TGN gives them (sources._place): each
# with its kind and the places it lies in, nearest first, named by their records.
TGN_PLACES = {
    "United States": ("nations", ()),
    "Illinois": ("states (political divisions), first level subdivisions (political entities)",
        ("United States",)),
    "Cook": ("counties, second level subdivisions (political entities)", ("Illinois", "United States")),
    "Chicago": ("inhabited places", ("Cook", "Illinois", "United States")),
}
# The larger units each place field's text lies in, as a GEOLocate query names them.
WITHIN = {"country": (), "province_state": ("United States",), "county": ("Illinois", "United States"),
    "city": ("Cook", "Illinois", "United States")}


def geolocate_query(text, key="city"):
    """A GEOLocate query for a place on the synthetic label: the text, then its larger units."""
    return ", ".join((text, *WITHIN[key]))


class FakeSources:
    """Approved sources: GBIF matches the taxon; Getty TGN the synthetic label's
    country, state and county (TGN_PLACES) and nothing else; GEOLocate any
    place, which lies in the larger units its query names; Wikidata and NGA a
    place at no level. Each distinct query is answered once and from the cache
    after, as sources.py does."""

    sources = ("gbif", "geolocate", "tgn", "wikidata", "nga")

    def __init__(self, blobs, *, down=()):
        self.blobs, self.down, self.cache = blobs, set(down), {}

    async def lookup(self, source_id, query, *, field_key):
        key = (source_id, query)
        if key not in self.cache:
            self.cache[key] = self._answer(source_id, query)
        return self.cache[key]

    def _answer(self, source_id, query):
        if source_id in self.down:
            return SourceAnswer(source_id, query, LookupStatus.PROVIDER, (), None, note="unreachable")
        raw = json.dumps({"source": source_id, "query": query}).encode()
        ref, sha = self.blobs.put(raw), hashlib.sha256(raw).hexdigest()
        if source_id == "tgn" and query in TGN_PLACES:
            kind, within = TGN_PLACES[query]
            candidate = SourceCandidate(query, f"tgn:{query}", kind, detail="in " + ", ".join(within) if within
                else None, parents=tuple(PlaceRef(name, f"tgn:{name}") for name in within))
            evidence = Evidence(kind="authority", source="tgn", locator=candidate.authority_id,
                excerpt=f"match\n{query} | {candidate.authority_id} | {kind} | {candidate.detail or ''}",
                raw_ref=ref, digest=sha)
            return SourceAnswer("tgn", query, LookupStatus.SUCCESS, (candidate,), evidence, note="match")
        if source_id == "tgn":
            evidence = Evidence(kind="lookup", source="tgn", locator=None, excerpt="Getty TGN: no match",
                raw_ref=ref, digest=sha)
            return SourceAnswer("tgn", query, LookupStatus.NO_MATCH, (), evidence, note="no match")
        if source_id == "gbif":
            candidate = SourceCandidate(name=GBIF_NAME, authority_id=GBIF_KEY, kind="SPECIES")
            evidence = Evidence(kind="authority", source="gbif", locator=GBIF_KEY,
                excerpt=f"GBIF: exact accepted match\n{GBIF_NAME} | {GBIF_KEY} | SPECIES | ", raw_ref=ref, digest=sha)
            lookup = Lookup(provider="gbif", adapter_version="test", query={"name": query},
                status=LookupStatus.SUCCESS, candidates=[{"key": GBIF_KEY, "scientificName": GBIF_NAME}],
                raw_ref=ref, digest=sha)
            return SourceAnswer("gbif", query, LookupStatus.SUCCESS, (candidate,), evidence,
                note="exact", taxonomy_lookup=lookup)
        place, *within = [part.strip() for part in query.split(",")]
        candidate = SourceCandidate(name=place, authority_id=f"{source_id}:{query}", kind="place",
            detail="in " + ", ".join(within) if within else None, parents=tuple(map(PlaceRef, within)))
        evidence = Evidence(kind="authority", source=source_id, locator=candidate.authority_id,
            excerpt=f"match\n{place} | {candidate.authority_id} | place | {candidate.detail or ''}",
            raw_ref=ref, digest=sha)
        return SourceAnswer(source_id, query, LookupStatus.SUCCESS, (candidate,), evidence, note="match")


def resolved(literal, *, value=None, authority_id=None, cited=(), reading="1A"):
    return FieldAnswer(outcome="resolved", literal=literal, reading_names=[reading], value=value,
        authority_id=authority_id, source_evidence_ids=list(cited), explanation="Settled.")


class Scripted:
    """A resolver: each field's script, recording which fields it was asked for."""

    def __init__(self, scripts=None, *, meter=None, delay=0.0, tokens=(100, 50)):
        self.scripts, self.meter, self.delay, self.tokens = dict(scripts or {}), meter, delay, tokens
        self.calls, self.spans, self.active, self.peak = [], [], 0, 0

    async def __call__(self, task, readings, context, *, tools):
        self.calls.append(task.key)
        self.active += 1
        self.peak = max(self.peak, self.active)
        started = time.monotonic()
        try:
            await asyncio.sleep(self.delay)
            if self.meter is not None:
                ticket = await self.meter.reserve(*self.tokens)
                self.meter.settle(ticket, *self.tokens)
            script = self.scripts.get(task.key, default_script)
            return await script(task, readings, tools)
        finally:
            self.active -= 1
            self.spans.append((task.key, started, time.monotonic()))


async def default_script(task, readings, tools):
    key, evidence, lookups = task.key, [], []
    if key == "taxon":
        answer = await tools.lookup("gbif", LABEL["taxon"], field_key=key)
        evidence, lookups = [answer.evidence], [answer.taxonomy_lookup]
        result = resolved(LABEL["taxon"], value=GBIF_NAME, authority_id=GBIF_KEY, cited=[answer.evidence.id])
    elif key in {"country", "province_state", "county", "city"}:
        # Getty TGN settles the country, state and county; GEOLocate only a city.
        source, query = ("geolocate", geolocate_query(LABEL[key])) if key == "city" else ("tgn", LABEL[key])
        answer = await tools.lookup(source, query, field_key=key)
        evidence = [answer.evidence]
        result = resolved(LABEL[key], authority_id=answer.candidates[0].authority_id, cited=[answer.evidence.id])
    elif key == "fmnh_ins_number":
        result = resolved(LABEL[key], value="0010001")
    elif key == "elevation_from_ft":
        # The organiser's candidate, whole; the check's number is its value.
        result = resolved(LABEL[key], value="1500")
    elif key in LABEL:
        result = resolved(LABEL[key])
    else:
        result = FieldAnswer(outcome="label_lacks_value", explanation="No reading states it.")
    return FieldOutcome(key, result, evidence=evidence, lookups=lookups, model_calls=1)


def failing(failure):
    async def script(task, readings, tools):
        answer = await tools.lookup("geolocate", LABEL.get(task.key, "x"), field_key=task.key)
        return FieldOutcome(task.key, None, failure=failure,
            evidence=[answer.evidence] if answer.evidence else [], model_calls=1)
    return script


def answering(answer):
    async def script(task, readings, tools):
        return FieldOutcome(task.key, answer, model_calls=1)
    return script


def research(rig, resolver, **kwargs):
    run = rig.specimen.run
    calls = []
    prepared = build_tasks(run)
    tools = kwargs.pop("tools", None) or FakeSources(rig.blobs)
    outcomes = asyncio.run(research_fields(run, resolver=resolver, tools=tools, prepared=prepared,
        calls=calls, **kwargs))
    return prepared, outcomes, calls


def settle(rig, resolver, **kwargs):
    """Research, apply and finalize the rig's run in memory; the blocker."""
    prepared, outcomes, calls = research(rig, resolver, **kwargs)
    apply_outcomes(rig.specimen.run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    return finalize_fields(rig.specimen.run, None, outcomes, specimen=rig.specimen, blobs=rig.blobs, today=TODAY)


def field_checks(run, keys):
    """policy.py's per-field checks (62-98) that name these fields."""
    prefixes = ("mandatory_unresolved", "evidence_missing", "evidence_does_not_support_value",
        "pixel_lineage_missing", "unsupported_parsed", "unsupported_normalized", "unsupported_authority_id")
    return [reason for reason in evaluate(run) if reason.startswith(prefixes) and reason.split(":", 1)[1] in keys]


# ---- build_tasks ------------------------------------------------------------

def test_build_tasks_names_readings_as_the_organiser_and_hands_each_field_its_candidates(rig):
    run = rig.specimen.run
    readings, tasks, context = build_tasks(run)
    decided, raw = run.observations
    assert [(r.name, r.input_source, r.observation_id) for r in readings] == [
        ("1A", "decided_transcript", run.transcripts[0].selected_observation_id or decided.id),
        ("1B", "raw_reading", raw.id)]
    assert {r.region_id for r in readings} == {run.regions[0].id} and all(r.text == TEXT for r in readings)
    by_key = {task.key: task for task in tasks}
    published = published_registry().profiles[0]
    assert list(by_key) == [*published.mandatory_fields, *published.optional_fields]
    assert by_key["taxon"].mandatory and not by_key["identified_by_irn"].mandatory
    assert all(task.tools == FIELD_TOOLS[task.key] for task in tasks)
    assert by_key["taxon"].current.literal == "Danaus plexippus"
    # The keyed-line parser's value is a candidate of each reading that writes its line.
    assert [(c.reading, c.quote, c.literal) for c in by_key["taxon"].candidates] == [
        ("1A", "taxon: Danaus plexippus", "Danaus plexippus"), ("1B", "taxon: Danaus plexippus", "Danaus plexippus")]
    collectors = by_key["collectors"]
    assert collectors.current.state == ValueState.SUPPORTED and collectors.current.literal == "J. Smith"
    assert [(c.reading, c.quote, c.literal) for c in collectors.candidates] == [
        ("1A", "leg. J. Smith", "J. Smith"), ("1B", "leg. J. Smith", "J. Smith")]
    assert set(context) == set(run.fields) and context["taxon"] == run.fields["taxon"]


def test_a_settled_field_and_a_persons_decision_are_not_researched_again(rig):
    run = rig.specimen.run
    run.fields["habitat"] = run.fields["habitat"].model_copy(update={"layer": "settled"})
    run.dependencies["preserved_human_fields"] = {"taxon": {}}
    keys = {task.key for task in build_tasks(run)[1]}
    assert "habitat" not in keys and "taxon" not in keys and "county" in keys


# ---- research_fields --------------------------------------------------------

def test_accurate_reads_finalize_without_a_model_call(rig):
    resolver = Scripted()
    _, outcomes, _ = research(rig, resolver)
    by_key = {o.key: o for o in outcomes}
    assert NO_TOOLS <= set(by_key) and not NO_TOOLS & set(resolver.calls)
    assert all(by_key[key].finalized_without_model and by_key[key].model_calls == 0 for key in NO_TOOLS)
    # Label 1's decided transcript is 1A: its other reader is evidence only (G19).
    assert by_key["collectors"].answer.literal == "J. Smith" and by_key["collectors"].answer.reading_names == ["1A"]
    # No approved authority: no model call, the nonblocking exception.
    assert "identified_by_irn" not in resolver.calls and by_key["identified_by_irn"].finalized_without_model
    assert sorted(resolver.calls) == sorted(RESEARCHED)


def test_an_accurate_read_of_a_decided_label_uses_only_its_decided_reading():
    """The second review's note: label 1's decided transcript writes no
    collector, its other reader 1B writes "leg. J. Smith", and both readers of
    label 2 write it. The organiser's supported value is an accurate read of
    label 2 (1B is evidence only), and it finalizes."""
    readings = (Reading("1A", "r1", "o1a", "decided_transcript", "Det. label\nno collector here"),
        Reading("1B", "r1", "o1b", "raw_reading", "Det. label\nleg. J. Smith"),
        Reading("2A", "r2", "o2a", "raw_reading", "Guatemala\nleg. J. Smith"),
        Reading("2B", "r2", "o2b", "raw_reading", "Guatemala\nleg. J. Smith"))
    task = FieldTask("collectors", True, FieldValue(state=ValueState.SUPPORTED, literal="J. Smith"),
        tuple(Candidate(name, "leg. J. Smith", "J. Smith", "ev-" + name) for name in ("1B", "2A", "2B")),
        FIELD_TOOLS["collectors"])
    run = SimpleNamespace(evidence=[])
    [outcome] = asyncio.run(research_fields(run, SimpleNamespace(), resolver=Scripted(), tools=FakeSources(None),
        prepared=(readings, (task,), {})))
    assert outcome.finalized_without_model and outcome.answer.outcome == "resolved"
    by_name = {reading.name: reading for reading in readings}
    assert field_step._refusal(task, outcome.answer, readings=readings, by_name=by_name, sources=()) is None
    assert (outcome.answer.literal, outcome.answer.reading_names) == ("J. Smith", ["2A", "2B"])


def test_resolvers_run_concurrently_up_to_the_limit(rig):
    every = Scripted(delay=0.05)
    research(rig, every, concurrency=20)
    assert every.peak == len(RESEARCHED)
    starts, ends = [s for _, s, _ in every.spans], [e for _, _, e in every.spans]
    assert max(starts) < min(ends)  # Every field had started before any finished.
    two = Scripted(delay=0.01)
    research(rig, two, concurrency=2)
    assert two.peak == 2 and sorted(two.calls) == sorted(RESEARCHED)


def test_research_stops_a_minute_before_the_pilots_effect_timeout():
    """The pilot's step has 270 s (its profile's external timeout): research
    stops at 210 s, leaving at least three times the measured work after it."""
    timeout = published_registry().profiles[0].processing.external_timeout_seconds
    step = FieldResearchStep(resolver_factory=None, tools_factory=None)
    assert (timeout, step._bound(timeout)) == (270.0, 210.0)
    assert step.margin_seconds >= max(60.0, 3 * field_step.POST_RESEARCH_SECONDS)


def test_a_step_stops_research_a_minute_before_its_deadline_and_keeps_what_settled(rig):
    """Through the workflow, with a 62 s effect timeout: research stops 60 s
    before it, at 2 s; the field still running is a timeout for the retry and
    every settled field is kept."""
    run = rig.specimen.run
    run.profile.execution = run.profile.execution.model_copy(update={"external_timeout_seconds": 62.0})
    rig.specimen = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "timeout", "timeout")

    async def stuck(task, readings, tools):
        await asyncio.sleep(3600)

    mounted(rig, Scripted({"taxon": stuck}))
    began = time.monotonic()
    blocked = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert 2.0 <= time.monotonic() - began < 20.0  # A 30 s margin would research for 32 s.
    assert (blocked.stage, blocked.blocker) == ("retry_scheduled", "field_research_timeout")
    assert blocked.fields["taxon"].reason == field_step.FIELD_REASONS["timeout"]
    assert {key for key, value in blocked.fields.items() if value.layer == "settled"} == RESEARCHED - {
        "taxon", "elevation_to_ft", "elevation_from_m", "elevation_to_m", "date_visited_to"}


def test_a_field_still_running_at_the_deadline_is_a_timeout(rig):
    async def stuck(task, readings, tools):
        await asyncio.sleep(30)

    _, outcomes, _ = research(rig, Scripted({"taxon": stuck}), deadline_seconds=0.2)
    by_key = {o.key: o for o in outcomes}
    assert by_key["taxon"].failure == "timeout" and by_key["county"].answer.outcome == "resolved"


def test_one_field_research_span_carries_operational_counts_only(rig, capfire):
    research(rig, Scripted({"taxon": failing("source_unavailable"),
        "county": answering(FieldAnswer(outcome="sources_cannot_resolve", explanation="No match."))}))
    [span] = [item for item in capfire.exporter.exported_spans_as_dict() if item["name"] == "field_research"]
    counts = {key: span["attributes"][key] for key in ("fields_total", "finalized_without_model", "resolved",
        "review", "failed", "nonblocking_exceptions", "model_calls", "cost_micros")}
    assert counts == {"fields_total": 20, "finalized_without_model": len(NO_TOOLS),
        # Review: county, and the three elevations and the end date the label leaves out.
        "resolved": len(NO_TOOLS) + len(RESEARCHED) - 6, "review": 5, "failed": 1, "nonblocking_exceptions": 1,
        "model_calls": len(RESEARCHED), "cost_micros": 0}
    text = json.dumps(span["attributes"])
    assert not any(value in text for value in (*LABEL.values(), GBIF_NAME))


# ---- apply_outcomes ---------------------------------------------------------

def test_settled_values_and_their_evidence_pass_the_field_checks_and_integrity(rig):
    assert settle(rig, Scripted()) is None
    run = rig.specimen.run
    settled = {key for key, value in run.fields.items() if value.layer in {"verbatim", "settled"}}
    assert settled == (NO_TOOLS | RESEARCHED) - {"elevation_to_m", "elevation_from_m", "elevation_to_ft",
        "date_visited_to"}
    assert field_checks(run, settled) == []
    verify_evidence(rig.specimen, rig.blobs)
    evidence = {item.id: item for item in run.evidence}
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.normalized, taxon.authority_id, taxon.layer) == (
        ValueState.SUPPORTED, "Danaus plexippus", GBIF_NAME, GBIF_KEY, "settled")
    assert (taxon.input_source, taxon.source_region_id) == ("decided_transcript", run.regions[0].id)
    assert not taxon.verbatim_by_observation and not taxon.settled_observation_ids
    sources = {evidence[i].source: relation for i, relation in taxon.evidence_relations.items()}
    assert sources == {"label": "supports", "gbif": "decides"}
    # A place source supports a place; each stored answer is kept with its one producing call.
    county, city = run.fields["county"], run.fields["city"]
    assert {evidence[i].source: r for i, r in county.evidence_relations.items()} == {
        "label": "supports", "tgn": "supports"}
    assert {evidence[i].source: r for i, r in city.evidence_relations.items()} == {
        "label": "supports", "geolocate": "supports"}
    places = [item for item in run.evidence if item.source in ("tgn", "geolocate")]
    assert sorted(item.source for item in places) == ["geolocate", "tgn", "tgn", "tgn"]
    assert all(sum(call.evidence_id == item.id for call in run.tool_calls) == 1 for item in places)
    gbif = [call for call in run.tool_calls if call.source == "gbif"]
    assert [(call.field_keys, call.outcome) for call in gbif] == [(["taxon"], LookupStatus.SUCCESS)]
    assert [lookup.provider for lookup in run.lookups] == ["gbif"]
    # A catalog number's digits: the check, run again, is its evidence.
    catalog = run.fields["fmnh_ins_number"]
    [check] = [evidence[i] for i in catalog.evidence_ids if evidence[i].kind == "derived"]
    assert catalog.parsed == "0010001" and "0010001" in check.excerpt and check.locator == "check:catalog_number_validator"
    # The accurate read keeps its organiser rows and is the verbatim layer.
    collectors = run.fields["collectors"]
    assert collectors.layer == "verbatim" and set(collectors.evidence_ids) <= set(evidence)


def test_a_literal_only_raw_readings_write_keeps_each_readers_verbatim(rig):
    run = rig.specimen.run
    raw = run.observations[1]
    literal = LABEL["precise_location"]
    settle(rig, Scripted({"precise_location": answering(resolved(literal, reading="1B"))}))
    place = run.fields["precise_location"]
    assert place.input_source == "raw_reading" and place.verbatim_by_observation == {raw.id: literal}
    assert place.settled_observation_ids == [raw.id] and place.source_observation_id == raw.id
    assert field_checks(run, {"precise_location"}) == [] and field_step._raw_grounded(place, run)


def test_unsettled_outcomes_keep_the_label_rows_and_say_why(rig):
    settle(rig, Scripted({
        "county": answering(FieldAnswer(outcome="sources_cannot_resolve", explanation="Two Cooks.")),
        "city": answering(FieldAnswer(outcome="several_possibilities", options=["Chicago", "Chicago Heights"],
            explanation="Both are possible.")),
        "date_identified": answering(FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")),
    }))
    fields = rig.specimen.run.fields
    assert (fields["county"].state, fields["county"].literal, fields["county"].reason) == (
        ValueState.UNRESOLVED, "Cook", "Two Cooks.")
    assert fields["city"].state == ValueState.AMBIGUOUS and fields["city"].literal is None
    assert fields["city"].reason == "Both are possible. Options: Chicago; Chicago Heights."
    assert fields["date_identified"].state == ValueState.NOT_PRESENT and fields["date_identified"].evidence_ids


def test_derived_values_fill_what_the_label_leaves_out(rig):
    settle(rig, Scripted())
    run = rig.specimen.run
    evidence = {item.id: item for item in run.evidence}
    expected = {"elevation_to_ft": ("1500", ["elevation_from_ft"]), "elevation_from_m": ("457.2", ["elevation_from_ft"]),
        "elevation_to_m": ("457.2", ["elevation_from_ft"]), "date_visited_to": ("2020-06-01", ["date_visited_from"])}
    for key, (value, sources) in expected.items():
        field = run.fields[key]
        assert (field.state, field.parsed, field.literal, field.layer, field.derived_from) == (
            ValueState.SUPPORTED, value, None, "derived", sources), key
        [derived] = [evidence[i] for i in field.evidence_ids if evidence[i].kind == "derived"
            and evidence[i].locator.startswith("derivation:")]
        assert value in derived.excerpt and field.evidence_relations[derived.id] == "decides"
        assert set(run.fields[sources[0]].evidence_ids) <= set(field.evidence_ids)
    # The stated value is never replaced.
    stated = run.fields["elevation_from_ft"]
    assert (stated.literal, stated.parsed, stated.layer) == ("1500 ft", "1500", "settled")


def test_several_possibilities_keep_the_readers_verbatim_and_its_lineage(rig):
    run = rig.specimen.run
    raw = run.observations[1]
    run.fields["city"] = run.fields["city"].model_copy(update={"literal": None,
        "verbatim_by_observation": {raw.id: "Chicago"}, "input_source_by_observation": {raw.id: "raw_reading"},
        "settled_observation_ids": [raw.id], "input_source": "raw_reading", "source_observation_id": raw.id})
    before = run.fields["city"]
    settle(rig, Scripted({"city": answering(FieldAnswer(outcome="several_possibilities",
        options=["Chicago", "Chicago Heights"], explanation="Both are possible."))}))
    city = run.fields["city"]
    assert city.state == ValueState.AMBIGUOUS and city.verbatim_by_observation == {raw.id: "Chicago"}
    assert (city.input_source_by_observation, city.settled_observation_ids, city.input_source,
        city.source_region_id, city.source_observation_id) == (before.input_source_by_observation,
        before.settled_observation_ids, "raw_reading", before.source_region_id, raw.id)
    # The reader's text is the record's candidate for a person to choose from.
    from specimen_digitization.application.projection import _fields
    rows = [w.variables for w in _fields(run, {}, set(), {}) if w.variables["fieldKey"] == "city"]
    assert [(row["literalValue"], row["inputSource"]) for row in rows] == [("Chicago", "raw_reading")]


def test_an_ambiguous_check_is_no_evidence_for_one_of_its_readings():
    texts = ["Epipsocus sp. 1\n4-5-48 coll. F. G. Werner"]
    rules = {"version": "date-rules-v1", "two_digit_year_century": 1900, "roman_numeral_months": True}
    for value in ("1948-04-05", "1948-05-04"):
        assert field_step._check_row("date_visited_from", ("date_parser",), "4-5-48", value, texts=texts,
            date_rules=rules, asset_id=None, blobs=None) is None
    row = field_step._check_row("fmnh_ins_number", ("catalog_number_validator",), "FMNH-INS 0010001",
        "0010001", texts=[TEXT], date_rules=None, asset_id=None, blobs=None)
    assert row is not None and "0010001" in row.excerpt


class TwoTaxa(FakeSources):
    """GBIF decides GBIF_NAME and lists a fuzzy alternative beside it."""

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "gbif":
            return answer
        other = SourceCandidate(name="Danaus erippus (Cramer, 1775)", authority_id="5133099", kind="SPECIES",
            detail="alternative, fuzzy match")
        evidence = answer.evidence.model_copy(update={"excerpt": answer.evidence.excerpt
            + f"\n{other.name} | {other.authority_id} | SPECIES | alternative, fuzzy match"})
        return SourceAnswer("gbif", query, LookupStatus.SUCCESS, (*answer.candidates, other), evidence,
            note="exact", taxonomy_lookup=answer.taxonomy_lookup)


def taxon_on(query, *, value=GBIF_NAME, authority_id=GBIF_KEY, literal=LABEL["taxon"]):
    async def script(task, readings, tools):
        answer = await tools.lookup("gbif", query, field_key=task.key)
        return FieldOutcome(task.key, resolved(literal, value=value, authority_id=authority_id,
            cited=[answer.evidence.id]), evidence=[answer.evidence], lookups=[answer.taxonomy_lookup], model_calls=1)
    return script


@pytest.mark.parametrize(("script", "tools"), [
    # GBIF asked about a name no reading writes.
    (taxon_on("Bombus impatiens"), FakeSources),
    # The alternative GBIF listed, not the candidate it decided.
    (taxon_on(LABEL["taxon"], value="Danaus erippus (Cramer, 1775)", authority_id="5133099"), TwoTaxa),
])
def test_a_taxon_clears_only_on_the_candidate_gbif_decided_for_its_literal(rig, script, tools):
    settle(rig, Scripted({"taxon": script}), tools=tools(rig.blobs))
    run = rig.specimen.run
    assert run.fields["taxon"].state == ValueState.SUPPORTED
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["taxonomy_unresolved"])


def test_a_taxon_query_is_the_name_its_literal_writes_or_a_genus_level_identifications_genus():
    from specimen_digitization.field_research.checks import taxon_query_grounded

    assert taxon_query_grounded("Danaus plexippus", "Danaus plexippus")
    assert taxon_query_grounded("Danaus plexippus", "Danaus plexippus (Linnaeus, 1758)")
    assert taxon_query_grounded("Epipsocus", "Epipsocus sp. 1")  # G25
    assert not taxon_query_grounded("Danaus", "Danaus plexippus")  # a species is not its genus
    assert not taxon_query_grounded("Danau", "Danaus sp.")
    assert not taxon_query_grounded("Bombus impatiens", "Danaus plexippus")
    assert not taxon_query_grounded(" ", "Danaus plexippus")
    # Part of the name the label writes is not that name (the review's B2).
    assert not taxon_query_grounded("Danaus plexippus", "Danaus plexippus megalippe")


TRINOMIAL = "Danaus plexippus megalippe"
SUBSPECIES_NAME, SUBSPECIES_KEY = "Danaus plexippus megalippe (Hubner, 1819)", "5133090"


class Subspecies(FakeSources):
    """GBIF decides the subspecies when asked the whole trinomial; the species
    (GBIF_NAME) for any other name."""

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "gbif" or query != TRINOMIAL:
            return answer
        candidate = SourceCandidate(name=SUBSPECIES_NAME, authority_id=SUBSPECIES_KEY, kind="SUBSPECIES")
        evidence = answer.evidence.model_copy(update={"locator": SUBSPECIES_KEY,
            "excerpt": f"GBIF: exact accepted match\n{SUBSPECIES_NAME} | {SUBSPECIES_KEY} | SUBSPECIES | "})
        lookup = answer.taxonomy_lookup.model_copy(update={
            "candidates": [{"key": SUBSPECIES_KEY, "scientificName": SUBSPECIES_NAME}]})
        return SourceAnswer("gbif", query, LookupStatus.SUCCESS, (candidate,), evidence, note="exact",
            taxonomy_lookup=lookup)


@pytest.mark.parametrize(("query", "value", "key", "cleared"), [
    # GBIF's decision for "Danaus plexippus": the subspecies would be lost unreviewed.
    ("Danaus plexippus", GBIF_NAME, GBIF_KEY, False),
    (TRINOMIAL, SUBSPECIES_NAME, SUBSPECIES_KEY, True),
])
def test_a_taxon_clears_only_on_gbifs_decision_for_the_whole_name_the_label_writes(
        tmp_path, query, value, key, cleared):
    rig = build_rig(tmp_path, TEXT.replace("taxon: Danaus plexippus", "taxon: " + TRINOMIAL))
    settle(rig, Scripted({"taxon": taxon_on(query, value=value, authority_id=key, literal=TRINOMIAL)}),
        tools=Subspecies(rig.blobs))
    run = rig.specimen.run
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.normalized) == (ValueState.SUPPORTED, TRINOMIAL, value)
    if cleared:
        assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    else:
        assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["taxonomy_unresolved"])


# ---- a resolved literal is a whole candidate (the second review's B2) ----------

GENUS_NAME, GENUS_KEY = "Danaus Kluk, 1780", "5133074"


class Genus(FakeSources):
    """GBIF decides the genus Danaus when asked "Danaus"; the species otherwise."""

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "gbif" or query != "Danaus":
            return answer
        candidate = SourceCandidate(name=GENUS_NAME, authority_id=GENUS_KEY, kind="GENUS")
        evidence = answer.evidence.model_copy(update={"locator": GENUS_KEY,
            "excerpt": f"GBIF: exact accepted match\n{GENUS_NAME} | {GENUS_KEY} | GENUS | "})
        lookup = answer.taxonomy_lookup.model_copy(update={
            "candidates": [{"key": GENUS_KEY, "scientificName": GENUS_NAME}]})
        return SourceAnswer("gbif", query, LookupStatus.SUCCESS, (candidate,), evidence, note="exact",
            taxonomy_lookup=lookup)


def place_on(query):
    """A place expert: one GEOLocate lookup, then its candidate with the query as the literal."""
    async def script(task, readings, tools):
        answer = await tools.lookup("geolocate", query, field_key=task.key)
        return FieldOutcome(task.key, resolved(query, authority_id=answer.candidates[0].authority_id,
            cited=[answer.evidence.id]), evidence=[answer.evidence], model_calls=1)
    return script


@pytest.mark.parametrize(("key", "written", "script", "tools"), [
    # Both readers write the trinomial; the expert asks GBIF the binomial and answers it.
    ("taxon", TRINOMIAL, taxon_on("Danaus plexippus", literal="Danaus plexippus"), Subspecies),
    # A species label answered at its genus (G25 covers only a genus-level label).
    ("taxon", "Danaus plexippus", taxon_on("Danaus", value=GENUS_NAME, authority_id=GENUS_KEY, literal="Danaus"),
        Genus),
    # The day dropped from a date, which then parses at month precision.
    ("date_visited_from", "3 Sept. '46", answering(resolved("Sept. '46", value="1946-09")), FakeSources),
    # A town cut out of the whole name, which GEOLocate then finds.
    ("city", "San Pedro Sacatepequez", place_on("San Pedro"), FakeSources),
])
def test_a_piece_of_the_text_the_label_writes_never_settles_its_field(tmp_path, key, written, script, tools):
    rig = build_rig(tmp_path, TEXT.replace(f"{key}: {LABEL[key]}", f"{key}: {written}"))
    run = rig.specimen.run
    settle(rig, Scripted({key: script}), tools=tools(rig.blobs))
    value = run.fields[key]
    assert (value.state, value.literal) == (ValueState.UNRESOLVED, written)
    assert value.reason == agreement.NOT_CANDIDATE + " Settled."
    assert run.disposition == Disposition.REVIEW and f"mandatory_unresolved:{key}" in run.reasons


class SearchesTheFirstName(FakeSources):
    """Getty TGN as sources._gazetteer asks it: only the query's first name is
    searched. For "San Pedro" it has one inhabited place, in Costa Rica, beside
    a mine, as in its live answer of 2026-10-09 (cut to two)."""

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "tgn" or query.split(",")[0].strip() != "San Pedro":
            return answer
        candidates = (SourceCandidate("San Pedro", "tgn:1016278", "inhabited places", "in San Jose, Costa Rica",
                (PlaceRef("San Jose"), PlaceRef("Costa Rica"))),
            SourceCandidate("San Pedro", "tgn:2640741", "mines (extracting complexes)", "in Santa Fe"))
        evidence = answer.evidence.model_copy(update={"kind": "authority", "excerpt": "\n".join(
            f"{c.name} | {c.authority_id} | {c.kind} | {c.detail}" for c in candidates)})
        return SourceAnswer("tgn", query, LookupStatus.AMBIGUOUS, candidates, evidence, note="ambiguous")


def test_a_gazetteer_is_asked_only_the_name_before_the_first_comma(tmp_path):
    """The third review's N2: "San Pedro, Sacatepequez" asks a gazetteer about
    "San Pedro" alone, never about the label's "San Pedro Sacatepequez"."""
    written = "San Pedro Sacatepequez"
    rig = build_rig(tmp_path, TEXT.replace("city: Chicago", "city: " + written))
    run = rig.specimen.run

    async def script(task, readings, tools):
        found = await tools.lookup("tgn", "San Pedro, Sacatepequez", field_key=task.key)
        return FieldOutcome(task.key, resolved(written, value="San Pedro", authority_id="tgn:1016278",
            cited=[found.evidence.id]), evidence=[found.evidence], model_calls=1)
    settle(rig, Scripted({"city": script}), tools=SearchesTheFirstName(rig.blobs))
    city = run.fields["city"]
    assert (city.state, city.literal, city.reason) == (ValueState.UNRESOLVED, written,
        agreement.NO_PLACE + " Settled.")
    assert run.disposition == Disposition.REVIEW and "mandatory_unresolved:city" in run.reasons


def test_an_organiser_candidate_that_cuts_the_name_on_its_line_never_settles_the_taxon(tmp_path):
    """The third review's N3: the line writes "Danaus plexippus megalippe" with
    no key, and the organiser's candidate in both readings is "Danaus
    plexippus", quoting the whole line. GBIF settles the binomial it was asked."""
    rig = build_rig(tmp_path, TEXT.replace("taxon: Danaus plexippus", TRINOMIAL), candidates=[*COLLECTORS,
        ("taxon", "1A", "Danaus plexippus", TRINOMIAL), ("taxon", "1B", "Danaus plexippus", TRINOMIAL)])
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": taxon_on("Danaus plexippus", literal="Danaus plexippus")}),
        tools=Subspecies(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.reason) == (ValueState.UNRESOLVED, agreement.PART_OF_NAME + " Settled.")
    assert run.disposition == Disposition.REVIEW and "mandatory_unresolved:taxon" in run.reasons


def test_a_field_with_no_candidate_is_never_resolved(tmp_path):
    """No reading is decided, so the keyed-line parser reads nothing, and the
    organiser gave only the collectors: the taxon expert's answer, GBIF's
    decision for the name both readers write, has no candidate to be."""
    rig = build_rig(tmp_path, TEXT, TEXT.replace("Synthetic grassland", "Synthetic grassIand"))
    run = rig.specimen.run
    [task] = [task for task in build_tasks(run)[1] if task.key == "taxon"]
    assert task.candidates == () and task.current.state == ValueState.UNKNOWN
    settle(rig, Scripted())
    taxon = run.fields["taxon"]
    assert taxon.state == ValueState.UNRESOLVED and taxon.reason == agreement.NOT_CANDIDATE + " Settled."
    assert run.disposition == Disposition.REVIEW and "mandatory_unresolved:taxon" in run.reasons


# ---- readers that disagree (G19, G20, G27; the review's B1) --------------------

SMYTH = TEXT.replace("leg. J. Smith", "leg. J. Smyth")
SMITH_OR_SMYTH = [("collectors", "1A", "J. Smith", "leg. J. Smith"),
    ("collectors", "1B", "J. Smyth", "leg. J. Smyth")]
CHIMALTENAGO, CHIMALTENANGO = (TEXT.replace("Illinois", name) for name in ("Chimaltenago", "Chimaltenango"))
PROVINCES = [*COLLECTORS, ("province_state", "1A", "Chimaltenago", "province_state: Chimaltenago"),
    ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")]


def cited_rows(run, key):
    evidence = {item.id: item for item in run.evidence}
    value = run.fields[key]
    return {evidence[i].excerpt: value.evidence_relations.get(i) for i in value.evidence_ids}


def test_a_pick_between_readers_no_source_settles_never_clears(tmp_path):
    """The review's first probe: no decided transcript, reader 1A writes
    "leg. J. Smith" and 1B "leg. J. Smyth", the organiser leaves collectors
    ambiguous, and the expert answers with 1A's text."""
    rig = build_rig(tmp_path, TEXT, SMYTH, candidates=SMITH_OR_SMYTH)
    run = rig.specimen.run
    assert {r.input_source for r in field_step.run_readings(run)} == {"raw_reading"}
    assert run.fields["collectors"].state == ValueState.AMBIGUOUS
    settle(rig, Scripted({"collectors": answering(resolved("J. Smith", reading="1A"))}))
    collectors = run.fields["collectors"]
    assert (collectors.state, collectors.literal) == (ValueState.AMBIGUOUS, None)
    assert collectors.reason == agreement.DIFFER + " Settled."
    # Both readers' rows stay cited, for the person who chooses.
    assert {"leg. J. Smith", "leg. J. Smyth"} <= set(cited_rows(run, "collectors"))
    assert run.disposition == Disposition.REVIEW and "mandatory_unresolved:collectors" in run.reasons


def test_a_place_the_readers_disagree_on_never_clears_without_a_lookup(tmp_path):
    """G27's own example with no lookup at all: 1A writes "Chimaltenago", 1B
    "Chimaltenango", and the expert answers with 1B's text."""
    rig = build_rig(tmp_path, CHIMALTENAGO, CHIMALTENANGO, candidates=PROVINCES)
    run = rig.specimen.run
    settle(rig, Scripted({"province_state": answering(resolved("Chimaltenango", reading="1B"))}))
    province = run.fields["province_state"]
    assert (province.state, province.reason) == (ValueState.AMBIGUOUS, agreement.DIFFER + " Settled.")
    assert run.disposition == Disposition.REVIEW and "mandatory_unresolved:province_state" in run.reasons


def confirming(text, literal=None, *, reading="1B", absent=(), source="geolocate", within=None):
    """A place expert: one lookup of `text` (with GEOLocate, followed by its
    larger units: `within`, by default the synthetic label's), a Getty TGN
    lookup (no match) for each text in `absent`, then `literal` (`text` by
    default) from `reading` with the answer's candidate."""
    async def script(task, readings, tools):
        query = (", ".join((text, *(WITHIN[task.key] if within is None else within)))
            if source == "geolocate" else text)
        answer = await tools.lookup(source, query, field_key=task.key)
        missing = [await tools.lookup("tgn", item, field_key=task.key) for item in absent]
        return FieldOutcome(task.key, resolved(literal or text, reading=reading,
            authority_id=answer.candidates[0].authority_id, cited=[answer.evidence.id]),
            evidence=[answer.evidence, *(item.evidence for item in missing)], model_calls=1)
    return script


ILINOIS = TEXT.replace("Illinois", "Ilinois")
STATES = [("province_state", "1A", "Ilinois", "province_state: Ilinois"),
    ("province_state", "1B", "Illinois", "province_state: Illinois")]


def test_a_lookup_that_confirms_exactly_one_readers_place_settles_it_and_keeps_both_readers(tmp_path):
    """1A writes "Ilinois", 1B "Illinois": Getty TGN has the state for 1B's
    text and nothing for 1A's."""
    rig = build_rig(tmp_path, ILINOIS, TEXT, candidates=every_field(*STATES))
    run = rig.specimen.run
    first, second = run.observations
    settle(rig, Scripted({"province_state": confirming("Illinois", source="tgn", absent=["Ilinois"])}))
    province = run.fields["province_state"]
    assert (province.state, province.literal, province.layer) == (ValueState.SUPPORTED, "Illinois", "settled")
    # G20 and G27: the confirmed reader settles it; the other's text is kept, unsettled.
    assert province.verbatim_by_observation == {second.id: "Illinois", first.id: "Ilinois"}
    assert (province.settled_observation_ids, province.source_observation_id) == ([second.id], second.id)
    rows = cited_rows(run, "province_state")
    assert rows["province_state: Ilinois"] == "contradicts"
    assert rows["province_state: Illinois"] == "supports"
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])


SAN_PEDRO, SAN_PABLO = (TEXT.replace("city: Chicago", "city: " + name) for name in ("San Pedro", "San Pablo"))
CITIES = [("city", "1A", "San Pedro", "city: San Pedro"), ("city", "1B", "San Pablo", "city: San Pablo")]


@pytest.mark.parametrize(("absent", "cleared"), [
    # The second review's B1: GEOLocate was asked only about the reader it picked.
    ((), False),
    # Getty TGN finds nothing for the other reader's text: G20 settles it.
    (("San Pablo",), True),
])
def test_readers_that_differ_settle_only_when_every_readers_text_was_looked_up(tmp_path, absent, cleared):
    rig = build_rig(tmp_path, SAN_PEDRO, SAN_PABLO, candidates=every_field(*CITIES))
    run = rig.specimen.run
    settle(rig, Scripted({"city": confirming("San Pedro", reading="1A", absent=absent)}))
    city = run.fields["city"]
    if cleared:
        assert (city.state, city.literal) == (ValueState.SUPPORTED, "San Pedro")
        assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
        return
    assert (city.state, city.literal) == (ValueState.AMBIGUOUS, None)
    assert city.reason == agreement.DIFFER + " Settled."
    assert run.disposition == Disposition.REVIEW and "mandatory_unresolved:city" in run.reasons


def test_readers_whose_texts_one_source_confirms_as_one_place_name_that_place(tmp_path):
    """The third review's N4: 1A writes "Yepocapa,", 1B "Yepocapa", and one
    GEOLocate answer confirms both as the same town; on a label whose country
    and department Getty TGN settles, the city settles on that evidence."""
    places = dict(country="Guatemala", province_state="Chimaltenango", county=None)
    rig = build_rig(tmp_path, label_with(**places, city="Yepocapa,"), label_with(**places, city="Yepocapa"),
        candidates=[*COLLECTORS, *((key, name, value, f"{key}: {value}") for key, value in places.items()
            if value for name in ("1A", "1B")),
            ("city", "1A", "Yepocapa,", "city: Yepocapa,"), ("city", "1B", "Yepocapa", "city: Yepocapa")])
    run = rig.specimen.run
    first, second = run.observations
    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
        "province_state": from_tgn("Chimaltenango", "Chimaltenango", None, "tgn:1000565"),
        "city": confirming("Yepocapa", reading="1B", within=("Chimaltenango", "Guatemala"))}),
        tools=Gazetteer(rig.blobs))
    city = run.fields["city"]
    assert (city.state, city.literal, city.authority_id) == (
        ValueState.SUPPORTED, "Yepocapa", "geolocate:Yepocapa, Chimaltenango, Guatemala")
    # Each reader's text is kept, unfolded (G27); the confirmed reading settles it.
    assert city.verbatim_by_observation == {second.id: "Yepocapa", first.id: "Yepocapa,"}
    assert not reasons_for(run, "city")


def test_readers_whose_texts_name_two_places_never_settle(tmp_path):
    """San Pedro and San Pablo, each confirmed by GEOLocate as its own town."""
    rig = build_rig(tmp_path, SAN_PEDRO, SAN_PABLO, candidates=every_field(*CITIES))
    run = rig.specimen.run

    async def both(task, readings, tools):
        found = [await tools.lookup("geolocate", geolocate_query(text), field_key=task.key)
            for text in ("San Pedro", "San Pablo")]
        return FieldOutcome(task.key, resolved("San Pedro", authority_id=found[0].candidates[0].authority_id,
            cited=[found[0].evidence.id]), evidence=[item.evidence for item in found], model_calls=1)
    settle(rig, Scripted({"city": both}))
    assert (run.fields["city"].state, run.fields["city"].reason) == (ValueState.AMBIGUOUS,
        agreement.DIFFER + " Settled.")


def test_a_taxon_the_readers_write_differently_needs_every_readers_name_looked_up(tmp_path):
    """The second review's B1: 1A writes the trinomial, 1B the binomial, and
    GBIF was asked only the binomial, whose answer names 1B's text."""
    trinomial = TEXT.replace("taxon: Danaus plexippus", "taxon: " + TRINOMIAL)
    rig = build_rig(tmp_path, trinomial, TEXT, candidates=every_field(
        ("taxon", "1A", TRINOMIAL, "taxon: " + TRINOMIAL),
        ("taxon", "1B", "Danaus plexippus", "taxon: Danaus plexippus")))
    run = rig.specimen.run

    async def binomial_only(task, readings, tools):
        answer = await tools.lookup("gbif", "Danaus plexippus", field_key=task.key)
        return FieldOutcome(task.key, resolved("Danaus plexippus", value=GBIF_NAME, authority_id=GBIF_KEY,
            cited=[answer.evidence.id], reading="1B"), evidence=[answer.evidence],
            lookups=[answer.taxonomy_lookup], model_calls=1)
    settle(rig, Scripted({"taxon": binomial_only}), tools=Subspecies(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal) == (ValueState.AMBIGUOUS, None)
    assert run.disposition == Disposition.REVIEW and "mandatory_unresolved:taxon" in run.reasons


class Gazetteer(FakeSources):
    """Getty TGN as the pilot's recordings answer, with each place's parents:
    "P.I." the nation and places that are none; "Chimaltenango" the department
    and its town; "Escuintla" a department and its town."""

    FIRST = "departments (political divisions), agricultural land, first level subdivisions (political entities)"
    NATION = "nations, commonwealths, controlled regions"
    GT = (("Guatemala", "tgn:7005493"),)
    PLACES = {
        "P.I.": [("Philippines", "tgn:1000135", NATION, (("Philippines", "tgn:1000135"),)),
            ("Philippine", "tgn:7268540", "inhabited places", (("Zeeland", None), ("Nederland", None)))],
        "Chimaltenango": [("Chimaltenango", "tgn:1016636", "inhabited places, cities, department capitals",
                (("Chimaltenango", "tgn:1000565"), *GT)),
            ("Chimaltenango", "tgn:1000565", FIRST, GT)],
        "Escuintla": [("Escuintla", "tgn:1000566", FIRST, GT),
            ("Escuintla", "tgn:1016700", "inhabited places", (("Escuintla", "tgn:1000566"), *GT))],
        # As TGN answered "Philippine Islands" and "Guatemala" on the pilot's records.
        "Philippine Islands": [("Philippine Islands", "tgn:2578581", "ridges (landforms)",
                (("Portage", None), ("Wisconsin", None), ("United States", None))),
            ("Philippines", "tgn:1000135", NATION, (("Philippines", "tgn:1000135"),)),
            ("Philippine", "tgn:7268540", "inhabited places", (("Zeeland", None), ("Nederland", None))),
            ("Philippine Sea", "tgn:7016773", "seas", (("Oceans", None), ("World", None))),
            ("Caroline Islands", "tgn:7005669", "island groups", (("Oceania", None), ("World", None)))],
        "Philippines": [("Philippines", "tgn:1000135", NATION, (("Philippines", "tgn:1000135"),)),
            ("Philippine", "tgn:7268540", "inhabited places", (("Zeeland", None), ("Nederland", None)))],
        "Guatemala": [("Guatemala", "tgn:7422823", "inhabited places", (("Zacatecas", None), ("Mexico", None))),
            ("Guatemala", "tgn:7005493", "nations, colonies, independent political entities", GT),
            ("Guatemala", "tgn:1000621", FIRST, GT)],
    }

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "tgn" or query not in self.PLACES:
            return answer
        candidates = tuple(SourceCandidate(name, key, kind, "in " + ", ".join(parent for parent, _ in parents),
            tuple(PlaceRef(*parent) for parent in parents)) for name, key, kind, parents in self.PLACES[query])
        evidence = answer.evidence.model_copy(update={"kind": "authority", "excerpt": "\n".join(
            f"{c.name} | {c.authority_id} | {c.kind} | {c.detail}" for c in candidates)})
        return SourceAnswer("tgn", query, LookupStatus.AMBIGUOUS, candidates, evidence, note="ambiguous")


def from_tgn(query, literal, value, authority_id, source="tgn"):
    async def script(task, readings, tools):
        answer = await tools.lookup(source, query, field_key=task.key)
        return FieldOutcome(task.key, resolved(literal, value=value, authority_id=authority_id,
            cited=[answer.evidence.id]), evidence=[answer.evidence], model_calls=1)
    return script


def label_with(**places):
    """TEXT with these place lines instead; None leaves a line out."""
    lines = []
    for line in TEXT.splitlines():
        key = line.partition(":")[0]
        if key in places and places[key] is None:
            continue
        lines.append(f"{key}: {places[key]}" if key in places else line)
    return "\n".join(lines)


# A Guatemalan label: its country, which Getty TGN settles, and no county or city.
GUATEMALAN = dict(country="Guatemala", county=None, city=None)
IN_GUATEMALA = {"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
    **dict.fromkeys(("county", "city"), answering(FieldAnswer(outcome="label_lacks_value",
        explanation="Not on the label.")))}


def guatemalan(**scripts):
    return Scripted({**IN_GUATEMALA, **scripts})


def reasons_for(run, key):
    return [reason for reason in run.reasons if reason.endswith(":" + key)]


@pytest.mark.parametrize(("key", "written", "query", "value", "authority_id", "settles"), [
    # Getty TGN's answer is ambiguous only because it also holds places that are no nation.
    ("country", "P.I.", "P.I.", "Philippines", "tgn:1000135", True),
    # The department is the province; as a city, the department never is.
    ("province_state", "Chimaltenango", "Chimaltenango", None, "tgn:1000565", True),
    ("city", "Chimaltenango", "Chimaltenango", None, "tgn:1000565", False),
])
def test_an_ambiguous_place_answer_settles_on_its_one_candidate_at_the_fields_level(
        tmp_path, key, written, query, value, authority_id, settles):
    rig = build_rig(tmp_path, label_with(**{**GUATEMALAN, key: written}) if key != "country"
        else label_with(country=written))
    run = rig.specimen.run
    scripts = {key: from_tgn(query, written, value, authority_id)}
    settle(rig, guatemalan(**scripts) if key != "country" else Scripted(scripts), tools=Gazetteer(rig.blobs))
    place = run.fields[key]
    if settles:
        assert (place.state, place.literal, place.authority_id) == (ValueState.SUPPORTED, written, authority_id)
        assert place.normalized == value and not reasons_for(run, key)
        return
    assert (place.state, place.reason) == (ValueState.UNRESOLVED, agreement.NO_PLACE + " Settled.")
    assert run.disposition == Disposition.REVIEW and f"mandatory_unresolved:{key}" in run.reasons


@pytest.mark.parametrize(("written", "query", "value", "authority_id", "outcome"), [
    # An unrelated lookup: Escuintla for what the label writes as Chimaltenago.
    ("Chimaltenago", "Escuintla", "Escuintla", "tgn:1000566", None),
    # TGN's Chimaltenango, one letter from the label's "Chimaltenago": the label's one
    # other place field, its country Guatemala, is the department's parent (G34).
    ("Chimaltenago", "Chimaltenango", "Chimaltenango", "tgn:1000565", "near_spelling"),
    # The label's own text, case and punctuation aside.
    ("chimaltenango,", "Chimaltenango", "Chimaltenango", "tgn:1000565", "asked"),
    # Two letters from it.
    ("Chimaltango", "Chimaltenango", "Chimaltenango", "tgn:1000565", None),
])
def test_a_place_settles_only_on_a_lookup_of_the_labels_own_text_or_one_letter_from_it(
        tmp_path, written, query, value, authority_id, outcome):
    rig = build_rig(tmp_path, label_with(**GUATEMALAN, province_state=written))
    run = rig.specimen.run
    settle(rig, guatemalan(province_state=from_tgn(query, written, value, authority_id)), tools=Gazetteer(rig.blobs))
    place = run.fields["province_state"]
    near = [f for f in run.findings if f.reason_code == "near_spelling:province_state"]
    if outcome is None:
        assert (place.state, place.reason) == (ValueState.UNRESOLVED, agreement.NO_PLACE + " Settled.")
        assert run.disposition == Disposition.REVIEW and not near
        return
    # The label's spelling stays the literal (G27); the value is TGN's department.
    assert (place.state, place.literal, place.normalized, place.authority_id) == (
        ValueState.SUPPORTED, written, value, authority_id)
    # The county and city the label leaves out clear as not on the label (owner decision A).
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert {key for key in ("county", "city") if field_step.not_on_label(key, run.fields[key], run,
        {item.id: item for item in run.evidence}, field_step.not_on_label_keys(field_step.profile_of(run)))} == {
        "county", "city"}
    if outcome == "asked":
        assert not near
        return
    [finding] = near
    assert (finding.severity, finding.field_key, finding.rule_id) == ("warning", "province_state", "near_spelling")
    assert set(finding.evidence_ids) <= set(place.evidence_ids) and finding.evidence_ids


class InParaguay(Gazetteer):
    """Wikidata's live answer for "San Pedro" (2026-10-09, as the third review
    read it): seven places, the only one at a province's level San Pedro
    Department, in Paraguay (cut to two)."""

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "wikidata" or query != "San Pedro":
            return answer
        candidates = (SourceCandidate("San Pedro Department", "wikidata:San Pedro Department",
                "department of Paraguay", "in Paraguay", (PlaceRef("Paraguay"),)),
            SourceCandidate("San Pedro", "wikidata:San Pedro", "human settlement", "in Philippines",
                (PlaceRef("Philippines"),)))
        evidence = answer.evidence.model_copy(update={"locator": None, "excerpt": "\n".join(
            f"{c.name} | {c.authority_id} | {c.kind} | {c.detail}" for c in candidates)})
        return SourceAnswer("wikidata", query, LookupStatus.AMBIGUOUS, candidates, evidence, note="ambiguous")


PHILIPPINE = label_with(country="P.I.", province_state="Chimaltenago", county="Davao", city="Mati")
NOTATION_COUNTRY = {"country": from_tgn("Philippine Islands", "P.I.", "Philippines", "tgn:1000135")}


@pytest.mark.parametrize(("text", "scripts", "key", "reason"), [
    # This PR's own earlier case (the third review's B3): a US label's province, one letter
    # from TGN's department of Guatemala.
    (label_with(province_state="Chimaltenago"),
     {"province_state": from_tgn("Chimaltenango", "Chimaltenago", "Chimaltenango", "tgn:1000565")},
     "province_state", agreement.NOT_IN_COUNTRY),
    # Its own text asked, the department still lies in another country.
    (label_with(province_state="Chimaltenango"),
     {"province_state": from_tgn("Chimaltenango", "Chimaltenango", None, "tgn:1000565")},
     "province_state", agreement.NOT_IN_COUNTRY),
    # The review's case of G34's own kind: a Philippine label (P.I. settled as the
    # Philippines, Davao, Mati) whose province settles one letter away in Guatemala.
    (PHILIPPINE, {**NOTATION_COUNTRY, "province_state": from_tgn(
        "Chimaltenango", "Chimaltenago", "Chimaltenango", "tgn:1000565"), "county": place_on("Davao"),
        "city": place_on("Mati")}, "province_state", agreement.NOT_IN_COUNTRY),
    # P1's "one candidate at the level" of a capped list: Wikidata's only department for
    # "San Pedro" is Paraguay's, on a Guatemalan label.
    (label_with(**GUATEMALAN, province_state="San Pedro"), {**IN_GUATEMALA, "province_state": from_tgn(
        "San Pedro", "San Pedro", "San Pedro Department", "wikidata:San Pedro Department", source="wikidata")},
     "province_state", agreement.NOT_IN_COUNTRY),
    # G34's whole condition: the reading also writes a city, which is no province's parent.
    (label_with(**{**GUATEMALAN, "city": "Yepocapa"}, province_state="Chimaltenago"),
     {**IN_GUATEMALA, "province_state": from_tgn("Chimaltenango", "Chimaltenago", "Chimaltenango", "tgn:1000565")},
     "province_state", agreement.NEAR_UNFIT),
    # A candidate whose source names no parent: GEOLocate asked the city alone.
    (TEXT, {"city": place_on("Chicago")}, "city", agreement.NO_PARENTS),
    # A city in the country, but not in the province the label gives.
    (TEXT, {"city": from_tgn("Chicago, Cook, Wisconsin, United States", "Chicago", None,
        "geolocate:Chicago, Cook, Wisconsin, United States", source="geolocate")}, "city",
     agreement.NOT_IN_PROVINCE),
    # No country is settled for the reading: none of the places below it settles.
    (TEXT, {"country": answering(FieldAnswer(outcome="sources_cannot_resolve", explanation="No match."))},
     "province_state", agreement.NO_COUNTRY),
], ids=["us-label-near-spelling", "us-label-asked", "philippine-label", "capped-list-paraguay",
        "near-spelling-with-a-city", "no-parents", "not-in-province", "no-country"])
def test_a_place_settles_only_inside_the_labels_country_and_province(tmp_path, text, scripts, key, reason):
    rig = build_rig(tmp_path, text)
    run = rig.specimen.run
    settle(rig, Scripted(scripts), tools=InParaguay(rig.blobs))
    place = run.fields[key]
    assert (place.state, place.reason) == (ValueState.UNRESOLVED, reason + " Settled.")
    assert run.disposition == Disposition.REVIEW and f"mandatory_unresolved:{key}" in run.reasons
    assert not [f for f in run.findings if f.reason_code == f"near_spelling:{key}"]


def test_a_near_spelling_settles_when_every_other_place_field_is_among_its_parents(tmp_path):
    """The full US label with its city one letter off: TGN's Chicago lies in
    Cook, Illinois, United States, the label's county, state and country."""
    rig = build_rig(tmp_path, label_with(city="Chicag"))
    run = rig.specimen.run
    settle(rig, Scripted({"city": from_tgn("Chicago", "Chicag", "Chicago", "tgn:Chicago")}))
    city = run.fields["city"]
    assert (city.state, city.literal, city.normalized, city.authority_id) == (
        ValueState.SUPPORTED, "Chicag", "Chicago", "tgn:Chicago")
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert [f.reason_code for f in run.findings] == ["near_spelling:city"]


@pytest.mark.parametrize(("written", "query", "value", "authority_id", "settles"), [
    # The table's expansion of "P.I.", with TGN's real ambiguous answer: one nation.
    ("P.I.", "Philippine Islands", "Philippines", "tgn:1000135", True),
    ("Guat.", "Guatemala", "Guatemala", "tgn:7005493", True),
    # Another name for the place is context only.
    ("P.I.", "Philippines", "Philippines", "tgn:1000135", False),
    # A notation the table does not hold.
    ("Guate.", "Guatemala", "Guatemala", "tgn:7005493", False),
])
def test_a_place_notation_settles_on_a_lookup_of_the_name_the_table_gives_it(
        tmp_path, written, query, value, authority_id, settles):
    rig = build_rig(tmp_path, label_with(country=written))
    run = rig.specimen.run
    settle(rig, Scripted({"country": from_tgn(query, written, value, authority_id)}), tools=Gazetteer(rig.blobs))
    country = run.fields["country"]
    rules = [item for item in run.evidence if item.kind == "rule"]
    if not settles:
        assert (country.state, country.reason) == (ValueState.UNRESOLVED, agreement.NO_PLACE + " Settled.")
        assert run.disposition == Disposition.REVIEW and not rules
        return
    assert (country.state, country.literal, country.normalized, country.authority_id) == (
        ValueState.SUPPORTED, written, value, authority_id)
    # The synthetic label's US places do not lie in it; the country itself needs no parent.
    assert not reasons_for(run, "country")
    # One rule row names the table entry; the value cites it as support. It has
    # no stored record, so it is never projected.
    [rule] = rules
    assert rule.locator == f"notation:country:{written}" and query in rule.excerpt
    assert (rule.raw_ref, rule.digest) == (None, None) and country.evidence_relations[rule.id] == "supports"


def test_a_place_never_clears_without_a_place_sources_candidate(rig):
    run = rig.specimen.run
    settle(rig, Scripted({"country": answering(resolved(LABEL["country"]))}))
    country = run.fields["country"]
    assert (country.state, country.literal) == (ValueState.UNRESOLVED, LABEL["country"])
    assert country.reason == agreement.NO_PLACE + " Settled."
    # The places below it wait for a settled country.
    assert run.fields["county"].reason == agreement.NO_COUNTRY + " Settled."
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [f"mandatory_unresolved:{key}"
        for key in ("city", "country", "county", "province_state")])


SLOPE, SPACED = "E. slope Mt. McKinley", "E.slope Mt. McKinley"


@pytest.mark.parametrize(("literal", "reading"), [(SLOPE, "1A"), (SPACED, "1B")])
def test_a_labels_decided_transcript_decides_its_text_and_the_other_reader_is_evidence(tmp_path, literal, reading):
    """As on 105526321's second label: the first pass decided the reading that
    writes "E. slope Mt. McKinley"; the other reader writes "E.slope"."""
    garden = LABEL["precise_location"]
    rig = build_rig(tmp_path, TEXT.replace(garden, SLOPE), TEXT.replace(garden, SPACED), decided=True,
        candidates=[*COLLECTORS, ("precise_location", "1B", SPACED, "precise_location: " + SPACED)])
    run = rig.specimen.run
    assert [r.input_source for r in field_step.run_readings(run)] == ["decided_transcript", "raw_reading"]
    settle(rig, Scripted({"precise_location": answering(resolved(literal, reading=reading))}))
    place = run.fields["precise_location"]
    if reading == "1B":
        assert (place.state, place.literal) == (ValueState.UNRESOLVED, SLOPE)
        assert place.reason == agreement.NOT_DECIDED + " Settled."
        assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["mandatory_unresolved:precise_location"])
        return
    assert (place.state, place.literal, place.input_source) == (ValueState.SUPPORTED, SLOPE, "decided_transcript")
    assert cited_rows(run, "precise_location")["precise_location: " + SPACED] == "contradicts"
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])


def test_no_elevation_is_derived_from_a_unit_the_readings_disagree_on(rig):
    run = rig.specimen.run
    settle(rig, Scripted({"elevation_to_ft": answering(FieldAnswer(outcome="several_possibilities",
        options=["1500", "1600"], explanation="Two readings."))}))
    assert run.fields["elevation_from_m"].state == ValueState.NOT_PRESENT
    assert "mandatory_unresolved:elevation_from_m" in run.reasons


# ---- finalize_fields ---------------------------------------------------------

def test_every_field_settled_clears_without_human_approval(rig):
    run = rig.specimen.run
    assert settle(rig, Scripted()) is None
    assert (run.stage, run.disposition, run.blocker, run.reasons) == ("finalized", Disposition.CLEARED, None, [])
    # The ordinary policy would hold it for blanket approval; field research does not (G1).
    assert "human_approval_required" in evaluate(run)


def test_an_unresolved_mandatory_field_sends_the_record_to_review_with_its_reason(rig):
    run = rig.specimen.run
    settle(rig, Scripted({"county": answering(FieldAnswer(outcome="sources_cannot_resolve",
        explanation="GEOLocate found no Cook County in Illinois."))}))
    assert (run.stage, run.disposition, run.blocker) == ("finalized", Disposition.REVIEW, None)
    assert run.reasons == ["mandatory_unresolved:county"]
    assert run.fields["county"].reason == "GEOLocate found no Cook County in Illinois."


LACKS = FieldAnswer(outcome="label_lacks_value", explanation="Not on the label.")


def test_an_empty_date_is_unresolved_not_a_date_precision_question(rig):
    run = rig.specimen.run
    settle(rig, Scripted({"date_identified": answering(LACKS)}))
    assert run.fields["date_identified"].state == ValueState.NOT_PRESENT
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["mandatory_unresolved:date_identified"])


def test_a_date_with_a_value_is_still_checked_for_precision_and_order(rig):
    run = rig.specimen.run
    settle(rig, Scripted())
    run.fields["date_identified"] = run.fields["date_identified"].model_copy(update={"parsed": "June 1946"})
    assert "date_precision_requires_review" in field_step.scientific_reasons(run, {
        key: field_step.RESOLVED for key in run.fields}, mandatory=(), qualified=frozenset(), today=TODAY)
    run.fields["date_identified"] = run.fields["date_identified"].model_copy(update={"parsed": "2020-05-01"})
    assert "date_order" in field_step.scientific_reasons(run, {
        key: field_step.RESOLVED for key in run.fields}, mandatory=(), qualified=frozenset(), today=TODAY)


def test_an_empty_elevation_is_unresolved_not_an_invalid_elevation(rig):
    run = rig.specimen.run
    settle(rig, Scripted({"elevation_from_ft": answering(LACKS)}))
    # Nothing is derived from an elevation the label lacks: all four are empty.
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, [f"mandatory_unresolved:elevation_{end}_{unit}"
        for end, unit in (("from", "ft"), ("from", "m"), ("to", "ft"), ("to", "m"))])
    # A value that is no number is still invalid.
    run.fields["elevation_to_ft"] = FieldValue(state=ValueState.SUPPORTED, literal="about 1500")
    assert "elevation_invalid:ft" in field_step.scientific_reasons(run, {
        key: field_step.RESOLVED for key in run.fields}, mandatory=(), qualified=frozenset(), today=TODAY)


def test_a_spent_budget_sends_its_field_to_review_not_to_a_retry(rig):
    run = rig.specimen.run
    assert settle(rig, Scripted({"taxon": failing("budget_exhausted")})) is None
    assert (run.stage, run.disposition) == ("finalized", Disposition.REVIEW)
    assert {"mandatory_unresolved:taxon", "taxonomy_unresolved"} == set(run.reasons)
    assert run.fields["taxon"].reason == field_step.FIELD_REASONS["budget_exhausted"]


def test_an_outage_blocks_the_run_and_keeps_every_settled_field(rig):
    run = rig.specimen.run
    blocker = settle(rig, Scripted({"country": failing("source_unavailable")}))
    assert blocker == "lookup_operational_failure"
    assert (run.stage, run.disposition, run.blocker) == ("processing_blocked", None, blocker)
    assert run.reasons[0] == "lookup_operational_failure:country"
    assert run.fields["country"].state == ValueState.UNRESOLVED and run.fields["country"].literal == "United States"
    assert run.fields["taxon"].normalized == GBIF_NAME and run.fields["taxon"].layer == "settled"
    # The places below the country wait for it: no country, no place inside it.
    assert {run.fields[key].reason for key in ("province_state", "county", "city")} == {
        agreement.NO_COUNTRY + " Settled."}


# ---- through the workflow: one step, retry, cost -------------------------------

def mounted(rig, resolver, tools_down=(), sources=None):
    state = SimpleNamespace(meters=[], tools=[])

    def meter_factory(cap, price):
        meter = field_step.cost_meter(cap, price)
        state.meters.append(meter)
        resolver.meter = meter
        return meter

    @asynccontextmanager
    async def tools_factory(run, profile, blobs):
        tools = (sources or FakeSources)(blobs, down=tools_down)
        state.tools.append(tools)
        yield tools

    rig.workflow.field_research = FieldResearchStep(resolver_factory=lambda run, profile, meter: resolver,
        tools_factory=tools_factory, meter_factory=meter_factory)
    return state


def test_a_blocked_run_retries_only_its_unsettled_fields_and_settles_its_cost(rig):
    first = Scripted({"country": failing("source_unavailable")})
    state = mounted(rig, first)
    blocked = rig.workflow.step(rig.principal, rig.specimen.id)
    run = blocked.run
    assert (run.stage, run.blocker, run.disposition) == ("retry_scheduled", "lookup_operational_failure", None)
    assert run.next_retry_at and run.attempts[FIELD_RESEARCH] == 1 and FIELD_RESEARCH not in run.completed_steps
    assert run.fields["taxon"].layer == "settled" and run.fields["country"].state == ValueState.UNRESOLVED
    # One reservation of the whole headroom, settled to what the meter spent.
    [paid] = run.paid_calls
    spent = state.meters[0].spent_micros
    assert spent == 50 * len(RESEARCHED) and paid["reserved_micros"] == 1_000_000
    assert (paid["cost_micros"], paid["cost_basis"], paid["outcome"]) == (spent, "computed", "failed")
    assert run.usage.reserved_cost_micros == spent and run.usage.actual_cost_micros == spent

    second = Scripted()
    mounted(rig, second)
    rig.clock.now += timedelta(hours=1)
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    # The country, and the places below it that waited for it.
    assert second.calls == ["country", "province_state", "county", "city"]
    run = done.run
    assert (run.stage, run.disposition, run.blocker, run.reasons) == ("finalized", Disposition.CLEARED, None, [])
    assert run.completed_steps[-1] == FIELD_RESEARCH and run.attempts[FIELD_RESEARCH] == 2
    assert [call["attempt"] for call in run.paid_calls] == [1, 2]
    assert run.paid_calls[1]["reserved_micros"] == 1_000_000 - spent
    assert run.usage.reserved_cost_micros == spent + 50 * 4 <= run.profile.execution.approved_cost_limit_micros
    verify_evidence(done, rig.blobs)


def test_a_run_without_a_harness_route_keeps_the_ordinary_plan_step(rig):
    mounted(rig, Scripted())
    run = rig.specimen.run
    snapshot = dict(run.profile_snapshot)
    snapshot.pop("harness_route")
    run.profile_snapshot = snapshot
    rig.specimen = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "no-route", "no-route")
    planned = rig.workflow.step(rig.principal, rig.specimen.id)
    assert "plan" in planned.run.completed_steps and FIELD_RESEARCH not in planned.run.attempts


def test_the_ceiling_left_is_the_meters_cap(rig):
    run = rig.specimen.run
    run.usage.reserved_cost_micros = 999_000
    rig.specimen = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "spent", "spent")
    state = mounted(rig, Scripted())
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    assert state.meters[0].cap_micros == 1_000
    assert done.run.usage.reserved_cost_micros <= 1_000_000


@pytest.mark.parametrize(("broken", "blocker"), [
    ("_route_price", "field_research_price_unavailable"),
    ("build_tasks", "field_research_unconfigured"),
])
def test_a_setup_error_before_any_request_settles_to_nothing_and_blocks_with_its_reason(
        rig, monkeypatch, broken, blocker):
    def fail(*args, **kwargs):
        if broken == "_route_price":
            raise OperationalBlock(blocker)
        raise ValueError("unreadable inputs")

    monkeypatch.setattr(field_step, broken, fail)
    resolver = Scripted()
    state = mounted(rig, resolver)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.stage, run.blocker, run.disposition) == ("processing_blocked", blocker, None)
    assert resolver.calls == [] and state.tools == []
    [paid] = run.paid_calls
    assert (paid["reserved_micros"], paid["cost_micros"], paid["cost_basis"], paid["outcome"]) == (
        1_000_000, 0, "computed", "failed")
    assert run.usage.reserved_cost_micros == 0


def test_a_crash_after_research_settles_to_the_meters_exact_spend(rig):
    resolver = Scripted()
    state = mounted(rig, resolver)

    @asynccontextmanager
    async def closing_fails(run, profile, blobs):
        yield FakeSources(blobs)
        raise RuntimeError("client close failed")

    rig.workflow.field_research.tools_factory = closing_fails
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    spent = state.meters[0].spent_micros
    assert spent == 50 * len(RESEARCHED) and run.blocker == "external_outcome_unknown"
    [paid] = run.paid_calls
    assert (paid["cost_micros"], paid["cost_basis"], paid["outcome"]) == (spent, "computed", "failed")
    assert run.usage.reserved_cost_micros == spent


def test_an_overrun_step_keeps_its_settled_spend(rig):
    state = mounted(rig, Scripted())
    rig.workflow.monotonic = iter([0.0, 10_000.0]).__next__  # Far past the effect timeout.
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    # The intent copy comes back (nothing researched is kept), but not its whole reservation.
    assert (run.blocker, run.reasons) == ("external_outcome_unknown", ["external_stage_deadline_exceeded"])
    assert run.fields["taxon"].layer is None
    spent = state.meters[0].spent_micros
    [paid] = run.paid_calls
    assert (paid["cost_micros"], paid["cost_basis"]) == (spent, "computed")
    assert run.usage.reserved_cost_micros == spent


def seed_program(rig, reserved_total, allowance=5_000_000):
    """The run carries the program's allowance; its ledger already holds `reserved_total`."""
    from specimen_digitization.application.domain import Scope
    from specimen_digitization.application.lane_allowance import LEDGER_KIND, ProgramLedger

    run = rig.specimen.run
    run.profile.execution = run.profile.execution.model_copy(update={"program_allowance_micros": allowance,
        "program_ledger_collection": COLLECTION})
    ledger = ProgramLedger(rig.repository, Scope(organization_id=ORG, collection_id=COLLECTION))
    rig.repository.put_document(ledger.scope, LEDGER_KIND, ledger.ident,
        {"sensitive": False, "reserved_total_micros": reserved_total}, 0)
    rig.specimen = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "program", "program")
    return ledger


# One expert request's worst case at the harness route's prices (USD 0.20 and 0.60
# per million): 48,000 input tokens and 512 of chat template, 2,048 output tokens.
ONE_REQUEST = 10_932


def test_a_low_program_allowance_caps_the_step_and_sends_what_does_not_fit_to_review(rig):
    ledger = seed_program(rig, 5_000_000 - 25_000)
    resolver = Scripted(tokens=(48_000, 2048))  # Each field's call settles at its worst case.
    state = mounted(rig, resolver)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    [meter] = state.meters
    assert meter.cap_micros == 25_000 and ONE_REQUEST < 25_000
    [paid] = run.paid_calls
    assert paid["reserved_micros"] == 25_000 and paid["cost_micros"] == meter.spent_micros <= 25_000
    assert (run.stage, run.disposition, run.blocker) == ("finalized", Disposition.REVIEW, None)
    exhausted = [key for key, value in run.fields.items()
        if value.reason == field_step.FIELD_REASONS["budget_exhausted"]]
    assert exhausted and f"mandatory_unresolved:{exhausted[0]}" in run.reasons
    assert ledger.read()["reserved_total_micros"] == 5_000_000 - 25_000 + meter.spent_micros


def test_a_program_allowance_below_one_request_still_blocks_the_record(rig):
    ledger = seed_program(rig, 5_000_000 - (ONE_REQUEST - 1))
    resolver = Scripted()
    state = mounted(rig, resolver)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.stage, run.blocker) == ("processing_blocked", "program_allowance_exhausted")
    assert resolver.calls == [] and state.meters == []
    assert ledger.read()["reserved_total_micros"] == 5_000_000 - (ONE_REQUEST - 1)


def test_the_one_request_bound_is_the_meters_own_bound():
    from specimen_digitization.field_research.budget import (
        DEFAULT_MAX_INPUT_TOKENS, DEFAULT_MAX_TOKENS, TEMPLATE_TOKENS,
    )

    profile = published_registry().profiles[0]
    price = profile.processing.price_list.models[profile.harness_route]
    assert field_step.one_request_micros(price) == field_step.cost_meter(0, price).cost(
        DEFAULT_MAX_INPUT_TOKENS + TEMPLATE_TOKENS, DEFAULT_MAX_TOKENS) == ONE_REQUEST


# ---- a reviewer's decisions after field research --------------------------------

def test_a_reviewers_correction_is_kept_and_the_run_is_never_researched_or_paid_again(rig):
    mounted(rig, Scripted())
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    assert (done.run.stage, done.run.disposition, done.run.attempts[FIELD_RESEARCH]) == (
        "finalized", Disposition.CLEARED, 1)
    # A "field" decision on taxon as api.apply_decision saved it before it knew
    # field research (api.py 1940-1952): the run went back to "lookup", whose next
    # ordinary step is "plan", the field research handover.
    corrected = done.model_copy(deep=True)
    run = corrected.run
    run.fields["taxon"] = FieldValue(state=ValueState.SUPPORTED, literal="Danaus plexippus",
        normalized="Reviewer Choice", authority_id="999", evidence_ids=list(run.fields["taxon"].evidence_ids))
    run.human_approved, run.lookups, run.stage, run.disposition = False, [], "lookup", None
    run.completed_steps = [step for step in run.completed_steps
        if step not in {"lookup", "resolve", "normalize", "validate", "finalize"}]
    saved = rig.repository.save(rig.principal, corrected, done.version, "review", "review")
    second = Scripted()
    state = mounted(rig, second)
    again = rig.workflow.step(rig.principal, saved.id).run
    # Nothing researched, reserved or paid for a second time.
    assert second.calls == [] and state.meters == [] and state.tools == []
    assert again.attempts[FIELD_RESEARCH] == 1 and again.paid_calls == done.run.paid_calls
    assert again.usage.reserved_cost_micros == done.run.usage.reserved_cost_micros
    # The reviewer's value exactly as made; the clearance rules recomputed on it.
    assert again.fields == corrected.run.fields
    assert (again.stage, again.disposition, again.blocker) == ("finalized", Disposition.REVIEW, None)
    assert set(again.reasons) == {"unsupported_normalized:taxon", "unsupported_authority_id:taxon",
        "taxonomy_unresolved"}
    verify_evidence(rig.repository.get(rig.principal.scope, saved.id), rig.blobs)


def test_a_retry_action_on_a_researched_run_only_applies_the_rules_again(rig):
    mounted(rig, Scripted())
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    # api.action "retry": the next ordinary step, "plan", becomes the stage.
    retried = done.model_copy(deep=True)
    retried.run.stage = rig.workflow.next_step(retried.run).split(":")[0]
    assert retried.run.stage == "plan"
    retried.run.disposition = None
    saved = rig.repository.save(rig.principal, retried, done.version, "retry", "retry")
    second = Scripted()
    mounted(rig, second)
    again = rig.workflow.step(rig.principal, saved.id).run
    assert second.calls == [] and again.paid_calls == done.run.paid_calls
    assert (again.stage, again.disposition, again.reasons) == ("finalized", Disposition.CLEARED, [])
    assert again.completed_steps == done.run.completed_steps


def review_client(rig):
    from fastapi.testclient import TestClient

    from specimen_digitization.application.api import create_app

    member = {"organization_id": ORG, "collection_id": COLLECTION, "role": "reviewer",
        "can_view_sensitive": False}
    app = create_app(mode="emulator", repository=rig.repository, blobs=rig.blobs,
        adapters=SyntheticAdapters(rig.blobs, TEXT), identity_verifier=lambda token, check: "reviewer-1",
        memberships=lambda user: [member])
    return TestClient(app, raise_server_exceptions=False)


def decide(client, rig, key, kind, **body):
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    request = {"expected_revision": current.version, "kind": kind, "reason": "Reviewed.",
        "base_record_version_id": f"{current.run.id}:{current.version}", **body}
    response = client.post(f"/v1/organizations/{ORG}/specimens/{current.id}/decisions",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": key}, json=request)
    assert response.status_code == 200, response.text
    return rig.repository.get(rig.principal.scope, current.id).run


def test_a_correction_waits_for_approval_and_an_approval_clears_by_the_field_research_rules(rig):
    state = mounted(rig, Scripted())
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    assert done.run.disposition == Disposition.CLEARED
    client = review_client(rig)
    # Approving a record field research cleared keeps it cleared: the rules are
    # field research's (derived values have no literal; the ordinary policy
    # would refuse them), and the approval is the person's.
    approved = decide(client, rig, "approve-1", "approve")
    assert (approved.stage, approved.disposition, approved.reasons) == ("finalized", Disposition.CLEARED, [])
    # A correction on taxon is kept exactly, never researched again, and waits
    # for the reviewer's approval.
    taxon = approved.fields["taxon"]
    after = taxon.model_dump(mode="json", exclude={"evidence_ids"}) | {"reason": "Checked against GBIF."}
    corrected = decide(client, rig, "field-1", "field", target_id="taxon", after=after,
        evidence_ids=list(taxon.evidence_ids))
    assert corrected.fields["taxon"].reason == "Checked against GBIF."
    assert corrected.fields["taxon"].normalized == GBIF_NAME and corrected.lookups == approved.lookups
    assert (corrected.stage, corrected.disposition, corrected.reasons) == (
        "finalized", Disposition.REVIEW, ["human_approval_required"])
    assert FIELD_RESEARCH in corrected.completed_steps and len(state.meters) == 1
    cleared = decide(client, rig, "approve-2", "approve")
    assert (cleared.stage, cleared.disposition, cleared.reasons) == ("finalized", Disposition.CLEARED, [])
    assert cleared.fields == corrected.fields and cleared.paid_calls == done.run.paid_calls
    # A correction the rules refuse stays in review after the approval.
    county = cleared.fields["county"]
    wrong = decide(client, rig, "field-2", "field", target_id="county",
        after=county.model_dump(mode="json", exclude={"evidence_ids"}) | {"literal": "Lake"},
        evidence_ids=list(county.evidence_ids))
    assert wrong.reasons == ["evidence_does_not_support_value:county", "human_approval_required"]
    held = decide(client, rig, "approve-3", "approve")
    assert (held.disposition, held.reasons) == (Disposition.REVIEW, ["evidence_does_not_support_value:county"])


# GBIF's other usage of the label's name, beside GBIF_NAME.
HOMONYM_NAME, HOMONYM_KEY = "Danaus plexippus (Cramer, 1777)", "5133100"


class UndecidedTaxon(FakeSources):
    """GBIF cannot settle the taxon: two usages of its name, neither decided."""

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "gbif":
            return answer
        usages = {GBIF_KEY: GBIF_NAME, HOMONYM_KEY: HOMONYM_NAME}
        candidates = tuple(SourceCandidate(name=name, authority_id=key, kind="SPECIES") for key, name in usages.items())
        evidence = answer.evidence.model_copy(update={"locator": None, "excerpt": "GBIF cannot settle the name\n"
            + "\n".join(f"{c.name} | {c.authority_id} | SPECIES | " for c in candidates)})
        lookup = answer.taxonomy_lookup.model_copy(update={"status": LookupStatus.AMBIGUOUS,
            "candidates": [{"key": key, "scientificName": name} for key, name in usages.items()]})
        return SourceAnswer("gbif", query, LookupStatus.AMBIGUOUS, candidates, evidence, note="ambiguous",
            taxonomy_lookup=lookup)


async def undecided(task, readings, tools):
    answer = await tools.lookup("gbif", LABEL["taxon"], field_key=task.key)
    return FieldOutcome(task.key, FieldAnswer(outcome="several_possibilities",
        options=[c.name for c in answer.candidates], source_evidence_ids=[answer.evidence.id],
        explanation="GBIF cannot settle the name."), evidence=[answer.evidence],
        lookups=[answer.taxonomy_lookup], model_calls=1)


class UnmatchedVariant(UndecidedTaxon):
    """As UndecidedTaxon for the label's name; GBIF has no match for any other."""

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "gbif" or query == LABEL["taxon"]:
            return answer
        evidence = answer.evidence.model_copy(update={"kind": "lookup", "excerpt": "GBIF has no match"})
        lookup = answer.taxonomy_lookup.model_copy(update={"status": LookupStatus.NO_MATCH, "candidates": []})
        return SourceAnswer("gbif", query, LookupStatus.NO_MATCH, (), evidence, note="no match",
            taxonomy_lookup=lookup)


async def undecided_then_a_variant(task, readings, tools):
    """The label's name (ambiguous), then a variant spelling (no match)."""
    outcome = await undecided(task, readings, tools)
    variant = await tools.lookup("gbif", "Danaus plexipus", field_key=task.key)
    outcome.evidence.append(variant.evidence)
    outcome.lookups.append(variant.taxonomy_lookup)
    return outcome


def written_undecided(rig, script=undecided, sources=UndecidedTaxon):
    """A researched run in review on its taxon alone, GBIF's answer ambiguous,
    after the reviewer's field decision that the label writes the name."""
    mounted(rig, Scripted({"taxon": script}), sources=sources)
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (done.disposition, done.fields["taxon"].state) == (Disposition.REVIEW, ValueState.AMBIGUOUS)
    # The lookup a reviewer chooses from is the run's last (api.apply_decision).
    assert done.lookups[-1].status == LookupStatus.AMBIGUOUS
    client = review_client(rig)
    taxon = done.fields["taxon"]
    written = decide(client, rig, "field-taxon", "field", target_id="taxon",
        after=taxon.model_dump(mode="json", exclude={"evidence_ids"})
        | {"state": "supported", "literal": LABEL["taxon"], "reason": "The label writes this name."},
        evidence_ids=list(taxon.evidence_ids))
    assert written.reasons == ["taxonomy_unresolved", "human_approval_required"]
    return client


def test_a_reviewers_choice_of_one_of_gbifs_candidates_clears_the_taxon_on_approval(rig):
    client = written_undecided(rig)
    chosen = decide(client, rig, "choose-taxon", "taxonomy_resolution", after={"authority_id": HOMONYM_KEY})
    taxon = chosen.fields["taxon"]
    assert (taxon.literal, taxon.normalized, taxon.authority_id) == (LABEL["taxon"], HOMONYM_NAME, HOMONYM_KEY)
    assert (chosen.disposition, chosen.reasons) == (Disposition.REVIEW, ["human_approval_required"])
    approved = decide(client, rig, "approve-taxon", "approve")
    assert (approved.stage, approved.disposition, approved.reasons) == ("finalized", Disposition.CLEARED, [])
    # A later pass (an operator's retry) reaches the recheck: still cleared,
    # nothing researched again.
    retried = rig.repository.get(rig.principal.scope, rig.specimen.id).model_copy(deep=True)
    retried.run.stage, retried.run.disposition = rig.workflow.next_step(retried.run).split(":")[0], None
    saved = rig.repository.save(rig.principal, retried, retried.version, "retry", "retry")
    again = rig.workflow.step(rig.principal, saved.id).run
    assert (again.stage, again.disposition, again.reasons) == ("finalized", Disposition.CLEARED, [])
    assert again.attempts[FIELD_RESEARCH] == 1 and again.paid_calls == approved.paid_calls


def test_a_lookup_with_no_candidates_is_never_the_one_a_reviewer_chooses_from(rig):
    """The review's N1: the expert asks the label's name (ambiguous), then a
    variant (no match). The reviewer still chooses from the name's candidates."""
    client = written_undecided(rig, undecided_then_a_variant, UnmatchedVariant)
    run = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert [lookup.status for lookup in run.lookups] == [LookupStatus.NO_MATCH, LookupStatus.AMBIGUOUS]
    chosen = decide(client, rig, "choose-taxon", "taxonomy_resolution", after={"authority_id": HOMONYM_KEY})
    assert (chosen.fields["taxon"].normalized, chosen.fields["taxon"].authority_id) == (HOMONYM_NAME, HOMONYM_KEY)
    approved = decide(client, rig, "approve-taxon", "approve")
    assert (approved.disposition, approved.reasons) == (Disposition.CLEARED, [])


def test_the_lookup_for_the_labels_whole_name_is_last_among_those_with_candidates():
    def lookup(name, status=LookupStatus.AMBIGUOUS, candidates=({"key": "1"},)):
        return Lookup(provider="gbif", adapter_version="test", query={"name": name}, status=status,
            candidates=list(candidates))

    whole, variant, failed = lookup("Danaus plexippus"), lookup("Danaus plexipus"), lookup(
        "Danaus", LookupStatus.PROVIDER, ())
    run = SimpleNamespace(lookups=[whole, variant, failed])
    field_step._choosable_lookup_last(run, (), ["Danaus plexippus (Linnaeus, 1758)"])
    assert run.lookups == [variant, failed, whole]
    # No grounded name: the last with candidates.
    run = SimpleNamespace(lookups=[variant, failed])
    field_step._choosable_lookup_last(run, (), ["sp. 30"])
    assert run.lookups == [failed, variant]
    # None with candidates: nothing moves.
    run = SimpleNamespace(lookups=[failed, lookup("x", LookupStatus.NO_MATCH, ())])
    before = list(run.lookups)
    field_step._choosable_lookup_last(run, (), ["Danaus plexippus"])
    assert run.lookups == before


def test_a_taxon_no_recorded_choice_of_gbifs_names_stays_in_review(rig):
    client = written_undecided(rig)
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    # A name GBIF never returned cannot be chosen.
    response = client.post(f"/v1/organizations/{ORG}/specimens/{current.id}/decisions",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": "choose-unknown"},
        json={"expected_revision": current.version, "base_record_version_id": f"{current.run.id}:{current.version}",
            "kind": "taxonomy_resolution", "after": {"authority_id": "5133111"}, "reason": "Reviewed."})
    assert response.status_code == 422
    # GBIF's other usage typed in as a correction is no recorded choice.
    taxon = current.run.fields["taxon"]
    after = taxon.model_dump(mode="json", exclude={"evidence_ids"})
    decide(client, rig, "field-usage", "field", target_id="taxon", evidence_ids=list(taxon.evidence_ids),
        after=after | {"normalized": HOMONYM_NAME, "authority_id": HOMONYM_KEY})
    held = decide(client, rig, "approve-usage", "approve")
    assert (held.disposition, held.reasons) == (Disposition.REVIEW, ["taxonomy_unresolved"])
    # Nor is a correction that keeps the recorded choice but names another usage.
    chosen = decide(client, rig, "choose-taxon", "taxonomy_resolution", after={"authority_id": HOMONYM_KEY})
    taxon = chosen.fields["taxon"]
    decide(client, rig, "field-other", "field", target_id="taxon", evidence_ids=list(taxon.evidence_ids),
        after=taxon.model_dump(mode="json", exclude={"evidence_ids"}) | {"normalized": GBIF_NAME,
            "authority_id": GBIF_KEY})
    held = decide(client, rig, "approve-other", "approve")
    assert (held.disposition, held.reasons) == (Disposition.REVIEW, ["taxonomy_unresolved"])


def test_only_a_recorded_choice_of_a_candidate_in_a_stored_lookup_decides_a_taxon():
    lookup = Lookup(provider="gbif", adapter_version="test", query={"name": LABEL["taxon"]},
        status=LookupStatus.AMBIGUOUS, candidates=[{"key": GBIF_KEY, "scientificName": GBIF_NAME},
            {"usage": {"key": HOMONYM_KEY, "scientificName": HOMONYM_NAME}, "diagnostics": {"matchType": "EXACT"}}])

    def choice(source=lookup.id, key=HOMONYM_KEY, kind="authority_selection"):
        return Evidence(kind=kind, source=source, locator="candidate:" + key, excerpt="chosen")

    def decided(row, *, value=HOMONYM_NAME, key=HOMONYM_KEY, cited=True, lookups=(lookup,)):
        taxon = FieldValue(state=ValueState.SUPPORTED, literal=LABEL["taxon"], normalized=value, authority_id=key,
            evidence_ids=[row.id] if cited else [])
        return field_step.taxon_decided(taxon, (), {row.id: row}, lookups)

    assert decided(choice())  # GBIF's alternative usage, as api.apply_decision records the choice
    assert decided(choice(key=GBIF_KEY), value=GBIF_NAME, key=GBIF_KEY)
    assert not decided(choice(), cited=False)
    assert not decided(choice(), lookups=())
    assert not decided(choice(), lookups=(lookup.model_copy(update={"status": LookupStatus.NO_MATCH}),))
    assert not decided(choice(source="authority-result"))  # an authority_resolution's choice
    assert not decided(choice(kind="authority"))
    assert not decided(choice(key="5133111"), value="Danaus fictus", key="5133111")
    assert not decided(choice(), value=GBIF_NAME)
    assert not decided(choice(), key=GBIF_KEY)


def test_on_a_label_with_no_decided_transcript_the_way_out_is_a_transcription_decision(tmp_path):
    """FIELD_RESEARCH.md, after field research: readers that differ go to
    review; a reviewer's correction of the field, approved, leaves
    unresolved_transcription (the corrected value has no raw reading behind
    it); a transcription decision researches the label again, paid again."""
    rig = build_rig(tmp_path, TEXT, SMYTH, candidates=every_field(*SMITH_OR_SMYTH))
    mounted(rig, Scripted({"collectors": answering(resolved("J. Smith", reading="1A"))}))
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    region = done.regions[0].id
    assert (done.disposition, done.reasons) == (Disposition.REVIEW,
        [f"unresolved_transcription:{region}", "mandatory_unresolved:collectors"])
    client = review_client(rig)
    collectors = done.fields["collectors"]
    after = collectors.model_dump(mode="json", exclude={"evidence_ids"}) | {"state": "supported",
        "literal": "J. Smith", "reason": "The label reads Smith."}
    decide(client, rig, "field-1", "field", target_id="collectors", after=after,
        evidence_ids=list(collectors.evidence_ids))
    approved = decide(client, rig, "approve-1", "approve")
    assert (approved.disposition, approved.reasons) == (Disposition.REVIEW, [f"unresolved_transcription:{region}"])
    corrected = decide(client, rig, "transcription-1", "transcription", target_id=region,
        after={"text": TEXT, "state": "supported"})
    assert corrected.stage == "parse" and FIELD_RESEARCH not in corrected.completed_steps
    mounted(rig, Scripted())
    rig.workflow.step(rig.principal, rig.specimen.id)  # parse
    again = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert again.attempts[FIELD_RESEARCH] == 2 and f"unresolved_transcription:{region}" not in again.reasons
    assert [call["attempt"] for call in again.paid_calls if call["step"] == FIELD_RESEARCH] == [1, 2]


def test_a_transcription_correction_researches_the_reparsed_fields_again(rig):
    mounted(rig, Scripted())
    rig.workflow.step(rig.principal, rig.specimen.id)
    client = review_client(rig)
    region = rig.specimen.run.regions[0].id
    corrected = decide(client, rig, "transcription-1", "transcription", target_id=region,
        after={"text": TEXT, "state": "supported"})
    assert corrected.stage == "parse" and FIELD_RESEARCH not in corrected.completed_steps
    second = Scripted()
    mounted(rig, second)
    rig.workflow.step(rig.principal, rig.specimen.id)  # parse
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    # Every field with a source or a check again (the organiser's collectors
    # candidate, added after parse by the rig, is gone with the new parse).
    assert RESEARCHED <= set(second.calls) and done.attempts[FIELD_RESEARCH] == 2
    assert done.completed_steps[-1] == FIELD_RESEARCH


# ---- fields the label does not state (owner decision A, 2026-10-09) ------------

# The pilot profile's "not on the label" list (contracts.NOT_ON_LABEL) but the city.
ABSENT = ("county", "collection_code", "collection_method", "date_identified", "habitat", "elevation_from_m",
    "elevation_to_m", "elevation_from_ft", "elevation_to_ft", "precise_location")
ELEVATIONS = ("elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft")
# The synthetic label without them: its country, state and city, catalogue number,
# collecting date, collectors, D/T/S line and taxon.
SPARSE = label_with(**dict.fromkeys(ABSENT, None))


def lacking(*keys, **scripts):
    """Every field's expert as default_script, and these fields' experts find
    nothing on the label."""
    return Scripted({**{key: answering(LACKS) for key in keys}, **scripts})


def not_on_label_rows(run, key):
    evidence = {item.id: item for item in run.evidence}
    return [evidence[i] for i in run.fields[key].evidence_ids if evidence[i].locator == field_step.NOT_ON_LABEL_CHECK]


def cleared_as_not_on_label(run):
    """The fields the clearance rules take as not on the label (step.not_on_label)."""
    allowed = field_step.not_on_label_keys(field_step.profile_of(run))
    evidence = {item.id: item for item in run.evidence}
    return {key for key, value in run.fields.items() if field_step.not_on_label(key, value, run, evidence, allowed)}


def unresolved(*keys):
    return [f"mandatory_unresolved:{key}" for key in sorted(keys)]


def test_the_listed_fields_a_label_does_not_state_clear_as_not_on_the_label(tmp_path):
    """The label states none of ten listed fields and their experts find
    none: each clears as not on the label, citing one check row that names
    every reading. Its city is on the label: a precise location counts as not
    on the label only beside a settled city or county, so on a label that
    lacks the city too it alone stays for a person."""
    rig = build_rig(tmp_path, SPARSE)
    run = rig.specimen.run
    settle(rig, lacking(*ABSENT))
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    assert cleared_as_not_on_label(run) == set(ABSENT)
    readings = field_step.run_readings(run)
    for key in ABSENT:
        value = run.fields[key]
        [row] = not_on_label_rows(run, key)
        assert (value.state, value.literal, value.parsed, value.authority_id) == (
            ValueState.NOT_PRESENT, None, None, None)
        assert value.reason.startswith("Not on the label:") and value.evidence_relations[row.id] == "supports"
        assert (row.kind, row.source, row.locator) == ("derived", "field_research", "check:not_on_label")
        assert row.excerpt == field_step.not_on_label_excerpt(key, readings)
        assert all(r.name in row.excerpt and r.observation_id in row.excerpt for r in readings)
        assert row.raw_ref and row.digest
    verify_evidence(rig.specimen, rig.blobs)

    (tmp_path / "no-city").mkdir()
    rig = build_rig(tmp_path / "no-city", label_with(**dict.fromkeys((*ABSENT, "city"), None)))
    run = rig.specimen.run
    settle(rig, lacking(*ABSENT, "city"))
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, unresolved("precise_location"))
    assert cleared_as_not_on_label(run) == set(ABSENT) - {"precise_location"} | {"city"}


def test_collectors_the_label_does_not_state_still_go_to_review(tmp_path):
    rig = build_rig(tmp_path, SPARSE.replace("\nleg. J. Smith", ""), candidates=[])
    run = rig.specimen.run
    settle(rig, lacking(*ABSENT))
    assert run.fields["collectors"].state == ValueState.NOT_PRESENT
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, unresolved("collectors"))
    assert cleared_as_not_on_label(run) == set(ABSENT) and not not_on_label_rows(run, "collectors")


def test_a_field_whose_line_the_label_writes_never_clears_as_not_on_the_label(tmp_path):
    """The county line is on the label, and its expert says it is not."""
    rig = build_rig(tmp_path, label_with(**dict.fromkeys(set(ABSENT) - {"county"}, None)))
    run = rig.specimen.run
    settle(rig, lacking(*ABSENT))
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, unresolved("county"))
    assert not not_on_label_rows(run, "county") and "county" not in cleared_as_not_on_label(run)


def add_a_reader(run):
    """A third reader of the label, after research."""
    run.observations.append(run.observations[1].model_copy(update={"id": "third-reader",
        "route_id": "third-route", "model_id": "synthetic-third"}))


def forget_the_row(run):
    """The county as a record from before the rule stored it: not present, no row."""
    run.fields["county"] = FieldValue(state=ValueState.NOT_PRESENT, reason="Not on the label.")


@pytest.mark.parametrize(("case", "other", "change", "kept"), [
    # A reader marked part of the label unreadable.
    ("unreadable span", None, None, ABSENT),
    # The raw reader (not the decided one) writes an elevation: no elevation clears.
    ("elevation in a reading", SPARSE + "\n1500 ft", None, ELEVATIONS),
    # The rows name the readings research saw; a reader added since makes them stale.
    ("stale row", None, add_a_reader, ABSENT),
    # A not-present value with no row never clears on a re-check.
    ("old value", None, forget_the_row, ("county",)),
], ids=["unreadable-span", "elevation-in-a-reading", "stale-row", "old-value-under-refinalize"])
def test_a_listed_field_stays_in_review_when_the_label_or_its_record_is_in_doubt(tmp_path, case, other, change, kept):
    rig = build_rig(tmp_path, SPARSE, other, decided=other is not None)
    run = rig.specimen.run
    if case == "unreadable span":
        run.observations[1].unreadable_spans = ["0:3"]
    settle(rig, lacking(*ABSENT))
    if change is not None:
        assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
        change(run)
        field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, unresolved(*kept))
    allowed = field_step.not_on_label_keys(field_step.profile_of(run))
    evidence = {item.id: item for item in run.evidence}
    assert not any(field_step.not_on_label(key, run.fields[key], run, evidence, allowed) for key in kept)
    assert cleared_as_not_on_label(run) == set(ABSENT) - set(kept)


GUATEMALAN_TOWN = label_with(**dict.fromkeys(ABSENT, None), country="Guatemala",
    province_state="Chimaltenango", city="Yepocapa")
IN_YEPOCAPA = {"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
    "province_state": from_tgn("Chimaltenango", "Chimaltenango", None, "tgn:1000565"),
    "city": confirming("Yepocapa", reading="1A", within=("Chimaltenango", "Guatemala"))}
NO_TOWN = answering(FieldAnswer(outcome="sources_cannot_resolve", explanation="No match."))


@pytest.mark.parametrize(("place", "city", "kept"), [
    # The organiser's precise location is the town, the settled city's own text.
    ("Yepocapa", None, ()),
    # A precise location finer than the town.
    ("nr. Yepocapa", None, ("precise_location",)),
    # The town is not settled.
    ("Yepocapa", NO_TOWN, ("city", "precise_location")),
], ids=["the-city-itself", "finer-than-the-city", "city-unresolved"])
def test_a_precise_location_is_not_on_the_label_only_beside_a_settled_city_holding_its_text(
        tmp_path, place, city, kept):
    """A town-only label (105526328 to 105526330): the organiser gives the
    town's line, or a finer one, as the precise location too."""
    text = GUATEMALAN_TOWN + ("" if place == "Yepocapa" else "\n" + place)
    quote = "city: Yepocapa" if place == "Yepocapa" else place
    rig = build_rig(tmp_path, text, candidates=[*COLLECTORS,
        *(("precise_location", name, place, quote) for name in ("1A", "1B"))])
    run = rig.specimen.run
    scripts = {**IN_YEPOCAPA, **({"city": city} if city else {})}
    settle(rig, lacking(*ABSENT, **scripts), tools=Gazetteer(rig.blobs))
    assert run.fields["precise_location"].state == ValueState.NOT_PRESENT
    assert (run.disposition, run.reasons) == (Disposition.REVIEW if kept else Disposition.CLEARED, unresolved(*kept))
    assert ("precise_location" in cleared_as_not_on_label(run)) is not kept


# ---- a taxon that names no genus (owner decision B, 2026-10-09) -----------------

MORPHOCODE = "sp. 30 \N{FEMALE SIGN}"


class NoGenus(FakeSources):
    """GBIF as the record's sources answer a name it cannot read
    (sources.ApprovedSources._taxon, application.lookup.no_name_lookup): no
    match, nothing sent, no stored response."""

    def _answer(self, source_id, query):
        from specimen_digitization.application.lookup import no_name_lookup
        from specimen_digitization.research_harness.taxonomy import taxonomy_scientific_name

        if source_id != "gbif" or taxonomy_scientific_name(query) is not None:
            return super()._answer(source_id, query)
        return SourceAnswer("gbif", query, LookupStatus.NO_MATCH, (), None,
            note="The query writes no scientific name, so nothing was sent to GBIF",
            taxonomy_lookup=no_name_lookup(query))


def cannot_resolve(literal, *, asks=(), reading="1A"):
    """A taxon expert: GBIF asked each of `asks`, then sources_cannot_resolve quoting `literal`."""
    async def script(task, readings, tools):
        found = [await tools.lookup("gbif", query, field_key=task.key) for query in asks]
        return FieldOutcome(task.key, FieldAnswer(outcome="sources_cannot_resolve", literal=literal,
            reading_names=[reading], source_evidence_ids=[a.evidence.id for a in found if a.evidence],
            explanation="GBIF cannot resolve the name."), evidence=[a.evidence for a in found if a.evidence],
            lookups=[a.taxonomy_lookup for a in found if a.taxonomy_lookup], model_calls=1)
    return script


def morphocoded(code):
    return TEXT.replace("taxon: Danaus plexippus", "taxon: " + code)


def label_texts(run):
    """Every reading's text, as the clearance rules read the label."""
    return [reading.text for reading in field_step.run_readings(run)]


# 105526321's second label: the first pass decided 2A's "sp. 30 <female sign>"; 2B writes "Sp.30 <female sign>".
VARIANT = "Sp.30 \N{FEMALE SIGN}"


@pytest.mark.parametrize(("asked", "other"), [(True, None), (False, None), (True, VARIANT)],
    ids=["expert-asked-gbif", "step-adds-the-lookup", "decided-reading-beside-a-variant"])
def test_a_taxon_that_names_no_genus_clears_as_written_and_unmatched(tmp_path, asked, other):
    rig = build_rig(tmp_path, morphocoded(MORPHOCODE), other and morphocoded(other), decided=bool(other),
        candidates=[*COLLECTORS, *([("taxon", "1B", other, "taxon: " + other)] if other else [])])
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve(MORPHOCODE, asks=[MORPHOCODE] if asked else [])}),
        tools=NoGenus(rig.blobs))
    if other:
        # The other reader's text is evidence only (G19), kept as contradicting it.
        assert cited_rows(run, "taxon")["taxon: " + other] == "contradicts"
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.parsed, taxon.normalized, taxon.authority_id, taxon.layer) == (
        ValueState.SUPPORTED, MORPHOCODE, MORPHOCODE, None, None, "settled")
    assert taxon.reason == "Unmatched: the label names no genus, so GBIF has nothing to match"
    assert (taxon.input_source, taxon.source_region_id) == ("decided_transcript", run.regions[0].id)
    evidence = {item.id: item for item in run.evidence}
    [row] = [evidence[i] for i in taxon.evidence_ids if evidence[i].locator == "check:taxon_no_genus"]
    [lookup] = run.lookups
    assert (lookup.provider, lookup.status, lookup.query, lookup.candidates) == ("gbif", LookupStatus.NO_MATCH, {}, [])
    assert lookup.metadata["verbatim_name"] == MORPHOCODE and lookup.id in row.excerpt and MORPHOCODE in row.excerpt
    assert (row.kind, taxon.evidence_relations[row.id]) == ("derived", "supports")
    assert field_step.taxon_unmatched(taxon, evidence, run.lookups, texts=label_texts(run))
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    verify_evidence(rig.specimen, rig.blobs)


def gbif_again(messages, info):
    """A taxon expert's model that asks GBIF the code again and again."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    return ModelResponse(parts=[ToolCallPart("lookup", {"source": "gbif", "query": MORPHOCODE})])


def a_piece_again(messages, info):
    """A taxon expert's model that asks GBIF the code, then keeps resolving a
    piece of it, which its answer's checks refuse."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

    if not any(isinstance(part, ToolReturnPart) for m in messages if isinstance(m, ModelRequest) for part in m.parts):
        return gbif_again(messages, info)
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"outcome": "resolved", "literal": "sp. 30",
        "reading_names": ["1A"], "explanation": "A piece."})])


@pytest.mark.parametrize(("model", "fallback"), [(gbif_again, "EXHAUSTED"), (a_piece_again, "UNCHECKED")],
    ids=["out-of-requests", "answers-it-cannot-check"])
def test_an_experts_fallback_never_clears_a_taxon_as_unmatched(tmp_path, model, fallback):
    """The resolver's own sources_cannot_resolve (experts.EXHAUSTED,
    experts.UNCHECKED) is no answer of the expert's, even after GBIF was asked."""
    from pydantic_ai.models.function import FunctionModel

    from specimen_digitization.field_research import experts
    from specimen_digitization.field_research.budget import CostMeter

    resolver = experts.make_resolver(model_factory=lambda: FunctionModel(model),
        meter=CostMeter(1_000_000, input_micros_per_million=200_000, output_micros_per_million=600_000))

    async def expert(task, readings, tools):
        return await resolver(task, readings, {}, tools=tools)

    rig = build_rig(tmp_path, morphocoded(MORPHOCODE))
    run = rig.specimen.run
    prepared, outcomes, calls = research(rig, Scripted({"taxon": expert}), tools=NoGenus(rig.blobs))
    [outcome] = [item for item in outcomes if item.key == "taxon"]
    assert (outcome.answer.outcome, outcome.answer.explanation, outcome.failure) == (
        "sources_cannot_resolve", getattr(experts, fallback), None)
    assert [call.source_id for call in calls if call.field_key == "taxon"][:1] == ["gbif"]
    apply_outcomes(run, None, prepared[1], outcomes, blobs=rig.blobs, calls=calls)
    finalize_fields(run, None, outcomes, specimen=rig.specimen, blobs=rig.blobs, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["mandatory_unresolved:taxon", "taxonomy_unresolved"])
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert not [item for item in run.evidence if item.locator == "check:taxon_no_genus"]


def test_an_answer_that_neither_asked_gbif_nor_quoted_the_code_never_clears_a_taxon(tmp_path):
    """Owner decision B needs the expert's own finding: a lookup that GBIF
    cannot settle, or the code it quotes from a reading."""
    rig = build_rig(tmp_path, morphocoded(MORPHOCODE))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": answering(FieldAnswer(outcome="sources_cannot_resolve",
        explanation="Nothing to look up."))}), tools=NoGenus(rig.blobs))
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["mandatory_unresolved:taxon", "taxonomy_unresolved"])
    assert not [item for item in run.evidence if item.locator == "check:taxon_no_genus"]


class Homonym(FakeSources):
    """GBIF's answer for "Epipsocus" (105526328): two genera of that name, neither decided."""

    def _answer(self, source_id, query):
        answer = super()._answer(source_id, query)
        if source_id != "gbif":
            return answer
        usages = {"1045361": "Epipsocus Hagen, 1866", "9999001": "Epipsocus Enderlein, 1903"}
        candidates = tuple(SourceCandidate(name=name, authority_id=key, kind="GENUS") for key, name in usages.items())
        evidence = answer.evidence.model_copy(update={"locator": None, "excerpt": "GBIF cannot settle the name\n"
            + "\n".join(f"{c.name} | {c.authority_id} | GENUS | " for c in candidates)})
        lookup = answer.taxonomy_lookup.model_copy(update={"status": LookupStatus.AMBIGUOUS,
            "candidates": [{"key": key, "scientificName": name} for key, name in usages.items()]})
        return SourceAnswer("gbif", query, LookupStatus.AMBIGUOUS, candidates, evidence, note="ambiguous",
            taxonomy_lookup=lookup)


def test_a_taxon_with_a_genus_gbif_cannot_decide_still_goes_to_review(tmp_path):
    written = "Epipsocus sp. 1"
    rig = build_rig(tmp_path, TEXT.replace("taxon: Danaus plexippus", "taxon: " + written))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve(written, asks=["Epipsocus"])}), tools=Homonym(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal) == (ValueState.UNRESOLVED, written)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["mandatory_unresolved:taxon", "taxonomy_unresolved"])
    assert not field_step.taxon_unmatched(taxon, {item.id: item for item in run.evidence}, run.lookups,
        texts=label_texts(run))
    assert not [item for item in run.evidence if item.locator == "check:taxon_no_genus"]


# The blocking finding (B1) of #289's review: the organiser's candidate is only
# the code, and the label writes the genus beside it.
EPIPSOCUS_CODE = "sp. 1 \N{FEMALE SIGN}"
GENUS_BESIDE = {
    # 105526328's label 2: "Epipsocus", then "sp. 1" on the next line.
    "genus-on-the-line-above": ("Epipsocus\n" + EPIPSOCUS_CODE, EPIPSOCUS_CODE),
    # The quote is the whole line.
    "genus-earlier-on-the-line": ("Epipsocus " + EPIPSOCUS_CODE, "Epipsocus " + EPIPSOCUS_CODE),
}


@pytest.mark.parametrize(("written", "quote"), GENUS_BESIDE.values(), ids=GENUS_BESIDE)
def test_a_code_the_label_writes_beside_a_genus_goes_to_review(tmp_path, written, quote):
    """GBIF cannot decide "Epipsocus" (a homonym), and the expert says so,
    quoting the organiser's candidate "sp. 1": the label names a genus, so
    the taxon is not cleared as unmatched."""
    rig = build_rig(tmp_path, TEXT.replace("taxon: Danaus plexippus", written), candidates=[*COLLECTORS,
        *(("taxon", name, EPIPSOCUS_CODE, quote) for name in ("1A", "1B"))])
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve(EPIPSOCUS_CODE, asks=["Epipsocus"])}), tools=Homonym(rig.blobs))
    taxon = run.fields["taxon"]
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["mandatory_unresolved:taxon", "taxonomy_unresolved"])
    assert taxon.state == ValueState.UNRESOLVED and taxon.layer is None
    assert not [item for item in run.evidence if item.locator == "check:taxon_no_genus"]
    assert not field_step.taxon_unmatched(taxon, {item.id: item for item in run.evidence}, run.lookups,
        texts=label_texts(run))


def test_an_unmatched_taxon_meets_the_agreement_rules_any_answer_meets(tmp_path, monkeypatch):
    """The unmatched value goes through agreement.refusal: were the label
    check to miss the genus, #284's guard against a candidate that cuts its
    quoted name ("sp. 1" quoting "Epipsocus sp. 1") still refuses it."""
    from specimen_digitization.field_research import checks

    monkeypatch.setattr(checks, "label_names_no_genus", lambda code, texts: True, raising=False)
    written, quote = GENUS_BESIDE["genus-earlier-on-the-line"]
    rig = build_rig(tmp_path, TEXT.replace("taxon: Danaus plexippus", written), candidates=[*COLLECTORS,
        *(("taxon", name, EPIPSOCUS_CODE, quote) for name in ("1A", "1B"))])
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve(EPIPSOCUS_CODE, asks=["Epipsocus"])}), tools=Homonym(rig.blobs))
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["mandatory_unresolved:taxon", "taxonomy_unresolved"])
    assert run.fields["taxon"].state == ValueState.UNRESOLVED
    assert not [item for item in run.evidence if item.locator == "check:taxon_no_genus"]


# The pilot's morphocodes that clear as unmatched, as their labels write them
# (the text before the code, the code, the text after it).
PILOT_CODES = {
    # 105526321's second label: its habitat line, then the code.
    "105526321": ("10-6-78-la\nMossy forest 6400'\n", "sp. 30 \N{FEMALE SIGN}", ""),
    # 105526326's third label: the code on a label of its own.
    "105526326": ("", "Sp. 22", "\n\N{FEMALE SIGN} wings"),
    # 105526327's third label: a slide code, the code, then "legs".
    "105526327": ("V-4-67-1\n", "sp 22", "\nlegs"),
}


@pytest.mark.parametrize(("before", "code", "after"), PILOT_CODES.values(), ids=PILOT_CODES)
def test_the_pilots_codes_with_no_genus_beside_them_still_clear_as_unmatched(tmp_path, before, code, after):
    rest = TEXT.replace("taxon: Danaus plexippus\n", "")
    text = before + code + after + "\n" + rest if not before else rest + "\n" + before + code + after
    rig = build_rig(tmp_path, text, candidates=[*COLLECTORS, *(("taxon", name, code, code) for name in ("1A", "1B"))])
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve(code)}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.reason) == (ValueState.SUPPORTED, code, field_step.UNMATCHED)
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])


def test_a_later_pass_judges_the_label_of_an_unmatched_taxon_again(tmp_path):
    """The clearance rules read the stored value's label too: text that now
    writes a genus before the code takes the clearance back."""
    rig = build_rig(tmp_path, morphocoded(MORPHOCODE))
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve(MORPHOCODE)}), tools=NoGenus(rig.blobs))
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    for item in run.observations:
        item.literal_text = item.literal_text.replace("taxon: ", "taxon: Epipsocus\n")
    for item in run.transcripts:
        item.text = item.text.replace("taxon: ", "taxon: Epipsocus\n")
    field_step.refinalize(run, today=TODAY)
    assert (run.disposition, run.reasons) == (Disposition.REVIEW, ["taxonomy_unresolved"])


@pytest.mark.parametrize(("other", "decided"), [("sp. 39", False), ("Sp.30", False), ("sp. 39", True)],
    ids=["no-first-pass-pick", "no-pick-same-code", "decided-but-another-code"])
def test_readers_that_write_different_morphocodes_stay_in_review(tmp_path, other, decided):
    """1A writes "sp. 30" and 1B something else, and GBIF matches neither:
    with no first-pass pick even the same code written differently stays,
    and a decided reading never settles beside another reader's other code."""
    taxa = [("taxon", "1A", "sp. 30", "taxon: sp. 30"), ("taxon", "1B", other, "taxon: " + other)]
    # With a decided transcript the keyed-line parser gives 1A's candidates itself.
    candidates = [*COLLECTORS, taxa[1]] if decided else every_field(*taxa)
    rig = build_rig(tmp_path, morphocoded("sp. 30"), morphocoded(other), decided=decided, candidates=candidates)
    run = rig.specimen.run
    settle(rig, Scripted({"taxon": cannot_resolve("sp. 30", asks=["sp. 30", other])}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    assert taxon.state != ValueState.SUPPORTED
    assert {"mandatory_unresolved:taxon", "taxonomy_unresolved"} <= set(run.reasons)
    assert not field_step.taxon_unmatched(taxon, {item.id: item for item in run.evidence}, run.lookups,
        texts=label_texts(run))
    assert not [item for item in run.evidence if item.locator == "check:taxon_no_genus"]


def test_the_not_on_label_list_is_the_published_profiles_and_reaches_a_pinned_snapshot(rig):
    from specimen_digitization.field_research import contracts

    published = published_registry().profiles[0]
    [key] = contracts.NOT_ON_LABEL
    assert key == (published.id, published.version) == ("zoology_insects_slides", "1.0.0")
    listed = contracts.NOT_ON_LABEL[key]
    assert listed == {*ABSENT, "city"} and listed <= set(published.mandatory_fields)
    assert not listed & contracts.NEVER_NOT_ON_LABEL
    assert contracts.NEVER_NOT_ON_LABEL == {"fmnh_ins_number", "country", "date_visited_from", "date_visited_to",
        "collectors", "taxon"}
    # Keep today's behaviour.
    assert not {"province_state", "verbatim_dts", "identified_by_irn"} & listed
    # A run's pinned snapshot, as stored before this list existed (unchanged since
    # it was pinned), reaches the list through its id and version.
    run = rig.specimen.run
    assert digest(run.profile_snapshot) == run.dependencies["profile_snapshot_sha256"]
    assert "not_on_label" not in json.dumps(run.profile_snapshot)
    assert field_step.not_on_label_keys(field_step.profile_of(run)) == listed
    other = dict(run.profile_snapshot, version="1.0.1")
    assert field_step.not_on_label_keys(field_step.profile_of(SimpleNamespace(profile_snapshot=other))) == frozenset()


def test_a_retry_researches_a_field_marked_not_on_the_label_again_and_cites_only_its_new_row(tmp_path):
    rig = build_rig(tmp_path, SPARSE)
    mounted(rig, lacking(*ABSENT, country=failing("source_unavailable")))
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.stage, run.blocker) == ("retry_scheduled", "lookup_operational_failure")
    [first] = not_on_label_rows(run, "habitat")
    second = lacking(*ABSENT)
    mounted(rig, second)
    rig.clock.now += timedelta(hours=1)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert "habitat" in second.calls and (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    [row] = not_on_label_rows(run, "habitat")
    assert row.id != first.id and first.id in {item.id for item in run.evidence}
    assert cleared_as_not_on_label(run) == set(ABSENT)


MCKINLEY = "E. slope Mt. McKinley"


@pytest.mark.parametrize(("city", "kept"), [("Mt. McKinley", ()), ("Mt. Apo", ("city",))],
    ids=["inside-the-settled-locality", "a-place-of-its-own"])
def test_a_city_the_organiser_took_from_the_settled_precise_location_counts_as_absent(tmp_path, city, kept):
    """105526321's second label: the organiser offers "Mt. McKinley", part of
    the precise location the record settles, as the city."""
    text = label_with(**dict.fromkeys(set(ABSENT) - {"precise_location"}, None), city=None,
        precise_location=MCKINLEY) + ("" if city in MCKINLEY else "\n" + city)
    quote = "precise_location: " + MCKINLEY if city in MCKINLEY else city
    rig = build_rig(tmp_path, text, candidates=[*COLLECTORS, *(("city", name, city, quote) for name in ("1A", "1B"))])
    run = rig.specimen.run
    settle(rig, lacking(*(set(ABSENT) - {"precise_location"}), "city",
        precise_location=answering(resolved(MCKINLEY))))
    assert run.fields["precise_location"].state == ValueState.SUPPORTED
    assert (run.disposition, run.reasons) == (Disposition.REVIEW if kept else Disposition.CLEARED, unresolved(*kept))
    assert ("city" in cleared_as_not_on_label(run)) is not kept


def test_a_label_whose_coverage_is_not_confirmed_never_clears_a_field_as_not_on_the_label(tmp_path):
    rig = build_rig(tmp_path, SPARSE)
    run = rig.specimen.run
    run.coverage_confirmed = False
    settle(rig, lacking(*ABSENT))
    assert run.reasons == ["label_coverage_unconfirmed", *unresolved(*ABSENT)]
    assert not any(not_on_label_rows(run, key) for key in ABSENT)


def test_readers_of_an_undecided_label_that_write_one_morphocode_settle_it(tmp_path):
    """No first-pass pick (the readers differ on the habitat line), and both
    write "sp. 30" with a female sign: B1 settles the taxon on that text."""
    other = morphocoded(MORPHOCODE).replace("Synthetic grassland", "Synthetic grassIand")
    rig = build_rig(tmp_path, morphocoded(MORPHOCODE), other, candidates=every_field(
        *(("taxon", name, MORPHOCODE, "taxon: " + MORPHOCODE) for name in ("1A", "1B"))))
    run = rig.specimen.run
    assert {r.input_source for r in field_step.run_readings(run)} == {"raw_reading"}
    settle(rig, Scripted({"taxon": cannot_resolve(MORPHOCODE, asks=[MORPHOCODE])}), tools=NoGenus(rig.blobs))
    taxon = run.fields["taxon"]
    assert (taxon.state, taxon.literal, taxon.input_source) == (ValueState.SUPPORTED, MORPHOCODE, "raw_reading")
    assert set(taxon.verbatim_by_observation.values()) == {MORPHOCODE}
    assert field_step.taxon_unmatched(taxon, {item.id: item for item in run.evidence}, run.lookups,
        texts=label_texts(run))
    assert not [reason for reason in run.reasons if "taxon" in reason]


# ---- the fourth review's NB4: what the place rules say -----------------------

def test_readers_whose_place_texts_differ_by_a_unit_word_settle_on_the_place_confirming_both(tmp_path):
    """Each reader's text matches the candidate's name by the place
    comparison key, which drops unit words: "Chimaltenango Dept." and
    "Chimaltenango", both confirmed by Getty TGN's one department."""
    places = dict(country="Guatemala", county=None, city=None)
    rig = build_rig(tmp_path, label_with(**places, province_state="Chimaltenango Dept."),
        label_with(**places, province_state="Chimaltenango"), candidates=[*COLLECTORS,
            *(("country", name, "Guatemala", "country: Guatemala") for name in ("1A", "1B")),
            ("province_state", "1A", "Chimaltenango Dept.", "province_state: Chimaltenango Dept."),
            ("province_state", "1B", "Chimaltenango", "province_state: Chimaltenango")])
    run = rig.specimen.run

    async def province(task, readings, tools):
        found = await tools.lookup("tgn", "Chimaltenango", field_key=task.key)
        return FieldOutcome(task.key, resolved("Chimaltenango", authority_id="tgn:1000565", cited=[found.evidence.id],
            reading="1B"), evidence=[found.evidence], model_calls=1)
    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
        "province_state": province}), tools=Gazetteer(rig.blobs))
    value = run.fields["province_state"]
    assert (value.state, value.literal, value.authority_id) == (ValueState.SUPPORTED, "Chimaltenango", "tgn:1000565")
    assert set(value.verbatim_by_observation.values()) == {"Chimaltenango", "Chimaltenango Dept."}
    assert not reasons_for(run, "province_state")


@pytest.mark.parametrize(("province", "authority_id", "settles"), [
    # Getty TGN's nation lists itself as its parent: a province of the nation's own name.
    ("Guatemala", "tgn:1000621", True),
    ("Chimaltenango", "tgn:1000565", False),
])
def test_a_near_spelled_country_settles_beside_places_of_the_nations_own_name_only(
        tmp_path, province, authority_id, settles):
    rig = build_rig(tmp_path, label_with(country="Guatamala", province_state=province, county=None, city=None))
    run = rig.specimen.run
    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatamala", "Guatemala", "tgn:7005493"),
        "province_state": from_tgn(province, province, None, authority_id),
        **dict.fromkeys(("county", "city"), answering(LACKS))}), tools=Gazetteer(rig.blobs))
    country = run.fields["country"]
    if not settles:
        assert (country.state, country.reason) == (ValueState.UNRESOLVED, agreement.NEAR_UNFIT + " Settled.")
        return
    assert (country.state, country.literal, country.normalized) == (ValueState.SUPPORTED, "Guatamala", "Guatemala")
    assert "near_spelling:country" in [f.reason_code for f in run.findings] and not reasons_for(run, "country")
