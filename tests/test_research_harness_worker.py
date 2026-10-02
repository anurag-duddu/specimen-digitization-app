"""HTTP-to-official-SDK retry completion with durable restart and effect guards."""

import asyncio
import inspect
from types import SimpleNamespace

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
import pytest

from specimen_digitization.model_gateway import HuggingFaceModelGateway
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.accepted_output import read_accepted_checkpoint_proof
from specimen_digitization.research_harness.gateway import ModelGatewayBlocked
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.persistence import (
    CapturedResult, DurableEffectBroker, HeldUnknown, ResearchStore,
    SqlConnectStepStore, SqliteStateBackend, canonical,
)
from specimen_digitization.research_harness.runtime import build_research_engine
from specimen_digitization.research_harness.worker import ResearchRetryWorker
from specimen_digitization.application.domain import FieldValue
from test_research_harness_api import BASE, RETRY, fields, private_error, rig


PRIVATE = "PRIVATE_WORKER_PROVIDER_OR_ENGINE_CANARY"


def queue(rig):
    response = rig.client.post(RETRY, json={"expected_checkpoint_revision":1})
    assert response.status_code == 202, response.text
    assert fields(rig.client.get(BASE + "/thread"))["taxon"]["work_state"] == "retry_scheduled"
    return response.json()["command_id"]


def command(store, scope, command_id):
    return store._read(scope).state["outbox"]["retry/" + command_id]


def response_for(request, info):
    output = SpecialistOutput(role=request.role, resolutions=(FieldResolution(
        field_key=FieldKey.TAXON, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(), reason="qualified_source_prerequisite"),))
    return ModelResponse([ToolCallPart(info.output_tools[0].name,
        output.model_dump(mode="json"), tool_call_id="worker-fixture-output")],
        usage=RequestUsage(input_tokens=2, output_tokens=2))


def runtime_factory(rig, *, store=None, provider=None, model=None, mutate=None, known_cost=True, request_guard=None):
    """All six admitted bindings enter the actual runtime; only retry field runs."""
    store = store or rig.store
    seen = SimpleNamespace(factories=[], models=[], providers=[])

    def factory(scope, lease, claimed):
        seen.factories.append((scope, lease, dict(claimed)))
        assert set(rig.requests) == set(rig.bindings) == set(SpecialistRole)
        assert claimed["status"] == "running" and claimed["field_key"] == "taxon"
        assert claimed["scope"] == scope.identity() and claimed["lease"]["fence"] == lease.fence

        def base(scoped):
            seen.models.append((scoped.role, scoped.field_keys, dict(scoped.field_revisions),
                scoped.retry_command_id))
            assert scoped.role == SpecialistRole.TAXONOMY
            assert scoped.field_keys == (FieldKey.TAXON,)
            assert scoped.field_revisions == {FieldKey.TAXON:1}
            assert scoped.retry_command_id == claimed["id"]
            if model is not None:
                return model

            async def respond(messages, info):
                seen.providers.append(scoped)
                result = provider(messages, info, scoped) if provider else response_for(scoped, info)
                return await result if inspect.isawaitable(result) else result

            return FunctionModel(respond)

        engine = build_research_engine(profile=rig.profile, requests=rig.requests,
            store=store, scope=scope, lease=lease, blobs=rig.blobs, tool_broker=object(),
            bindings=rig.bindings, settings=rig.settings, base_model_factory=base,
            actual_cost=(lambda _:2) if known_cost else None, request_guard=request_guard)
        if mutate:
            mutate(engine)
        return engine

    return factory, seen


def test_http_queue_official_sdk_and_durable_completion_preserve_neighbor_and_cumulative_budget(rig):
    neighbor = canonical(rig.store.job(rig.actor)["fields"]["country"])
    policy = rig.store._read(rig.actor).state["budget_policy"]
    async def prior(*_):
        return CapturedResult({"baseline":"offline existing effect"}, 3)
    asyncio.run(DurableEffectBroker(rig.store, rig.blobs).execute(
        rig.durable, rig.lease, "tool:existing-effect", {}, 10, prior, field_keys=("country",)))
    command_id = queue(rig)
    factory, seen = runtime_factory(rig)
    outcome = asyncio.run(ResearchRetryWorker(store=rig.store, engine_factory=factory).consume(
        rig.durable, rig.lease, command_id))
    assert outcome.status == "completed" and outcome.field_key == FieldKey.TAXON
    assert outcome.checkpoint_id and outcome.blocked_reason is None
    assert len(seen.factories) == len(seen.models) == len(seen.providers) == 1
    assert canonical(rig.store.job(rig.actor)["fields"]["country"]) == neighbor
    document = rig.store._read(rig.actor)
    assert document.state["budget_policy"] == policy
    assert len(document.state["effects"]) == 2
    assert all(effect["status"] == "completed" for effect in document.state["effects"].values())
    assert rig.store.budget(rig.actor)["settled_micro_usd"] == 5
    assert rig.store.budget(rig.actor)["held_micro_usd"] == 0
    saved = command(rig.store, rig.actor, command_id)
    assert saved["delivered"] is True and saved["command"]["status"] == "completed"
    assert saved["command"]["result_checkpoint_id"] == outcome.checkpoint_id
    taxon = fields(rig.client.get(BASE + "/thread"))["taxon"]
    assert taxon["work_state"] == "waiting_source" and taxon["checkpoint"]["revision"] == 2
    assert taxon["checkpoint"]["retry_command_id"] == command_id and taxon["actions"] == []
    native = SqlConnectStepStore(rig.store, rig.durable, rig.blobs, agent_name=str(SpecialistRole.TAXONOMY))
    records = asyncio.run(native.list_runs())
    assert len(records) == 1 and records[0].agent_name == str(SpecialistRole.TAXONOMY)
    assert asyncio.run(native.latest_snapshot(run_id=records[0].run_id)).state == "complete"
    # The actual inert FunctionModel path must also retain forward acceptance,
    # rather than treating a native checkpoint alone as validated output proof.
    accepted = read_accepted_checkpoint_proof(rig.store,rig.durable,rig.blobs,outcome.checkpoint_id)
    assert accepted.acceptance.native_run_id == records[0].run_id
    assert accepted.acceptance.original_request.retry_command_id == command_id
    assert accepted.acceptance.original_request.field_keys == (FieldKey.TAXON,)
    assert accepted.acceptance.resolutions[0].work_state == WorkState.WAITING_SOURCE
    assert accepted.checkpoints[0].retry_command_id == command_id

    restarted = ResearchStore(SqliteStateBackend(rig.backend.path), rig.store.program_key)
    def forbidden(*_):
        pytest.fail("Completed duplicate reconstructed an engine")
    duplicate = asyncio.run(ResearchRetryWorker(store=restarted, engine_factory=forbidden).consume(
        rig.durable, rig.lease, command_id))
    assert duplicate == outcome
    assert len(restarted._read(rig.actor).state["effects"]) == 2
    assert restarted.budget(rig.actor)["settled_micro_usd"] == 5


@pytest.mark.parametrize("ack_loss", ["before_completion", "after_completion"])
def test_restart_reconciles_committed_checkpoint_after_lost_completion_ack_without_engine(rig, monkeypatch, ack_loss):
    command_id = queue(rig)
    neighbor = canonical(rig.store.job(rig.actor)["fields"]["country"])
    factory, seen = runtime_factory(rig)
    complete = rig.store.complete_retry_command
    def interrupted(*args, **kwargs):
        if ack_loss == "after_completion":
            complete(*args, **kwargs)
        raise RuntimeError(PRIVATE)
    monkeypatch.setattr(rig.store, "complete_retry_command", interrupted)
    with pytest.raises(RuntimeError):
        asyncio.run(ResearchRetryWorker(store=rig.store, engine_factory=factory).consume(
            rig.durable, rig.lease, command_id))
    saved = command(rig.store, rig.actor, command_id)["command"]
    assert saved["result_checkpoint_id"] and len(seen.providers) == 1
    assert saved["status"] == ("running" if ack_loss == "before_completion" else "completed")
    restarted = ResearchStore(SqliteStateBackend(rig.backend.path), rig.store.program_key)
    # The server can supply a new fenced lease after a crash. Native result proof
    # remains tied to its original lease; acknowledgment recovery does not pay.
    def expired_and_halted(state, _):
        restarted._job(state, rig.durable)["lease"]["expires_at"] = 0
        state["halted"] = True
    restarted._mutate(rig.durable, expired_and_halted)
    new_lease = restarted.claim(rig.durable, "restart-ack-worker", ttl_seconds=120)
    assert new_lease.fence > rig.lease.fence
    def forbidden(*_):
        pytest.fail("Result checkpoint recovery invoked engine factory")
    recovered = asyncio.run(ResearchRetryWorker(store=restarted, engine_factory=forbidden).consume(
        rig.durable, new_lease, command_id))
    assert recovered.status == "completed" and recovered.checkpoint_id == saved["result_checkpoint_id"]
    assert command(restarted, rig.actor, command_id)["delivered"] is True
    assert canonical(restarted.job(rig.actor)["fields"]["country"]) == neighbor
    assert restarted.budget(rig.actor)["settled_micro_usd"] == 2
    assert restarted.budget(rig.actor)["held_micro_usd"] == 0
    assert len(restarted._read(rig.actor).state["effects"]) == 1


def test_worker_reconciles_checkpoint_committed_before_engine_raised_without_raw_failure(rig):
    command_id = queue(rig)
    def after_commit(engine):
        run = engine.run
        async def interrupted(**kwargs):
            await run(**kwargs)
            raise RuntimeError(PRIVATE)
        engine.run = interrupted
    factory, seen = runtime_factory(rig, mutate=after_commit)
    outcome = asyncio.run(ResearchRetryWorker(store=rig.store, engine_factory=factory).consume(
        rig.durable, rig.lease, command_id))
    assert outcome.status == "completed" and outcome.checkpoint_id
    assert outcome.blocked_reason is None and PRIVATE not in outcome.model_dump_json()
    assert len(seen.providers) == 1 and rig.store.budget(rig.actor)["settled_micro_usd"] == 2
    assert fields(rig.client.get(BASE + "/thread"))["taxon"]["checkpoint"]["revision"] == 2


def test_no_checkpoint_terminal_failure_is_private_and_cannot_advertise_or_acknowledge_retry_again(rig):
    command_id = queue(rig)
    neighbor = canonical(rig.store.job(rig.actor)["fields"]["country"])
    calls = []
    def failure(*_):
        calls.append(1)
        raise RuntimeError(PRIVATE)
    worker = ResearchRetryWorker(store=rig.store, engine_factory=failure)
    outcome = asyncio.run(worker.consume(rig.durable, rig.lease, command_id))
    assert outcome.status == "blocked" and outcome.checkpoint_id is None
    assert outcome.blocked_reason == "retry_worker_failed" and PRIVATE not in outcome.model_dump_json()
    assert command(rig.store, rig.actor, command_id)["delivered"] is True
    thread = rig.client.get(BASE + "/thread")
    assert thread.status_code == 200 and PRIVATE not in thread.text
    taxon = fields(thread)["taxon"]
    assert taxon["checkpoint"]["revision"] == 1 and taxon["work_state"] == "operational_failed"
    assert taxon["blocker_code"] == "research_retry_blocked" and taxon["actions"] == []
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":1}), 403)
    assert asyncio.run(worker.consume(rig.durable, rig.lease, command_id)) == outcome
    assert calls == [1]
    assert canonical(rig.store.job(rig.actor)["fields"]["country"]) == neighbor
    assert rig.store.budget(rig.actor)["settled_micro_usd"] == 0


def test_engine_return_without_durable_checkpoint_cannot_report_success(rig):
    command_id = queue(rig)
    def no_checkpoint(engine):
        async def returned(**kwargs):
            return None
        engine.run = returned
    factory, seen = runtime_factory(rig, mutate=no_checkpoint)
    outcome = asyncio.run(ResearchRetryWorker(store=rig.store, engine_factory=factory).consume(
        rig.durable, rig.lease, command_id))
    assert outcome.status == "blocked" and outcome.checkpoint_id is None
    assert outcome.blocked_reason == "retry_checkpoint_missing"
    assert len(seen.factories) == 1 and seen.models == seen.providers == []
    assert fields(rig.client.get(BASE + "/thread"))["taxon"]["actions"] == []
    assert rig.store.job(rig.actor)["fields"]["taxon"]["revision"] == 1


@pytest.mark.parametrize("change", ["revoked", "viewer"])
def test_completed_duplicate_still_requires_fresh_worker_write_authority(rig, change):
    command_id = queue(rig)
    factory, seen = runtime_factory(rig)
    worker = ResearchRetryWorker(store=rig.store, engine_factory=factory)
    assert asyncio.run(worker.consume(rig.durable, rig.lease, command_id)).status == "completed"
    if change == "revoked":
        rig.backend.revoke(rig.durable)
    else:
        rig.backend.grant(rig.durable, role="viewer")
    with pytest.raises(PermissionError):
        asyncio.run(worker.consume(rig.durable, rig.lease, command_id))
    assert len(seen.factories) == len(seen.providers) == 1
    assert rig.store.budget(rig.actor)["settled_micro_usd"] == 2


def test_actual_live_provider_cannot_use_queued_offline_authority_or_dispatch(rig, monkeypatch):
    command_id = queue(rig)
    live = HuggingFaceModelGateway(token="synthetic-no-live-access").model_for("harness-deepseek")
    calls = []
    async def forbidden(*_):
        calls.append(1)
        pytest.fail("Unqualified actual provider was dispatched")
    monkeypatch.setattr(live, "request", forbidden)
    guard_calls = []
    def inert_liability_refusal(messages, parameters, settings):
        # Explicit local refusal lets the real Harness checkpoint an operational
        # outcome; it supplies no fabricated live price or reservation authority.
        guard_calls.append((messages,parameters,settings))
        raise ModelGatewayBlocked("synthetic_inert_request_liability_refusal")
    factory, seen = runtime_factory(rig, model=live, request_guard=inert_liability_refusal)
    outcome = asyncio.run(ResearchRetryWorker(store=rig.store, engine_factory=factory).consume(
        rig.durable, rig.lease, command_id))
    assert calls == [] and len(seen.models) == 1
    assert len(guard_calls) == 1
    assert outcome.status == "completed"
    taxon = fields(rig.client.get(BASE + "/thread"))["taxon"]
    assert taxon["work_state"] == "operational_failed"
    assert taxon["checkpoint"]["resolution"]["reason"] == "specialist_operational_failure"
    assert rig.store._read(rig.actor).state["effects"] == {}
    assert rig.store.budget(rig.actor)["settled_micro_usd"] == rig.store.budget(rig.actor)["held_micro_usd"] == 0


@pytest.mark.parametrize("unknown", ["provider_exception", "actual_cost_missing"])
def test_unknown_send_or_cost_is_held_after_durable_checkpoint_and_never_reissued(rig, unknown):
    command_id = queue(rig)
    def provider(messages, info, request):
        if unknown == "provider_exception":
            raise RuntimeError(PRIVATE)
        return response_for(request, info)
    factory, seen = runtime_factory(rig, provider=provider, known_cost=unknown != "actual_cost_missing")
    worker = ResearchRetryWorker(store=rig.store, engine_factory=factory)
    outcome = asyncio.run(worker.consume(rig.durable, rig.lease, command_id))
    assert outcome.status == "completed" and len(seen.providers) == 1
    assert rig.store.budget(rig.actor)["held_micro_usd"] == 10
    assert rig.store.budget(rig.actor)["settled_micro_usd"] == 0
    taxon = fields(rig.client.get(BASE + "/thread"))["taxon"]
    assert taxon["checkpoint"]["revision"] == 2 and taxon["actions"] == []
    private_error(rig.client.post(RETRY, json={"expected_checkpoint_revision":2}), 403)
    assert asyncio.run(worker.consume(rig.durable, rig.lease, command_id)) == outcome
    assert len(seen.providers) == 1 and len(rig.store._read(rig.actor).state["effects"]) == 1
    assert PRIVATE not in rig.client.get(BASE + "/thread").text


@pytest.mark.parametrize("stage", ["before_send", "after_send"])
def test_cancellation_preserves_running_work_and_unknown_effect_guard(rig, stage):
    command_id = queue(rig)
    async def cancel():
        started = asyncio.Event()
        async def stuck(messages, info, request):
            started.set()
            await asyncio.Event().wait()
        def before_send(engine):
            async def stopped(**kwargs):
                started.set()
                await asyncio.Event().wait()
            engine.run = stopped
        factory, seen = runtime_factory(rig, provider=stuck if stage == "after_send" else None,
            mutate=before_send if stage == "before_send" else None)
        worker = ResearchRetryWorker(store=rig.store, engine_factory=factory)
        task = asyncio.create_task(worker.consume(rig.durable, rig.lease, command_id))
        await asyncio.wait_for(started.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return seen
    seen = asyncio.run(cancel())
    saved = command(rig.store, rig.actor, command_id)
    assert saved["command"]["status"] == "running" and not saved["delivered"]
    assert not saved["command"].get("result_checkpoint_id")
    assert fields(rig.client.get(BASE + "/thread"))["taxon"]["work_state"] == "researching"
    assert rig.store.budget(rig.actor)["held_micro_usd"] == (10 if stage == "after_send" else 0)
    assert rig.store.budget(rig.actor)["settled_micro_usd"] == 0
    if stage == "after_send":
        def forbidden(*_):
            pytest.fail("Unknown sent cancellation reentered runtime factory")
        with pytest.raises(HeldUnknown):
            asyncio.run(ResearchRetryWorker(store=rig.store, engine_factory=forbidden).consume(
                rig.durable, rig.lease, command_id))
        assert len(seen.providers) == 1
    else:
        recovery, recovered = runtime_factory(rig)
        outcome = asyncio.run(ResearchRetryWorker(store=rig.store, engine_factory=recovery).consume(
            rig.durable, rig.lease, command_id))
        assert outcome.status == "completed" and len(recovered.providers) == 1
        assert rig.store.budget(rig.actor)["settled_micro_usd"] == 2


def test_actual_live_provider_missing_liability_guard_blocks_before_native_run(rig,monkeypatch):
    command_id = queue(rig)
    before_checkpoint = canonical(rig.store.job(rig.actor)["fields"]["taxon"]["checkpoint"])
    before_journal = canonical(rig.store._read(rig.actor).state["journal"])
    live = HuggingFaceModelGateway(token="synthetic-no-live-access").model_for("harness-deepseek")
    calls = []
    async def forbidden(*_):
        calls.append(1)
        pytest.fail("Missing-guard provider was dispatched")
    monkeypatch.setattr(live,"request",forbidden)
    factory,seen = runtime_factory(rig,model=live)
    outcome = asyncio.run(ResearchRetryWorker(store=rig.store,engine_factory=factory).consume(
        rig.durable,rig.lease,command_id))
    assert outcome.status == "blocked" and outcome.blocked_reason == "retry_worker_failed"
    assert outcome.checkpoint_id is None
    assert calls == [] and len(seen.models) == 1 and seen.providers == []
    assert canonical(rig.store.job(rig.actor)["fields"]["taxon"]["checkpoint"]) == before_checkpoint
    assert canonical(rig.store._read(rig.actor).state["journal"]) == before_journal
    assert rig.store._read(rig.actor).state["effects"] == {}
    assert rig.store.budget(rig.actor)["settled_micro_usd"] == rig.store.budget(rig.actor)["held_micro_usd"] == 0
