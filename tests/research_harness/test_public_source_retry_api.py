"""Public same-job continuation with genuine current captured proofs; all effects offline.

Only native SQL HTTP, Firebase verification, worker metadata and provider transport
are explicit local stand-ins. The production app, authority, command reducers,
Harness, source capture and native publication/queue code are exercised together.
"""
import asyncio
import copy
from dataclasses import replace
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import production_e2e_support as support
from specimen_digitization.application.api import create_app
from specimen_digitization.application.derivation_readiness import DeployedDerivationWorker
from specimen_digitization.application.domain import Principal
from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.native_drain import RegisteredNativeDrainWorkflow
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.workflow import SyntheticAdapters, OperationalBlock
from specimen_digitization.research_harness.contracts import digest
from specimen_digitization.research_harness.persistence import ResearchStore, canonical
from specimen_digitization.research_harness.sources import FixtureSourceTransport
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow
from test_native_retry_work_queue import install_retry_sql_fixture, retry_models
from test_unkeyed_label_reading_citation import build_rig, run_research, supervised

REVIEWER = "offline-public-source-reviewer"
JOB = "projects/specimen-digitization/locations/us-east4/jobs/specimen-worker"
SHA = "36593f836427b912f04e72466ecd72b8dd4afe51"  # pragma: allowlist secret (public source commit fixture)


@pytest.fixture(scope="module")
def public_failed(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        import httpx
        def forbid(*args, **kwargs):
            raise AssertionError("the public retry test performs no external HTTP")
        # TestClient's in-memory ASGI transport remains usable.
        patch.setattr(httpx.HTTPTransport, "handle_request", forbid)
        patch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbid)
        import test_unkeyed_label_reading_citation as native_fixture
        original_specimen = native_fixture.specimen_before_adjudication
        def covered(blobs):
            specimen = original_specimen(blobs)
            [region] = specimen.run.regions
            assert (region.x, region.y, region.width, region.height) == (
                0, 0, specimen.asset.width, specimen.asset.height)
            specimen.run.coverage_confirmed = True
            return specimen
        patch.setattr(native_fixture, "specimen_before_adjudication", covered)
        rig, token = build_rig(tmp_path_factory.mktemp("public-source-retry"), patch, (support.LABEL_TEXT,))
        recorded = support.fixture_source_transport(rig.source_urls)
        counter = 0
        async def read(url, policy):
            nonlocal counter
            if policy.id == "geolocate":
                counter += 1
                if counter == 4:
                    rig.source_urls.append(url)
                    return 429, b"synthetic completed source busy"
            return await recorded.read(url, policy)
        rig.transport = FixtureSourceTransport(read)
        rig.models = retry_models(rig)
        try:
            parsed, current, hold, _ = run_research(rig, rig.models, rig.transport)
            assert hold is None and current.run.stage == "processing_blocked"
            factory = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
                environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=support.WORKER,
                state_backend=rig.backend, model_factory=rig.models, source_transport=rig.transport,
                blobs=rig.research_blobs).native_worker.runtime_factory
            binding = asyncio.run(factory.discovery.binding(rig.principal, rig.specimen_id))
            bound = binding.durability_scope(rig.principal)
            store = ResearchStore(rig.backend, binding.program_key)
            document = store._read(bound)
            failed = [key for key, value in binding.job["fields"].items()
                if value["work_state"] == "waiting_source" and store._completed_source_failure(
                    document.state, bound, binding.job, key)]
            assert len(failed) == 1
            field = failed[0]
            reviewer = Principal(user_id=REVIEWER, scope=rig.principal.scope, role="reviewer")
            rig.fake.members[REVIEWER] = [{"organization_id":support.ORG, "collection_id":support.COLLECTION,
                "role":"reviewer", "can_view_sensitive":False}]
            rig.backend.grant(replace(bound, actor_uid=REVIEWER), role="reviewer")
            install_retry_sql_fixture(rig)
            def compare(variables):
                rig.fake.require_member(variables, roles=("reviewer","manager","admin")
                    if variables.get("reviewRequired") else support.OPERATOR_ROLES)
                scope = replace(rig.fake._state_scope(variables["specimenId"]),
                    actor_uid=variables["actorUid"], sensitive=variables["sensitive"])
                prior = rig.backend.load(scope, variables["programKey"])
                state = json.loads(variables["stateJson"])
                assert state == variables["state"]
                assert state["budget_policy"] == prior.state["budget_policy"]
                assert state["contract_version"] == prior.state["contract_version"]
                assert state["program_key"] == variables["programKey"]
                assert not prior.state["halted"] or state["halted"]
                assert set(prior.state["effects"]) <= set(state["effects"])
                until = variables.get("validUntil")
                rig.backend.cas(scope, variables["programKey"], variables["expectedRevision"], state,
                    valid_until=datetime.fromisoformat(until.replace("Z","+00:00")).timestamp() if until else None,
                    review_required=bool(variables.get("reviewRequired")))
                return {"updated":{"revision":variables["expectedRevision"]+1}}
            rig.fake.op_CompareResearchHarnessStateV1 = compare
            metadata = {"name": JOB, "labels":{"source-sha":SHA}, "reconciling":False,
                "terminalCondition":{"state":"CONDITION_SUCCEEDED"},
                "template":{"taskCount":1,"parallelism":1,"template":{"maxRetries":0,
                    "containers":[{"args":["--mode","production","--drain","--max-seconds","3300"],
                        "env":[{"name":"SPECIMEN_RESEARCH_HARNESS","value":"on"}]}]}}}
            starts, reads = [], []
            def get(url, *, timeout):
                reads.append((url, timeout))
                return SimpleNamespace(status_code=200, json=lambda:copy.deepcopy(metadata))
            def start():
                row = rig.fake.specimens[rig.specimen_id]
                starts.append((actor_uid.get(), row["state"], row["revision"]))
                assert row["state"] == "retry_scheduled"
                return SimpleNamespace(status="requested")
            dispatcher = SimpleNamespace(job=JOB, session=lambda:SimpleNamespace(get=get), start=start)
            readiness = DeployedDerivationWorker(SimpleNamespace(worker_job=JOB,
                collection_bindings=((support.COLLECTION,"insects"),)), {"source_sha":SHA}, dispatcher)
            app = create_app(mode="emulator", repository=rig.repository, blobs=rig.repository.graph_blobs,
                adapters=SyntheticAdapters(rig.repository.graph_blobs, support.LABEL_TEXT),
                identity_verifier=lambda bearer, check: REVIEWER if bearer == "reviewer-fixture" else "unknown",
                memberships=rig.repository.memberships, worker_dispatcher=dispatcher,
                research_version="v2", research_derivation_ready=readiness,
                research_capture_blobs=rig.research_blobs)
            base = f"/v1/organizations/{support.ORG}/collections/{support.COLLECTION}/specimens/{rig.specimen_id}/research"
            route = base + f"/jobs/{bound.job_id}/generations/{bound.generation}"
            with TestClient(app) as client:
                yield SimpleNamespace(rig=rig, store=store, bound=bound, binding=binding, factory=factory,
                    field=field, client=client, app=app, route=route, base=base, metadata=metadata,
                    starts=starts, reads=reads, reviewer=reviewer, readiness=readiness, dispatcher=dispatcher,
                    headers={"Authorization":"Bearer reviewer-fixture"}, before=current.model_dump(mode="json"))
        finally:
            actor_uid.reset(token)


def retry(f, revision=None, route=None):
    field = f.store.job(f.bound)["fields"][f.field]
    return f.client.post((route or f.route) + f"/fields/{f.field}/retry", headers=f.headers,
        json={"expected_checkpoint_revision":field["revision"] if revision is None else revision})


def city_thread(f):
    response = f.client.get(f.route + "/thread", headers=f.headers)
    assert response.status_code == 200, response.text
    return next(row for row in response.json()["fields"] if row["field_key"] == f.field)



def test_verified_worker_environment_is_actual_scoped_metadata_and_immutable(public_failed):
    f = public_failed
    current = f.rig.repository.get(f.rig.principal.scope, f.rig.specimen_id)
    environment = f.readiness.research_environment(f.reviewer, current)
    assert dict(environment) == {"SPECIMEN_RESEARCH_HARNESS": "on"}
    with pytest.raises(TypeError):
        environment["SPECIMEN_RESEARCH_HARNESS"] = "off"
    row = f.metadata["template"]["template"]["containers"][0]["env"][0]
    try:
        row["value"] = "off"
        assert f.readiness.research_environment(f.reviewer, current) is None
        assert dict(environment) == {"SPECIMEN_RESEARCH_HARNESS": "on"}
    finally:
        row["value"] = "on"

@pytest.mark.parametrize("barrier", ["worker_off", "worker_old_source", "worker_retry_shape", "active_lease",
    "locked", "paused", "halted", "run_budget", "unknown_send", "unknown_cost", "reserved", "live_hold",
    "old_immutable_job", "unaccepted_source", "revoked_membership"])
def test_public_command_holds_never_schedule_start_or_discard_previous_work(public_failed, barrier):
    f, rig = public_failed, public_failed.rig
    before = copy.deepcopy(f.store._read(f.bound).state)
    snapshots = copy.deepcopy(rig.fake.snapshots)
    native = copy.deepcopy(rig.fake.bindings)
    metadata, members = copy.deepcopy(f.metadata), copy.deepcopy(rig.fake.members)
    starts, sources = len(f.starts), len(rig.source_urls)
    scheduled = rig.fake.calls.count("ScheduleResearchRetryV1")
    def change(state, now):
        job = state["jobs"][f.bound.key]
        target = job["fields"][f.field]
        source = next(effect for effect in state["effects"].values()
            if effect["field_keys"] == [f.field] and effect["operation_key"].startswith("source_capture_v2:"))
        if barrier == "active_lease": job["lease"] = {"owner":"competing","fence":999,"expires_at":now+600}
        elif barrier == "locked": target["locked"] = True
        elif barrier == "paused": job["paused"] = True
        elif barrier == "halted": state["halted"] = True
        elif barrier == "run_budget": state["ordinary_cost_micros"] = state["budget_policy"]["ceiling_micro_usd"]
        elif barrier == "unknown_send": source["status"] = "held_unknown"
        elif barrier == "unknown_cost": source["actual_micro_usd"] = source["receipt"]["actual_micro_usd"] = None
        elif barrier == "reserved": source["status"] = "reserved"
        elif barrier == "live_hold": state["budget_policy"].update(live_authorized=False, hold_reason="imported_unknown")
        elif barrier == "old_immutable_job":
            job["pins"]["serialization_version"] = "pydantic-ai-2.51.0+harness-0.36.0/v1"
            job["binding_digest"] = digest(job["pins"])
            rig.fake.bindings[rig.specimen_id]["runtime_binding_digest"] = job["binding_digest"]
        elif barrier == "unaccepted_source": target["checkpoint"].pop("accepted_output_proof")
    try:
        if barrier.startswith("worker_"):
            task = f.metadata["template"]["template"]
            if barrier == "worker_off": task["containers"][0]["env"][0]["value"] = "off"
            elif barrier == "worker_old_source": f.metadata["labels"]["source-sha"] = "0"*40
            else: task["maxRetries"] = 1
        elif barrier == "revoked_membership": rig.fake.members.pop(REVIEWER)
        else: f.store._mutate(f.bound, change)
        changed = copy.deepcopy(f.store._read(f.bound).state)
        if barrier == "old_immutable_job":
            # Retagging a causally published job also invalidates its native
            # chain. That genuine binding refusal must never grant a retry.
            assert f.client.get(f.route+"/thread", headers=f.headers).status_code == 503
        elif barrier != "revoked_membership":
            assert city_thread(f)["actions"] == []
        response = retry(f)
        assert response.status_code in ({503} if barrier == "old_immutable_job" else {403,409}), response.text
        assert f.store._read(f.bound).state == changed
        assert len(f.starts) == starts and len(rig.source_urls) == sources
        assert rig.fake.calls.count("ScheduleResearchRetryV1") == scheduled and rig.fake.snapshots == snapshots
    finally:
        f.metadata.clear(); f.metadata.update(metadata)
        rig.fake.members = members; rig.fake.bindings = native
        f.store._mutate(f.bound, lambda state, now: (state.clear(), state.update(copy.deepcopy(before))))


def test_public_command_requires_exact_current_checkpoint_and_generation(public_failed):
    f = public_failed
    before = f.store._read(f.bound).state
    assert retry(f, revision=f.store.job(f.bound)["fields"][f.field]["revision"] + 1).status_code == 409
    assert retry(f, route=f.route.replace("/generations/1", "/generations/2")).status_code == 409
    assert f.store._read(f.bound).state == before and f.starts == []




@pytest.mark.parametrize("change", [
    {"stage":"paused"}, {"stage":"cancelled"}, {"stage":"finalized"}, {"stage":"research_in_progress"},
    {"human_approved":True}, {"blocker":"external_outcome_unknown"}, {"disposition":"needs_human_review"},
    {"completed_steps":[]},
])
def test_current_specimen_lifecycle_holds_before_journal_admission(public_failed, change):
    f, rig = public_failed, public_failed.rig
    original = rig.repository.get
    before = f.store._read(f.bound).state
    starts = len(f.starts)
    def changed(scope, specimen_id):
        current = original(scope, specimen_id)
        return current.model_copy(update={"run":current.run.model_copy(update=change)})
    rig.repository.get = changed
    try:
        assert city_thread(f)["actions"] == []
        response = retry(f)
        assert response.status_code in {403,409}, response.text
        assert f.store._read(f.bound).state == before and len(f.starts) == starts
    finally:
        rig.repository.get = original

def test_readiness_lost_after_capability_does_not_reuse_api_store_authority(public_failed):
    f = public_failed
    original = f.readiness.research_environment
    metadata = copy.deepcopy(f.metadata)
    before = f.store._read(f.bound).state
    calls = 0
    def changing(principal, specimen):
        nonlocal calls
        calls += 1
        if calls == 3:
            f.metadata["template"]["template"]["containers"][0]["env"][0]["value"] = "off"
        return original(principal, specimen)
    f.readiness.research_environment = changing
    try:
        response = retry(f)
        assert response.status_code == 403, response.text
        assert calls >= 3 and f.store._read(f.bound).state == before and f.starts == []
    finally:
        f.readiness.research_environment = original
        f.metadata.clear(); f.metadata.update(metadata)


def test_unknown_worker_start_stays_held_without_second_start_or_paid_effect(public_failed):
    f, rig = public_failed, public_failed.rig
    before = copy.deepcopy(f.store._read(f.bound).state)
    row = copy.deepcopy(rig.fake.specimens[rig.specimen_id])
    original_start = f.dispatcher.start
    count, sources = len(f.starts), len(rig.source_urls)
    def unknown():
        original_start()
        raise OSError("synthetic unknown worker start")
    f.dispatcher.start = unknown
    try:
        response = retry(f)
        assert response.status_code in {409,503}, response.text
        uncertain = f.store._read(f.bound).state
        command = next(event["command"] for event in uncertain["outbox"].values()
            if event.get("kind") == "research_field_retry")
        assert command["dispatch_status"] == "unknown" and command["status"] == "queued"
        assert retry(f).status_code in {403,409}
        assert f.store._read(f.bound).state == uncertain
        assert len(f.starts) == count+1 and len(rig.source_urls) == sources
        assert uncertain["effects"] == before["effects"] and uncertain["budget_policy"] == before["budget_policy"]
        models = len(rig.model_calls)
        workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
            environ={"SPECIMEN_RESEARCH_HARNESS":"on"}, actor_uid=support.WORKER,
            state_backend=rig.backend, model_factory=rig.models, source_transport=rig.transport, blobs=rig.research_blobs)
        drain = DrainWorker(rig.repository, RegisteredNativeDrainWorkflow(workflow), support.WORKER,
            lambda user: [], execution_id="offline-unknown-start-hold")
        with supervised(), pytest.raises(OperationalBlock):
            drain._step_until_stopped(rig.principal, SimpleNamespace(hold=lambda *args:None), rig.specimen_id, None)
        assert len(rig.model_calls) == models and len(rig.source_urls) == sources
        assert f.store._read(f.bound).state == uncertain
        assert rig.repository.get(rig.principal.scope, rig.specimen_id).model_dump(mode="json") == f.before
    finally:
        f.dispatcher.start = original_start
        f.starts[count:] = []
        rig.fake.specimens[rig.specimen_id] = row
        f.store._mutate(f.bound, lambda state, now: (state.clear(), state.update(copy.deepcopy(before))))

def test_public_same_job_retry_captures_once_publishes_and_retires_due_work(public_failed):
    f, rig = public_failed, public_failed.rig
    before = f.store._read(f.bound).state
    prior = copy.deepcopy(before)
    job = before["jobs"][f.bound.key]
    original_cp = copy.deepcopy(job["fields"][f.field]["checkpoint"])
    siblings = {key:copy.deepcopy(value) for key,value in job["fields"].items() if key != f.field}
    policy = [key for key,value in siblings.items() if value["work_state"] == "waiting_policy"]
    assert "verbatim_dts" in policy
    assert city_thread(f)["actions"] == ["retry_field"]
    response = retry(f)
    assert response.status_code == 202, response.text
    command_id = response.json()["command_id"]
    assert retry(f).json() == response.json() and len(f.starts) == 1
    admitted = f.store._read(f.bound).state
    command = admitted["outbox"]["retry/" + command_id]["command"]
    assert command["scope"] == f.bound.identity() and command["execution_class"] == "live"
    assert command["created_by"] == REVIEWER and command["checkpoint_digest"] == digest(original_cp)
    assert command["dispatch_status"] == "requested" and command["status"] == "queued"
    assert admitted["jobs"][f.bound.key]["generation"] == f.bound.generation
    assert rig.repository.get(rig.principal.scope, rig.specimen_id).model_dump(mode="json") == f.before
    assert f.starts == [(REVIEWER,"retry_scheduled",f.before["version"])]
    source_count, liability = len(rig.source_urls), f.store.budget(f.bound)["settled_micro_usd"]
    workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS":"on"}, actor_uid=support.WORKER,
        state_backend=rig.backend, model_factory=rig.models, source_transport=rig.transport, blobs=rig.research_blobs)
    drain = DrainWorker(rig.repository, RegisteredNativeDrainWorkflow(workflow), support.WORKER,
        lambda user: [], execution_id="offline-public-retry")
    with supervised():
        result, progressed = drain._step_until_stopped(rig.principal, SimpleNamespace(hold=lambda *args:None), rig.specimen_id, None)
    assert progressed and result.stage == "finalized" and result.disposition == "needs_human_review"
    after = f.store._read(f.bound).state
    current = rig.repository.get(rig.principal.scope, rig.specimen_id)
    current_job = after["jobs"][f.bound.key]
    assert len(after["jobs"]) == 1 and current_job["generation"] == f.bound.generation
    assert {key:value for key,value in current_job["fields"].items() if key != f.field} == siblings
    assert original_cp in current_job["checkpoints"] and current_job["fields"][f.field]["revision"] == original_cp["revision"]+1
    assert all(after["effects"][key] == value for key,value in prior["effects"].items())
    assert len(rig.source_urls) == source_count+1 and f.store.budget(f.bound)["settled_micro_usd"] > liability
    assert {effect["execution_class"] for effect in after["effects"].values()} == {"offline"}
    assert after["outbox"]["retry/"+command_id]["command"]["status"] == "completed"
    assert after["outbox"]["retry/"+command_id]["delivered"] is True
    assert current.run.id == f.before["run"]["id"] and current.version == f.before["version"]+1
    assert rig.fake.specimens[rig.specimen_id]["state"] == "completed"
    assert rig.fake.specimens[rig.specimen_id]["work_available_at"] is None
    binding = asyncio.run(f.factory.discovery.binding(rig.principal, rig.specimen_id))
    progress = binding.native.causal_chain[-1].progress_receipt
    assert progress.field_work_digest == digest(current_job["fields"])
    assert progress.wire_status == "completed" and progress.disposition == "needs_human_review"
    final = f.client.get(f.route+"/thread", headers=f.headers)
    assert final.status_code == 200, final.text
    assert next(row for row in final.json()["fields"] if row["field_key"] == f.field)["work_state"] == "resolved"
