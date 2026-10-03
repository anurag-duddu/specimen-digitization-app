"""One synthetic specimen through the production research harness entry point.

The worker composes compose_production_research_workflow over the ordinary
Workflow and steps the specimen under its worker deadline: the ordinary
adjudicate and parse steps, then, at plan, automatic provisioning and the six
research roles. Every layer is the production code except the Data Connect HTTP
session (an in-memory connector, production_e2e_support.FakeDataConnect), the
model (scripted pydantic-ai FunctionModels) and source HTTP (recorded responses).
Label text is the public synthetic fixture.

Stage 1, the publications land: the taxon, researched through the three ready
taxonomy sources, precise_location, settled from its label evidence, and the
parties and collection fields. Its geography historian makes no GEOLocate
lookup, so the geography fields wait on a source. The dates and elevations are
not published; each carries its mandatory_unresolved field reason. Stage 2,
with the historian's GEOLocate lookups: the country, state, county and city
publish with their GEOLocate evidence, and the run reaches its final queue,
needs_human_review, on the mandatory_unresolved field reasons.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from types import SimpleNamespace

import pytest

from specimen_digitization.application.native_drain import compose_registered_native_drain
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import OperationalBlock, SyntheticAdapters, Workflow
from specimen_digitization.research_harness.contracts import FieldKey
from specimen_digitization.research_harness.persistence import (
    DurabilityScope, ImmutableFileBlobs, SqliteStateBackend,
)
from specimen_digitization.research_harness.production_runtime import research_program_key
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

from production_e2e_support import (
    COLLECTION, FIXTURES, LABEL_TEXT, LABEL_VALUES, ORG, WORKER, FakeDataConnect, GenerationBlobs,
    fixture_source_transport, research_state, scripted_model_factory, specimen_before_adjudication,
    worker_principal,
)

SWITCH_ON = {"SPECIMEN_RESEARCH_HARNESS": "on"}
OTHER_OPERATOR = "offline-e2e-other-operator"
RESEARCH_OPERATIONS = {"GetCanonicalResearchBindingV2", "RegisterCanonicalResearchBindingV2",
    "GetCanonicalResearchMaterializationInputsV2", "PublishCanonicalResearchV2"}
COL_XR = "7ddf754f-d193-4cc9-b351-99906754a03b"
DATES_AND_ELEVATIONS = ("date_visited_from", "date_visited_to", "date_identified", "elevation_from_m",
    "elevation_to_m", "elevation_from_ft", "elevation_to_ft")
GBIF_NAME = "Danaus plexippus (Linnaeus, 1758)"
GEOGRAPHY = ("country", "province_state", "county", "city")
# GEOLocate's best Chicago match in the recorded glcwrap answer, as an opaque id
# (sources.geolocate_authority_id: a digest of its name, admin unit and point), and its point.
CHICAGO = "geolocate:79a9389b0ba6bcaf"
CHICAGO_POINT = ("41.850033", "-87.650052")
# Two decimal numbers side by side, however separated: a point written into a string.
COORDINATE_PAIR = re.compile(r"-?\d{1,3}\.\d+\s*[,;/ ]\s*-?\d{1,3}\.\d+")


class SimulatedCrash(Exception):
    """The worker process dies at this point; the next tick is a new process."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("the offline e2e test performs no HTTP")
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    members = {uid: [{"organization_id": ORG, "collection_id": COLLECTION, "role": "operator",
        "can_view_sensitive": False}] for uid in (WORKER, OTHER_OPERATOR)}
    backend.grant(DurabilityScope(ORG, COLLECTION, "membership", "membership", 1, WORKER, False))
    fake = FakeDataConnect(backend, members=members)
    blobs = GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    ordinary = Workflow(repository, blobs, SyntheticAdapters(blobs, LABEL_TEXT))
    token = actor_uid.set(WORKER)
    principal = worker_principal()
    created = repository.create(principal, specimen_before_adjudication(blobs), "e2e-intake", "e2e-intake")
    yield SimpleNamespace(fake=fake, backend=backend, repository=repository, ordinary=ordinary,
        principal=principal, specimen_id=created.id, research_blobs=ImmutableFileBlobs(tmp_path / "research"),
        model_calls=[], source_urls=[])
    actor_uid.reset(token)


def compose(rig, *, environ=SWITCH_ON, geolocate=True):
    """The production composer with the three offline seams; a new worker process each call.

    ``geolocate`` False: the geography historian makes no GEOLocate lookup."""
    return compose_production_research_workflow(rig.ordinary, repository=rig.repository, environ=environ,
        actor_uid=WORKER, state_backend=rig.backend,
        model_factory=scripted_model_factory(rig.model_calls, geolocate=geolocate),
        source_transport=fixture_source_transport(rig.source_urls), blobs=rig.research_blobs)


def supervised():
    return WorkerDeadline(time.monotonic() + 600).scope()


def to_plan(workflow, rig):
    """The ordinary chain: adjudicate, then parse; each saves one revision."""
    with supervised():
        adjudicated = workflow.step(rig.principal, rig.specimen_id)
        parsed = workflow.step(rig.principal, rig.specimen_id)
    assert (adjudicated.version, parsed.version) == (2, 3)
    assert adjudicated.run.transcripts[0].decision_kind == "identical_readings"
    assert rig.ordinary.next_step(parsed.run) == "plan" and len(parsed.run.fields) == 20
    return parsed


def jobs_and_bindings(rig):
    binding = rig.fake.bindings.get(rig.specimen_id)
    loaded = None if binding is None else research_state(rig.fake, rig.specimen_id)
    return loaded, binding


def test_first_publication_lands_through_the_production_entry_point(rig):
    # The geography historian makes no GEOLocate lookup here, so this stage
    # covers the abstaining historian: the geography waits on a source and the
    # record is processing_blocked (Stage 2 covers the lookups).
    workflow = compose(rig, geolocate=False)
    parsed = to_plan(workflow, rig)
    assert not RESEARCH_OPERATIONS & set(rig.fake.calls)
    program = research_program_key(parsed.run.id)
    job_id = f"{parsed.run.id}-r3"
    state_scope = DurabilityScope(ORG, COLLECTION, rig.specimen_id, job_id, 1, WORKER, False)

    # Plan tick 1: the connector call that registers the binding is lost.
    def dropped(variables):
        raise ConnectionError("connector call lost")
    rig.fake.fail_before["RegisterCanonicalResearchBindingV2"] = dropped
    with supervised(), pytest.raises(ConnectionError):
        workflow.step(rig.principal, rig.specimen_id)
    document = rig.backend.load(state_scope, program)
    assert len(document.state["jobs"]) == 1 and rig.specimen_id not in rig.fake.bindings
    base_records = [row for row in rig.fake.tables["record_version"].values() if row["runId"] == parsed.run.id]
    assert len(base_records) == 1 and base_records[0]["disposition"] is None
    # Each label line's evidence is on the base record as recorded evidence, so
    # a supported value can link to it (G23).
    label = [row for row in rig.fake.tables["evidence_item"].values() if row["source"] == "label"]
    assert len(label) == len(LABEL_VALUES) == 20 and {row["outcome"] for row in label} == {"recorded"}
    assert {row["runId"] for row in label} == {parsed.run.id}

    # Plan tick 2, a new worker: provisioning replays and registers, then the
    # process dies before the research worker starts.
    restarted = compose(rig, geolocate=False)

    async def crash(*args, **kwargs):
        raise SimulatedCrash
    restarted.native_worker.run_registered = crash
    with supervised(), pytest.raises(SimulatedCrash):
        restarted.step(rig.principal, rig.specimen_id)
    (revision, state), binding = jobs_and_bindings(rig)
    assert list(state["jobs"].values())[0]["identity"]["job_id"] == job_id and len(state["jobs"]) == 1
    assert binding["active"] and binding["job_id"] == job_id and binding["program_key"] == program
    assert binding["current_receipt_id"] is None and binding["base_record_version_id"] == base_records[0]["id"]
    assert state["budget_policy"]["ceiling_micro_usd"] == 500_000 and state["budget_policy"]["live_authorized"]
    assert set(binding["semantic_mapping"]["evidence_sources"]) >= {"gbif", "global_names_verifier",
        "catalogue_of_life"}

    # Plan tick 3, a new worker: provisioning returns at once and research runs
    # all six roles. The taxon publishes, then precise_location, then the
    # parties and collection fields. Neither the geography fields still waiting
    # on a source nor the dates and elevations are offered for publication: the
    # evidence.py date and elevation helpers give a settled value no evidence
    # relation, which the V2 projection requires, so each of those fields keeps
    # its base record value and carries the field reason mandatory_unresolved.
    # The geography fields, with no GEOLocate lookup, keep the record
    # processing_blocked, so the step ends with an operational hold.
    resumed = compose(rig, geolocate=False)
    routing = []

    def observe(variables):
        # The specimen's routing as each publication finds it.
        row = rig.fake.specimens[rig.specimen_id]
        routing.append((row["state"], row["work_available_at"]))
        rig.fake.fail_before["PublishCanonicalResearchV2"] = observe
    rig.fake.fail_before["PublishCanonicalResearchV2"] = observe
    with supervised(), pytest.raises(OperationalBlock, match="native_research_operational_hold"):
        resumed.step(rig.principal, rig.specimen_id)
    rig.fake.fail_before.pop("PublishCanonicalResearchV2")
    assert rig.fake.calls.count("RegisterCanonicalResearchBindingV2") == 2

    # Exactly one job and one binding after every retry.
    (revision, state), binding = jobs_and_bindings(rig)
    assert len(state["jobs"]) == 1 and len(rig.fake.bindings) == 1 and binding["job_id"] == job_id

    # Only terminal checkpoints were offered: no publication was prepared for a
    # field still waiting on a source, or for a date or elevation.
    job = list(state["jobs"].values())[0]
    offered = {event["guard"]["checkpoint_id"] for event in state["outbox"].values()
        if event.get("kind") == "canonical_publication_required"}
    waiting = [field["checkpoint"]["id"] for field in job["fields"].values() if field["work_state"] == "waiting_source"]
    assert waiting and offered and not offered & set(waiting)
    assert {job["fields"][key]["work_state"] for key in DATES_AND_ELEVATIONS} == {"resolved"}
    assert not offered & {job["fields"][key]["checkpoint"]["id"] for key in DATES_AND_ELEVATIONS}

    # The three ready taxonomy sources were fetched once each through the
    # capture broker, offline, and the run's spend is within its allowance.
    assert sorted(url.split("/")[2] for url in rig.source_urls) == [
        "api.checklistbank.org", "api.gbif.org", "verifier.globalnames.org"]
    effects = list(state["effects"].values())
    assert all(effect["status"] == "completed" and effect["execution_class"] == "offline" for effect in effects)
    assert sum(effect["operation_key"].startswith("source_capture_v2:") for effect in effects) == 3
    settled = sum(effect.get("actual_micro_usd") or 0 for effect in effects)
    held = sum(effect["held_micro_usd"] for effect in effects)
    assert held == 0 and 0 < settled <= 500_000
    assert [role for role, _ in rig.model_calls] == ["specimen_taxonomy"] * 4 + [
        "specimen_geography", "specimen_temporal", "specimen_measurement", "specimen_parties",
        "specimen_collection"]

    # Eight publications: the taxon, from the GBIF exact match, precise_location,
    # then the parties and collection fields.
    receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    assert [row["causal_proof"]["changed_field"] for row in receipts] == ["taxon", "precise_location",
        "collectors", "identified_by_irn", "collection_code", "collection_method", "fmnh_ins_number", "habitat"]
    receipt, place, last = receipts[0], receipts[1], receipts[-1]
    assert (receipt["used_canonical_revision"], receipt["resulting_canonical_revision"]) == (3, 4)
    assert (place["used_canonical_revision"], place["resulting_canonical_revision"]) == (4, 5)
    assert binding["current_receipt_id"] == last["id"] and binding["registration_revision"] == 9
    assert binding["current_canonical_revision"] == 11
    published = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert published.version == 11 and published.run.id == parsed.run.id
    taxon = published.run.fields["taxon"]
    assert taxon.state == "supported" and taxon.normalized == GBIF_NAME
    assert taxon.authority_id.startswith(COL_XR + ":")
    # The taxon left the run unfinished and due again (no disposition).
    assert len(routing) == 8 and routing[1][0] == "running" and routing[1][1] is not None
    # From precise_location on, the record carries the geography fields still
    # waiting on a source, which the V2 routing treats as processing_blocked.
    assert published.run.stage == "processing_blocked" and published.run.disposition is None
    waiting_reasons = tuple(f"research_work:{key}:waiting_source" for key in ("city", "country", "county",
        "province_state"))
    assert set(waiting_reasons) <= set(published.run.reasons)
    assert rig.fake.specimens[rig.specimen_id]["state"] == "processing_blocked"
    # Each date and elevation carries its field reason, a human review reason
    # and never an operational one, and keeps its base record value (here the
    # ordinary parse of the synthetic label's explicit "key: value" line).
    progress = last["causal_proof"]["progress_receipt"]
    unresolved = {f"mandatory_unresolved:{key}" for key in DATES_AND_ELEVATIONS}
    assert unresolved <= set(progress["human_reason_codes"]) and unresolved <= set(published.run.reasons)
    assert tuple(progress["operational_reason_codes"]) == waiting_reasons
    assert all(published.run.fields[key] == parsed.run.fields[key] for key in DATES_AND_ELEVATIONS)
    record = rig.fake.tables["record_version"][receipt["native_record_version_id"]]
    assert record["predecessorId"] == base_records[0]["id"] and record["disposition"] is None
    fields = {row["fieldKey"]: row for row in rig.fake.tables["resolved_field"].values()
        if row["recordVersionId"] == record["id"]}
    assert len(fields) == 20 and fields["taxon"]["state"] == "supported"
    candidate = rig.fake.tables["field_candidate"][fields["taxon"]["candidateId"]]
    assert candidate["normalizedValue"] == GBIF_NAME and candidate["derivation"] == "settled"
    gbif = [row for row in rig.fake.tables["evidence_item"].values() if row["source"] == "gbif"]
    assert len(gbif) == 1 and gbif[0]["outcome"] == "success"
    call = [row for row in rig.fake.tables["tool_call"].values() if row["evidenceId"] == gbif[0]["id"]]
    assert len(call) == 1 and call[0]["inputSource"] == "decided_transcript"
    snapshot = rig.fake.snapshots[(rig.specimen_id, 4)]
    assert snapshot["sha256"] == canonical_digest(snapshot["snapshot"]) == receipt["snapshot_sha256"]
    assert not rig.fake.duplicates

    # precise_location: the written value, linked as "supports" to its label
    # evidence row on the base record.
    location = published.run.fields["precise_location"]
    assert location.state == "supported" and location.normalized == LABEL_VALUES["precise_location"]
    place_record = rig.fake.tables["record_version"][place["native_record_version_id"]]
    assert place_record["predecessorId"] == record["id"] and place_record["disposition"] is None
    place_field = next(row for row in rig.fake.tables["resolved_field"].values()
        if row["recordVersionId"] == place_record["id"] and row["fieldKey"] == "precise_location")
    links = [row for row in rig.fake.tables["candidate_evidence"].values()
        if row["candidateId"] == place_field["candidateId"]]
    label_ids = {row["id"] for row in label}
    assert links and {row["relation"] for row in links} == {"supports"}
    assert {row["evidenceId"] for row in links} <= label_ids
    job = list(state["jobs"].values())[0]
    assert job["fields"][str(FieldKey.TAXON)]["work_state"] == "resolved"

    # The next tick finds the run processing_blocked: it does not re-enter
    # research, so nothing is published or paid for twice.
    again = compose(rig, geolocate=False)
    before = len(rig.fake.calls)
    with supervised():
        blocked = again.step(rig.principal, rig.specimen_id)
    assert blocked.version == 11 and blocked.run.stage == "processing_blocked"
    assert not RESEARCH_OPERATIONS & set(rig.fake.calls[before:])
    assert len(rig.fake.receipts) == 8
    assert rig.repository.get(rig.principal.scope, rig.specimen_id).version == 11
    assert len(rig.model_calls) == 9 and len(rig.source_urls) == 3


def test_the_run_reaches_its_final_queue(rig):
    """The historian validates the label's country, state, county and city with
    GEOLocate through the capture broker: four captures, one per field. The
    engine pins every receipt of the geography run on each of its checkpoints,
    and each field publishes with them, citing only its own field's capture.
    One plan tick publishes every terminal field and finalizes the run."""
    workflow = compose(rig)
    parsed = to_plan(workflow, rig)
    with supervised():
        specimen = workflow.step(rig.principal, rig.specimen_id)

    # The four queries send the one recorded glcwrap request, each a completed
    # offline capture effect of its own field.
    url = json.loads((FIXTURES / "sources.json").read_text())["geolocate"]["url"]
    assert len(rig.source_urls) == 7 and rig.source_urls.count(url) == 4
    assert [role for role, _ in rig.model_calls] == ["specimen_taxonomy"] * 4 + ["specimen_geography"] * 2 + [
        "specimen_temporal", "specimen_measurement", "specimen_parties", "specimen_collection"]
    _, state = research_state(rig.fake, rig.specimen_id)
    captures = {key: effect for key, effect in state["effects"].items()
        if effect["operation_key"].startswith("source_capture_v2:")}
    assert len(captures) == 7 and {effect["status"] for effect in captures.values()} == {"completed"}
    assert {effect["execution_class"] for effect in captures.values()} == {"offline"}
    job = list(state["jobs"].values())[0]
    for key in GEOGRAPHY:
        # Each geography checkpoint carries all four fields' captures.
        assert {tuple(captures[effect]["field_keys"]) for effect in job["fields"][key]["checkpoint"]["receipt_ids"]
            if effect in captures} == {(name,) for name in GEOGRAPHY}

    # Twelve publications: the taxon, the geography with precise_location, then
    # the parties and collection fields.
    receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    assert [row["causal_proof"]["changed_field"] for row in receipts] == ["taxon", "city", "country",
        "county", "precise_location", "province_state", "collectors", "identified_by_irn", "collection_code",
        "collection_method", "fmnh_ins_number", "habitat"]
    published = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert published.version == specimen.version == parsed.version + 12
    by_field = {row["causal_proof"]["changed_field"]: row for row in receipts}

    # G39: the matched point is candidate metadata in the tool result and the trace, not a record
    # field. No row of any table the record is written to, and no public field, holds Chicago's
    # point or any coordinate pair; the point stays in the evidence, the GEOLocate evidence
    # excerpts of the published snapshot (the tool result).
    for table, rows in rig.fake.tables.items():
        text = json.dumps(list(rows.values()), sort_keys=True, default=str)
        assert not any(number in text for number in CHICAGO_POINT) and not COORDINATE_PAIR.search(text), table
    public = json.dumps({key: value.model_dump(mode="json") for key, value in published.run.fields.items()},
        sort_keys=True)
    assert not any(number in public for number in CHICAGO_POINT) and not COORDINATE_PAIR.search(public)
    snapshot = rig.fake.snapshots[(rig.specimen_id, published.version)]["snapshot"]
    excerpts = [item["excerpt"] for item in snapshot["run"]["evidence"] if item["source"] == "geolocate"]
    assert len(excerpts) == len(GEOGRAPHY) and all(
        f'"decimal_latitude":{CHICAGO_POINT[0]},"decimal_longitude":{CHICAGO_POINT[1]}' in text for text in excerpts)
    for key in GEOGRAPHY:
        # The label's value with GEOLocate's Chicago match, linked as "supports"
        # to one GEOLocate evidence row: a success from its own field's capture,
        # with one producer call for that field.
        value = published.run.fields[key]
        assert value.state == "supported" and value.normalized == LABEL_VALUES[key] and value.authority_id == CHICAGO
        record = rig.fake.tables["record_version"][by_field[key]["native_record_version_id"]]
        field = next(row for row in rig.fake.tables["resolved_field"].values()
            if row["recordVersionId"] == record["id"] and row["fieldKey"] == key)
        links = [row for row in rig.fake.tables["candidate_evidence"].values()
            if row["candidateId"] == field["candidateId"]]
        assert [row["relation"] for row in links] == ["supports"]
        evidence = rig.fake.tables["evidence_item"][links[0]["evidenceId"]]
        assert (evidence["source"], evidence["outcome"]) == ("geolocate", "success")
        calls = [row for row in rig.fake.tables["tool_call"].values() if row["evidenceId"] == evidence["id"]]
        assert [(row["fieldKeys"], row["outcome"]) for row in calls] == [([key], "success")]

    # The final queue: needs human review on the field reasons of verbatim_dts
    # and the held dates and elevations, with no operational reason.
    assert specimen.run.stage == "finalized" and specimen.run.disposition == "needs_human_review"
    unresolved = {f"mandatory_unresolved:{key}" for key in ("verbatim_dts", *DATES_AND_ELEVATIONS)}
    assert {reason for reason in specimen.run.reasons if reason.startswith("mandatory_unresolved:")} == unresolved
    progress = receipts[-1]["causal_proof"]["progress_receipt"]
    assert unresolved <= set(progress["human_reason_codes"]) and not progress["operational_reason_codes"]
    assert not rig.fake.duplicates


def test_with_the_switch_off_the_worker_keeps_the_ordinary_workflow(rig):
    for environ in ({}, {"SPECIMEN_RESEARCH_HARNESS": "off"}):
        with pytest.raises(ValueError, match="research_harness_switch_off"):
            compose(rig, environ=environ)
        assert compose_registered_native_drain(rig.ordinary, repository=rig.repository,
            environ=environ) is rig.ordinary
    to_plan(rig.ordinary, rig)
    with supervised():
        planned = rig.ordinary.step(rig.principal, rig.specimen_id)
    assert "plan" in planned.run.completed_steps
    assert not RESEARCH_OPERATIONS & set(rig.fake.calls) and not rig.fake.bindings


def test_a_principal_other_than_the_worker_actor_is_refused_before_any_research_write(rig):
    workflow = compose(rig)
    parsed = to_plan(workflow, rig)
    other = worker_principal(user_id=OTHER_OPERATOR)
    with pytest.raises(PermissionError, match="research_worker_actor_required"):
        asyncio.run(workflow.provision(other, parsed))
    with supervised(), pytest.raises(OperationalBlock, match="native_research_admission_or_binding_unavailable"):
        workflow.step(other, rig.specimen_id)
    program = research_program_key(parsed.run.id)
    assert rig.backend.load(DurabilityScope(ORG, COLLECTION, rig.specimen_id, "read", 1, WORKER, False),
        program) is None
    assert not rig.fake.bindings and "RegisterCanonicalResearchBindingV2" not in rig.fake.calls
    assert not rig.model_calls and not rig.source_urls
