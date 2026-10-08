"""Offline supported scheduling and native retry consumption, with real science."""
import asyncio
import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.native_drain import RegisteredNativeDrainWorkflow
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.storage import digest as snapshot_digest
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import FieldKey, digest
from specimen_digitization.research_harness.discovery_v2 import CanonicalReadBindingV2
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.evidence import validate_resolution
from specimen_digitization.research_harness.persistence import (
    BudgetExceeded, HeldUnknown, ResearchStore, StaleWork, canonical,
)
from specimen_digitization.research_harness.retry_work_queue import (
    queued_retry_command, schedule_research_retry,
)
from specimen_digitization.research_harness.sources import FixtureSourceTransport
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow
from test_unkeyed_label_reading_citation import build_rig, run_research, supervised


def install_retry_sql_fixture(rig):
    """Explicit offline native operation stand-ins; never an SQL compile claim."""
    fake = rig.fake

    def clock_read(variables):
        fake.require_member(variables)
        document = rig.backend.load(fake._state_scope(variables["specimenId"]), variables["programKey"])
        return {"read": {"researchHarnessState": {"revision": document.revision,
            "state": document.state, "stateJson": canonical(document.state).decode(),
            "observedAt": datetime.fromtimestamp(document.server_time, timezone.utc).isoformat()}}}

    def metadata(variables, *, scheduled):
        fake.require_member(variables)
        row = fake.specimens[variables["specimenId"]]
        native = fake.bindings[variables["specimenId"]]
        document = rig.backend.load(fake._state_scope(variables["specimenId"]), variables["programKey"])
        command = document.state["outbox"]["retry/" + variables["commandId"]]["command"]
        assert row["revision"] == native["current_canonical_revision"] == variables["recordRevision"]
        assert row["active_run_id"] == native["canonical_run_id"] == variables["canonicalRunId"]
        assert native["current_snapshot_sha256"] == variables["snapshotSha256"]
        assert native["job_key"] == variables["jobKey"] and native["generation"] == variables["generation"]
        assert document.revision == variables["stateRevision"]
        assert command["scope"]["generation"] == native["generation"]
        assert command["scope"]["job_id"] == native["job_id"]
        assert command["status"] == ("queued" if scheduled else "completed")
        row["state"] = "retry_scheduled" if scheduled else "completed"
        row["work_available_at"] = row.get("work_available_at") or support.iso_now() if scheduled else None
        return {"scheduled" if scheduled else "finished": 1, "read": {"specimen": {
            "revision": row["revision"], "activeRunId": row["active_run_id"],
            "state": row["state"], "workAvailableAt": row["work_available_at"]}}}

    def due(variables):
        fake.require_member(variables)
        rows = [(ident, row) for ident, row in fake.specimens.items()
            if row["state"] in {"pending", "running", "retry_scheduled"}
            and row["work_available_at"] is not None and not row["sensitive"]]
        return {"items": [{"id": ident, "revision": row["revision"], "state": row["state"],
            "workAvailableAt": row["work_available_at"], "createdAt": support.iso_now()}
            for ident, row in rows[:variables["limit"]]]}

    fake.op_ReadResearchHarnessStateV1 = clock_read
    fake.op_ScheduleResearchRetryV1 = lambda variables: metadata(variables, scheduled=True)
    fake.op_FinishResearchRetryV1 = lambda variables: metadata(variables, scheduled=False)
    def park(variables):
        response = metadata(variables, scheduled=False)
        fake.specimens[variables["specimenId"]]["state"] = "processing_blocked"
        response["read"]["specimen"]["state"] = "processing_blocked"
        return {"parked": response["finished"], "read": response["read"]}
    fake.op_ParkResearchRetryV1 = park
    fake.op_ListDueWorkV2 = due


def retry_models(rig):
    ordinary = support.scripted_model_factory(rig.model_calls)

    def models(request, binding):
        if request.retry_command_id is None:
            return ordinary(request, binding)
        [field] = request.field_keys
        def respond(messages, info):
            results, attempted = support._results(messages)
            rig.model_calls.append((str(request.role), "retry"))
            if not attempted:
                query = support._geolocate_queries(request)[field]
                return ModelResponse([ToolCallPart("lookup_source", {"query": {
                    "source_id": "geolocate", "field_key": str(field), "query_text": query}},
                    tool_call_id="retry-known-source")], usage=support.USAGE)
            proposal = support._proposals(request, results)[field]
            proposal = proposal or support._waiting_source(field)
            output = SpecialistOutput(role=request.role,
                resolutions=(validate_resolution(request, proposal, tuple(results)),))
            return ModelResponse([ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="retry-output")], usage=support.USAGE)
        return FunctionModel(respond)
    return models


@pytest.fixture(scope="module", params=[False, True], ids=["retry_success", "known_failure_again"])
def failed_native(tmp_path_factory, request):
    with pytest.MonkeyPatch.context() as patch:
        def forbid(*args, **kwargs):
            raise AssertionError("the native retry fixture performs no public HTTP")
        import httpx
        patch.setattr(httpx.Client, "send", forbid)
        patch.setattr(httpx.AsyncClient, "send", forbid)
        import test_unkeyed_label_reading_citation as native_fixture
        original = native_fixture.specimen_before_adjudication
        def covered(blobs):
            specimen = original(blobs)
            [region] = specimen.run.regions
            assert (region.x, region.y, region.width, region.height) == (
                0, 0, specimen.asset.width, specimen.asset.height)
            specimen.run.coverage_confirmed = True
            return specimen
        patch.setattr(native_fixture, "specimen_before_adjudication", covered)
        rig, token = build_rig(tmp_path_factory.mktemp("native-retry"), patch, (support.LABEL_TEXT,))
        recorded = support.fixture_source_transport(rig.source_urls)
        count = 0
        async def read(url, policy):
            nonlocal count
            if policy.id == "geolocate":
                count += 1
                if count == 4 or request.param and count > 4:
                    rig.source_urls.append(url)
                    return 429, b"synthetic completed source busy"
            return await recorded.read(url, policy)
        rig.transport = FixtureSourceTransport(read)
        rig.models = retry_models(rig)
        import specimen_digitization.research_harness.retry_work_queue as queue
        original_park = queue.park_research_retry
        rig.park_errors = []
        def observed_park(*args, **kwargs):
            try:
                return original_park(*args, **kwargs)
            except Exception as error:
                rig.park_errors.append(str(error))
                raise
        patch.setattr(queue, "park_research_retry", observed_park)
        try:
            parsed, current, hold, published = run_research(rig, rig.models, rig.transport)
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
            command = store.admit_retry(bound, field, expected_generation=bound.generation,
                expected_field_revision=binding.job["fields"][field]["revision"],
                idempotency_key="native-known-source", execution_class="offline")
            # The transport is an explicit fixture; this API-scheduling-only pin
            # selects the live contract without making any network/model send.
            def live_command(state, now):
                state["outbox"]["retry/" + command["id"]]["command"]["execution_class"] = "live"
            store._mutate(bound, live_command)
            binding = asyncio.run(factory.discovery.binding(rig.principal, rig.specimen_id))
            install_retry_sql_fixture(rig)
            yield SimpleNamespace(rig=rig, factory=factory, binding=binding, bound=bound,
                store=store, field=field, command_id=command["id"], parsed=parsed,
                before=current.model_dump(mode="json"), source_effects=copy.deepcopy(document.state["effects"]), repeat_failure=request.param)
        finally:
            actor_uid.reset(token)


def test_native_schedule_only_changes_due_metadata_and_replays_exactly(failed_native):
    f, rig = failed_native, failed_native.rig
    before = copy.deepcopy(rig.fake.snapshots)
    jobs = f.store._read(f.bound).state["jobs"]
    receipt = schedule_research_retry(rig.repository, rig.principal, f.binding, f.command_id)
    assert receipt["status"] == "scheduled"
    assert schedule_research_retry(rig.repository, rig.principal, f.binding, f.command_id) == receipt
    assert rig.repository.get(rig.principal.scope, rig.specimen_id).model_dump(mode="json") == f.before
    assert rig.fake.snapshots == before and f.store._read(f.bound).state["jobs"] == jobs
    due = rig.repository.oldest_due(rig.principal.scope, support.iso_now())
    assert len(due) == 1 and due[0].specimen_id == rig.specimen_id and due[0].state == "retry_scheduled"


@pytest.mark.parametrize("barrier", ["active_lease", "locked", "paused", "halted", "budget", "unknown_send",
    "unknown_cost", "reserved", "stale_field", "stale_generation", "unproved_source", "revoked"])
def test_scheduling_rechecks_fresh_custody_and_never_dispatches_or_saves(failed_native, barrier):
    f, rig = failed_native, failed_native.rig
    before = copy.deepcopy(f.store._read(f.bound).state)
    saved = copy.deepcopy(rig.fake.snapshots)
    members = copy.deepcopy(rig.fake.members)
    calls = rig.fake.calls.count("ScheduleResearchRetryV1")
    def change(state, now):
        job = state["jobs"][f.bound.key]
        field = job["fields"][f.field]
        source = next(value for value in state["effects"].values()
            if value["field_keys"] == [f.field] and value["operation_key"].startswith("source_capture_v2:"))
        if barrier == "active_lease": job["lease"] = {"owner": "competing", "fence": 999, "expires_at": now + 600}
        elif barrier == "locked": field["locked"] = True
        elif barrier == "paused": job["paused"] = True
        elif barrier == "halted": state["halted"] = True
        elif barrier == "budget": state["ordinary_cost_micros"] = state["budget_policy"]["ceiling_micro_usd"]
        elif barrier == "unknown_send": source["status"] = "held_unknown"
        elif barrier == "unknown_cost": source["actual_micro_usd"] = source["receipt"]["actual_micro_usd"] = None
        elif barrier == "reserved": source["status"] = "reserved"
        elif barrier == "stale_field": field["revision"] += 1
        elif barrier == "stale_generation": job["generation"] += 1
        elif barrier == "unproved_source": field["checkpoint"]["accepted_output_proof"] = None
    try:
        f.store._mutate(f.bound, change)
        if barrier == "revoked": rig.fake.members.clear()
        with pytest.raises((PermissionError, StaleWork, HeldUnknown, BudgetExceeded, ValueError, OperationalBlock, PublicationUnavailable)):
            binding = asyncio.run(f.factory.discovery.binding(rig.principal, rig.specimen_id))
            schedule_research_retry(rig.repository, rig.principal, binding, f.command_id)
        assert rig.fake.calls.count("ScheduleResearchRetryV1") == calls
        assert rig.fake.snapshots == saved
    finally:
        rig.fake.members = members
        f.store._mutate(f.bound, lambda state, now: (state.clear(), state.update(copy.deepcopy(before))))


@pytest.mark.parametrize("dispatch", ["unknown", "sending", None])
def test_due_live_retry_without_known_start_never_sends_or_administratively_saves(failed_native, dispatch, monkeypatch):
    import specimen_digitization.research_harness.retry_work_queue as queue
    monkeypatch.setattr(queue, "START_RECEIPT_ATTEMPTS", 2)
    monkeypatch.setattr(queue, "START_RECEIPT_INTERVAL_SECONDS", 0)
    f, rig = failed_native, failed_native.rig
    before = copy.deepcopy(f.store._read(f.bound).state)
    def change(state, now):
        command = state["outbox"]["retry/" + f.command_id]["command"]
        command["execution_class"] = "live"
        if dispatch is None:
            command.pop("dispatch_status", None)
        else:
            command["dispatch_status"] = dispatch
    f.store._mutate(f.bound, change)
    held = copy.deepcopy(f.store._read(f.bound).state)
    snapshots = copy.deepcopy(rig.fake.snapshots)
    counts = (len(rig.source_urls), len(rig.model_calls))
    workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=support.WORKER,
        state_backend=rig.backend, model_factory=rig.models, source_transport=rig.transport, blobs=rig.research_blobs)
    drain = DrainWorker(rig.repository, RegisteredNativeDrainWorkflow(workflow), support.WORKER,
        lambda user: [], execution_id="offline-unknown-start")
    try:
        with supervised(), pytest.raises(OperationalBlock, match="^research_retry_requires_reconciliation$"):
            drain._step_until_stopped(rig.principal, SimpleNamespace(hold=lambda *args: None), rig.specimen_id, None)
        assert f.store._read(f.bound).state == held
        assert rig.fake.snapshots == snapshots and (len(rig.source_urls), len(rig.model_calls)) == counts
    finally:
        f.store._mutate(f.bound, lambda state, now: (state.clear(), state.update(copy.deepcopy(before))))


def test_supported_native_workflow_consumes_known_retry_and_publishes_current_whole20(failed_native):
    f, rig = failed_native, failed_native.rig
    schedule_research_retry(rig.repository, rig.principal, f.binding, f.command_id)
    # Restore the explicit offline execution class before the real local worker
    # classifies its injected FunctionModel/source fixture.
    f.store._mutate(f.bound, lambda state, now: state["outbox"]["retry/" + f.command_id]["command"].update(execution_class="offline"))
    before = f.store._read(f.bound).state
    siblings = {key: copy.deepcopy(value) for key, value in before["jobs"][f.bound.key]["fields"].items() if key != f.field}
    liability = f.store.budget(f.bound)["settled_micro_usd"]
    source_count = len(rig.source_urls)
    workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=support.WORKER,
        state_backend=rig.backend, model_factory=rig.models, source_transport=rig.transport, blobs=rig.research_blobs)
    drain = DrainWorker(rig.repository, RegisteredNativeDrainWorkflow(workflow), support.WORKER,
        lambda user: [], execution_id="offline-known-source")
    try:
        with supervised():
            result, progressed = drain._step_until_stopped(rig.principal, SimpleNamespace(hold=lambda *args: None), rig.specimen_id, None)
    except OperationalBlock as error:
        raise AssertionError(f"native retry bridge: {rig.park_errors}") from error
    assert progressed
    if f.repeat_failure:
        assert result.stage == "processing_blocked" and result.disposition is None
    else:
        assert result.stage == "finalized" and result.disposition == "needs_human_review"
    after = f.store._read(f.bound).state
    job = after["jobs"][f.bound.key]
    assert job["generation"] == f.bound.generation and len(after["jobs"]) == 1
    assert {key: value for key, value in job["fields"].items() if key != f.field} == siblings
    assert all(after["effects"][key] == value for key, value in f.source_effects.items())
    assert len(rig.source_urls) == source_count + 1 and f.store.budget(f.bound)["settled_micro_usd"] > liability
    assert after["outbox"]["retry/" + f.command_id]["delivered"] is True
    assert after["outbox"]["retry/" + f.command_id]["command"]["status"] == "completed"
    current = rig.repository.get(rig.principal.scope, rig.specimen_id)
    binding = asyncio.run(f.factory.discovery.binding(rig.principal, rig.specimen_id))
    progress = binding.native.causal_chain[-1].progress_receipt
    from specimen_digitization.research_harness.native_worker import _current_progress_matches_job
    if f.repeat_failure:
        assert binding.canonical.record_revision == current.version == f.before["version"]
        assert progress.wire_status == "processing_blocked"
        assert _current_progress_matches_job(binding.native, f.bound, job) is False
        assert job["fields"][f.field]["revision"] == 2
        assert job["fields"][f.field]["work_state"] == "waiting_source"
        assert rig.fake.calls.count("ParkResearchRetryV1") == 1
        assert rig.fake.calls.count("FinishResearchRetryV1") == 0
    else:
        assert binding.canonical.record_revision == current.version == f.before["version"] + 1
        assert len(progress.canonical_field_work) == len(progress.research_field_work) == 20
        assert progress.wire_status == "completed" and progress.operational_reason_codes == ()
        assert progress.human_reason_codes == ("mandatory_unresolved:verbatim_dts",)
        assert _current_progress_matches_job(binding.native, f.bound, job)
        assert rig.fake.calls.count("FinishResearchRetryV1") == 1
        assert rig.fake.calls.count("ParkResearchRetryV1") == 0
    assert rig.repository.oldest_due(rig.principal.scope, support.iso_now()) == []
    counts = {name: rig.fake.calls.count(name) for name in ("FinishResearchRetryV1", "ParkResearchRetryV1")}
    assert workflow.step(rig.principal, rig.specimen_id) == current
    assert {name: rig.fake.calls.count(name) for name in counts} == counts
    assert not any(item.action == "lane_block" for item in current.audit)


def test_known_whole_output_failure_parks_bare_failure_without_scientific_value(failed_native):
    f, rig = failed_native, failed_native.rig
    if not f.repeat_failure:
        pytest.skip("the second bounded retry starts from the retained completed source failure")
    binding = asyncio.run(f.factory.discovery.binding(rig.principal, rig.specimen_id))
    command = f.store.admit_retry(f.bound, f.field, expected_generation=f.bound.generation,
        expected_field_revision=binding.job["fields"][f.field]["revision"],
        idempotency_key="known-output-failure", execution_class="offline")
    f.store._mutate(f.bound, lambda state, now: state["outbox"]["retry/" + command["id"]]["command"].update(execution_class="live", dispatch_status="requested"))
    binding = asyncio.run(f.factory.discovery.binding(rig.principal, rig.specimen_id))
    schedule_research_retry(rig.repository, rig.principal, binding, command["id"])
    def invalid_output(request, model_binding):
        def respond(messages, info):
            output = SpecialistOutput(role=request.role, resolutions=(support._waiting_source(FieldKey.TAXON),))
            return ModelResponse([ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="wrong-field-output")], usage=support.USAGE)
        return FunctionModel(respond)
    workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=support.WORKER,
        state_backend=rig.backend, model_factory=invalid_output, source_transport=rig.transport, blobs=rig.research_blobs)
    before = rig.repository.get(rig.principal.scope, rig.specimen_id)
    try:
        with supervised():
            current = workflow.step(rig.principal, rig.specimen_id)
    except OperationalBlock as error:
        state = f.store._read(f.bound).state
        command_state = state["outbox"]["retry/" + command["id"]]["command"]
        job_state = state["jobs"][f.bound.key]
        raise AssertionError({"parking_errors": rig.park_errors, "command_status": command_state["status"],
            "work_state": job_state["fields"][f.field]["work_state"], "lease": job_state["lease"] is not None,
            "effects": [(value["status"], value["actual_micro_usd"]) for value in state["effects"].values()]}) from error
    assert current == before and current.run.stage == "processing_blocked"
    state = f.store._read(f.bound).state
    job = state["jobs"][f.bound.key]
    checkpoint = job["fields"][f.field]["checkpoint"]
    assert checkpoint["payload"]["resolution"]["work_state"] == "operational_failed"
    assert checkpoint.get("accepted_output_proof") is None
    assert checkpoint["payload"]["resolution"]["value"]["state"] == "unresolved"
    assert all(effect["status"] == "completed" and effect["actual_micro_usd"] is not None
        for effect in state["effects"].values())
    assert state["outbox"]["retry/" + command["id"]]["command"]["status"] == "completed"
    assert rig.fake.calls.count("ParkResearchRetryV1") == 2
    assert rig.repository.oldest_due(rig.principal.scope, support.iso_now()) == []
    assert workflow.completed_side_work(current)
