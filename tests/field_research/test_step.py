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
from specimen_digitization.application.workflow import FIELD_RESEARCH, SyntheticAdapters, Workflow
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS, FieldAnswer, FieldOutcome, SourceAnswer, SourceCandidate,
)
from specimen_digitization.field_research.step import (
    FieldResearchStep, apply_outcomes, build_tasks, finalize_fields, research_fields,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_harness"))
from production_e2e_support import WORKER, worker_principal  # noqa: E402

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


def make_specimen(blobs, text=TEXT):
    """A non-sensitive specimen at adjudicate: one label, two agreeing readers."""
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
    for route in run.profile.routes:
        raw = ("SYNTHETIC FIXTURE " + route + "\n" + text).encode()
        run.observations.append(Observation(region_id=region.id, route_id=route, model_id="synthetic-" + route,
            provider="synthetic", prompt_version="prompt:" + route, input_sha256=crop, input_asset_id=asset.id,
            input_crop_ref=region.crop_ref, literal_text=text, raw_ref=blobs.put(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest()))
    run.completed_steps = ["pin_dependencies", "classify", "quality_check", "segment"] + [
        f"transcribe:{region.id}:{route}" for route in run.profile.routes]
    run.stage = "running"
    return specimen


@pytest.fixture
def rig(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    repository = SQLiteRepository(tmp_path / "records.sqlite")
    clock = SimpleNamespace(now=datetime(2026, 10, 8, 12, tzinfo=timezone.utc))
    workflow = Workflow(repository, blobs, SyntheticAdapters(blobs, TEXT), clock=lambda: clock.now)
    principal = worker_principal()
    created = repository.create(principal, make_specimen(blobs), "intake", "intake")
    workflow.step(principal, created.id)  # adjudicate
    parsed = workflow.step(principal, created.id)  # parse
    assert workflow.next_step(parsed.run) == "plan"
    # The organiser's candidate for the unkeyed collectors line, in both readings.
    run = parsed.run
    raw = b"organiser response"
    apply_candidates(run, parsed.asset.id, ExtractionOutput(candidates=[
        ExtractionCandidate(field_key="collectors", reading=name, literal="J. Smith", source_excerpt="leg. J. Smith")
        for name in ("1A", "1B")]), blobs.put(raw), hashlib.sha256(raw).hexdigest())
    parsed = repository.save(principal, parsed, parsed.version, "organiser", "organiser")
    return SimpleNamespace(blobs=blobs, repository=repository, workflow=workflow, principal=principal,
        specimen=parsed, clock=clock)


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

    def __init__(self, scripts=None, *, meter=None, delay=0.0):
        self.scripts, self.meter, self.delay = dict(scripts or {}), meter, delay
        self.calls, self.spans, self.active, self.peak = [], [], 0, 0

    async def __call__(self, task, readings, context, *, tools):
        self.calls.append(task.key)
        self.active += 1
        self.peak = max(self.peak, self.active)
        started = time.monotonic()
        try:
            await asyncio.sleep(self.delay)
            if self.meter is not None:
                ticket = await self.meter.reserve(100, 50)
                self.meter.settle(ticket, 100, 50)
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

def mounted(rig, resolver, tools_down=()):
    state = SimpleNamespace(meters=[], tools=[])

    def meter_factory(cap, price):
        meter = field_step.cost_meter(cap, price)
        state.meters.append(meter)
        resolver.meter = meter
        return meter

    @asynccontextmanager
    async def tools_factory(run, profile, blobs):
        tools = FakeSources(blobs, down=tools_down)
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
