"""One synthetic specimen through the production research harness entry point.

The worker composes compose_production_research_workflow over the ordinary
Workflow and steps the specimen under its worker deadline: the ordinary
adjudicate and parse steps, then, at plan, automatic provisioning and the six
research roles. Every layer is the production code except the Data Connect HTTP
session (an in-memory connector, production_e2e_support.FakeDataConnect), the
model (scripted pydantic-ai FunctionModels) and source HTTP (recorded responses).
Label text is the public synthetic fixture.

Stage 1, the first publication, lands: the taxon, researched through the three
ready taxonomy sources. Stage 2, the run reaching its final queue, is expected to
fail until the blockers named on its test are fixed.
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
    COLLECTION, LABEL_TEXT, ORG, WORKER, FakeDataConnect, GenerationBlobs, fixture_source_transport,
    research_state, scripted_model_factory, specimen_before_adjudication,
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
    # The taxon publishes. The geography fields still waiting on a source are
    # not offered for publication; the next terminal field offered,
    # precise_location, links evidence that has no evidence_item row, which the
    # connector refuses (the blocker named on the Stage 2 test), so the step
    # ends with an operational block.
    resumed = compose(rig)
    with supervised(), pytest.raises(OperationalBlock, match="native_publication_requires_reconciliation"):
        resumed.step(rig.principal, rig.specimen_id)
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
    assert [role for role, _ in rig.model_calls].count("specimen_taxonomy") == 4

    # One publication: the taxon, from the GBIF exact match.
    assert len(rig.fake.receipts) == 1
    receipt = next(iter(rig.fake.receipts.values()))
    assert (receipt["used_canonical_revision"], receipt["resulting_canonical_revision"]) == (3, 4)
    assert binding["current_receipt_id"] == receipt["id"] and binding["registration_revision"] == 2
    assert binding["current_canonical_revision"] == 4
    published = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert published.version == 4 and published.run.id == parsed.run.id
    taxon = published.run.fields["taxon"]
    assert taxon.state == "supported" and taxon.normalized == GBIF_NAME
    assert taxon.authority_id.startswith(COL_XR + ":")
    assert published.run.stage == "research_in_progress" and published.run.disposition is None
    assert rig.fake.specimens[rig.specimen_id]["state"] == "running"
    assert rig.fake.specimens[rig.specimen_id]["work_available_at"] is not None
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
    job = list(state["jobs"].values())[0]
    assert job["fields"][str(FieldKey.TAXON)]["work_state"] == "resolved"

    # The next tick re-enters research at plan (the run is still due). It
    # replays the retained taxon receipt first; the blocked worker kept its
    # lease (custody needs reconciliation), so the open is refused and nothing
    # is published or paid for twice.
    again = compose(rig)
    with supervised(), pytest.raises(OperationalBlock, match="native_research_admission_or_binding_unavailable"):
        again.step(rig.principal, rig.specimen_id)
    assert len(rig.fake.receipts) == 1
    assert rig.repository.get(rig.principal.scope, rig.specimen_id).version == 4
    assert [role for role, _ in rig.model_calls].count("specimen_taxonomy") == 4
    assert len(rig.source_urls) == 3


@pytest.mark.xfail(strict=True, raises=OperationalBlock, reason=(
    "Blocked in src outside this test's scope (see the Lane H D report): settled label values "
    "cannot carry a publishable evidence relation (evidence.py helpers, and canonical literal "
    "evidence has no evidence_item row); geography stays waiting_source, which the V2 routing "
    "treats as processing_blocked"))
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
