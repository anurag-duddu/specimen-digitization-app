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
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS, FieldAnswer, FieldOutcome, SourceAnswer, SourceCandidate,
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


class FakeSources:
    """Approved sources: GBIF matches the taxon, GEOLocate the places, TGN nothing.
    Each distinct query is answered once and from the cache after, as sources.py does."""

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
        candidate = SourceCandidate(name=query, authority_id=f"{source_id}:{query}", kind="place")
        evidence = Evidence(kind="authority", source=source_id, locator=candidate.authority_id,
            excerpt=f"match\n{query} | {candidate.authority_id} | place | ", raw_ref=ref, digest=sha)
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
        answer = await tools.lookup("geolocate", LABEL[key], field_key=key)
        missing = await tools.lookup("tgn", LABEL[key], field_key=key)
        evidence = [answer.evidence, missing.evidence]
        result = resolved(LABEL[key], authority_id=answer.candidates[0].authority_id, cited=[answer.evidence.id])
    elif key == "fmnh_ins_number":
        result = resolved(LABEL[key], value="0010001")
    elif key == "elevation_from_ft":
        result = resolved("1500")  # As the experts write an elevation: the number alone.
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
    assert by_key["collectors"].answer.literal == "J. Smith" and by_key["collectors"].answer.reading_names == ["1A", "1B"]
    # No approved authority: no model call, the nonblocking exception.
    assert "identified_by_irn" not in resolver.calls and by_key["identified_by_irn"].finalized_without_model
    assert sorted(resolver.calls) == sorted(RESEARCHED)


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
    # GEOLocate supports a place; the lookup row TGN returned is kept with its one producing call.
    county = run.fields["county"]
    assert {evidence[i].source: r for i, r in county.evidence_relations.items()} == {
        "label": "supports", "geolocate": "supports"}
    tgn = [item for item in run.evidence if item.source == "tgn"]
    assert len(tgn) == 4 and all(sum(call.evidence_id == item.id for call in run.tool_calls) == 1 for item in tgn)
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
        [derived] = [evidence[i] for i in field.evidence_ids if evidence[i].kind == "derived"]
        assert value in derived.excerpt and field.evidence_relations[derived.id] == "decides"
        assert set(run.fields[sources[0]].evidence_ids) <= set(field.evidence_ids)
    # The stated value is never replaced.
    assert run.fields["elevation_from_ft"].literal == "1500" and run.fields["elevation_from_ft"].layer == "settled"


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
    assert run.fields["taxon"].normalized == GBIF_NAME and run.fields["county"].layer == "settled"


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
    assert second.calls == ["country"]
    run = done.run
    assert (run.stage, run.disposition, run.blocker, run.reasons) == ("finalized", Disposition.CLEARED, None, [])
    assert run.completed_steps[-1] == FIELD_RESEARCH and run.attempts[FIELD_RESEARCH] == 2
    assert [call["attempt"] for call in run.paid_calls] == [1, 2]
    assert run.paid_calls[1]["reserved_micros"] == 1_000_000 - spent
    assert run.usage.reserved_cost_micros == spent + 50 <= run.profile.execution.approved_cost_limit_micros
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


def written_undecided(rig):
    """A researched run in review on its taxon alone, GBIF's answer ambiguous,
    after the reviewer's field decision that the label writes the name."""
    mounted(rig, Scripted({"taxon": undecided}), sources=UndecidedTaxon)
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (done.disposition, done.fields["taxon"].state) == (Disposition.REVIEW, ValueState.AMBIGUOUS)
    assert [lookup.status for lookup in done.lookups] == [LookupStatus.AMBIGUOUS]
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
