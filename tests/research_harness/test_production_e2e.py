"""One synthetic specimen through the production research harness entry point.

The worker composes compose_production_research_workflow over the ordinary
Workflow and steps the specimen under its worker deadline: the ordinary
adjudicate and parse steps, then, at plan, automatic provisioning and the six
research roles. Every layer is the production code except the Data Connect HTTP
session (an in-memory connector, production_e2e_support.FakeDataConnect), the
model (scripted pydantic-ai FunctionModels) and source HTTP (recorded responses).
Label text is the public synthetic fixture.

Stage 1, the first publications, land: the taxon, researched through the three
ready taxonomy sources, and precise_location, settled from its label evidence.
Stage 2, the run reaching its final queue, is expected to fail until the
blockers named on its test are fixed.
"""
from __future__ import annotations

import asyncio
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
    COLLECTION, LABEL_TEXT, LABEL_VALUES, ORG, WORKER, FakeDataConnect, GenerationBlobs,
    fixture_source_transport, research_state, scripted_model_factory, specimen_before_adjudication,
    worker_principal,
)

SWITCH_ON = {"SPECIMEN_RESEARCH_HARNESS": "on"}
OTHER_OPERATOR = "offline-e2e-other-operator"
RESEARCH_OPERATIONS = {"GetCanonicalResearchBindingV2", "RegisterCanonicalResearchBindingV2",
    "GetCanonicalResearchMaterializationInputsV2", "PublishCanonicalResearchV2"}
COL_XR = "7ddf754f-d193-4cc9-b351-99906754a03b"
GBIF_NAME = "Danaus plexippus (Linnaeus, 1758)"


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


def compose(rig, *, environ=SWITCH_ON):
    """The production composer with the three offline seams; a new worker process each call."""
    return compose_production_research_workflow(rig.ordinary, repository=rig.repository, environ=environ,
        actor_uid=WORKER, state_backend=rig.backend, model_factory=scripted_model_factory(rig.model_calls),
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
    workflow = compose(rig)
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
    restarted = compose(rig)

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

    # Plan tick 3, a new worker: provisioning returns at once and research runs.
    # The taxon publishes, then precise_location. The geography fields still
    # waiting on a source are not offered for publication. The next terminal
    # field offered, date_identified, has a settled value with no evidence
    # relation (the evidence.py date helper sets none; the blocker named on the
    # Stage 2 test), which the V2 projection refuses, so the step ends with an
    # operational block.
    resumed = compose(rig)
    routing = []

    def observe(variables):
        # The specimen's routing as each publication finds it.
        row = rig.fake.specimens[rig.specimen_id]
        routing.append((row["state"], row["work_available_at"]))
        rig.fake.fail_before["PublishCanonicalResearchV2"] = observe
    rig.fake.fail_before["PublishCanonicalResearchV2"] = observe
    with supervised(), pytest.raises(OperationalBlock, match="native_publication_requires_reconciliation"):
        resumed.step(rig.principal, rig.specimen_id)
    rig.fake.fail_before.pop("PublishCanonicalResearchV2")
    assert rig.fake.calls.count("RegisterCanonicalResearchBindingV2") == 2

    # Exactly one job and one binding after every retry.
    (revision, state), binding = jobs_and_bindings(rig)
    assert len(state["jobs"]) == 1 and len(rig.fake.bindings) == 1 and binding["job_id"] == job_id

    # Only terminal checkpoints were offered: no publication was prepared for a
    # field still waiting on a source.
    job = list(state["jobs"].values())[0]
    offered = {event["guard"]["checkpoint_id"] for event in state["outbox"].values()
        if event.get("kind") == "canonical_publication_required"}
    waiting = [field["checkpoint"]["id"] for field in job["fields"].values() if field["work_state"] == "waiting_source"]
    assert waiting and offered and not offered & set(waiting)

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
        "specimen_geography", "specimen_temporal"]

    # Two publications: the taxon, from the GBIF exact match, then precise_location.
    assert len(rig.fake.receipts) == 2
    receipt, place = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
    assert (receipt["used_canonical_revision"], receipt["resulting_canonical_revision"]) == (3, 4)
    assert (place["used_canonical_revision"], place["resulting_canonical_revision"]) == (4, 5)
    assert binding["current_receipt_id"] == place["id"] and binding["registration_revision"] == 3
    assert binding["current_canonical_revision"] == 5
    published = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert published.version == 5 and published.run.id == parsed.run.id
    taxon = published.run.fields["taxon"]
    assert taxon.state == "supported" and taxon.normalized == GBIF_NAME
    assert taxon.authority_id.startswith(COL_XR + ":")
    # The taxon left the run unfinished and due again (no disposition).
    assert len(routing) == 2 and routing[1][0] == "running" and routing[1][1] is not None
    # precise_location's record carries the geography fields still waiting on a
    # source, which the V2 routing treats as processing_blocked (the last
    # blocker named on the Stage 2 test).
    assert published.run.stage == "processing_blocked" and published.run.disposition is None
    assert {f"research_work:{key}:waiting_source" for key in ("country", "province_state", "county",
        "city")} <= set(published.run.reasons)
    assert rig.fake.specimens[rig.specimen_id]["state"] == "processing_blocked"
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
    again = compose(rig)
    before = len(rig.fake.calls)
    with supervised():
        blocked = again.step(rig.principal, rig.specimen_id)
    assert blocked.version == 5 and blocked.run.stage == "processing_blocked"
    assert not RESEARCH_OPERATIONS & set(rig.fake.calls[before:])
    assert len(rig.fake.receipts) == 2
    assert rig.repository.get(rig.principal.scope, rig.specimen_id).version == 5
    assert len(rig.model_calls) == 6 and len(rig.source_urls) == 3


@pytest.mark.xfail(strict=True, raises=OperationalBlock, reason=(
    "Blocked in src outside this test's scope (see the Lane H F report): date_identified's "
    "settled value carries no evidence relation, because the evidence.py date and elevation "
    "helpers set none and the validator admits only their exact result "
    "(canonical_lineage_candidate_evidence_unproved); once they do, the F report's offline run "
    "stops after nine publications at 'Bounded research aggregate is full' (persistence.py "
    "MAX_STATE_BYTES); geography stays waiting_source, which the V2 routing treats as "
    "processing_blocked"))
def test_the_run_reaches_its_final_queue(rig):
    workflow = compose(rig)
    to_plan(workflow, rig)
    with supervised():
        for _ in range(8):
            specimen = workflow.step(rig.principal, rig.specimen_id)
            if specimen.run.stage == "finalized":
                break
    assert specimen.run.stage == "finalized"
    assert specimen.run.disposition in {"cleared", "needs_human_review"}


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
