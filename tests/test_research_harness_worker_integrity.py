"""Independent actual SQLite/official SDK worker probes; no provider network."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.persistence import (
    BudgetExceeded, HeldUnknown, ImmutableFileBlobs, ResearchStore,
    SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.runtime import build_research_engine
from specimen_digitization.research_harness.worker import ResearchRetryWorker
from test_research_harness_runtime_pins import actual_offline_engine


def worker_rig(tmp_path, *, provider=None, literal=None):
    original, store, durable, bindings, settings, _ = actual_offline_engine(tmp_path)
    failed = FieldResolution(field_key=FieldKey.TAXON,
        work_state=WorkState.OPERATIONAL_FAILED, value=FieldValue(literal=literal),
        reason="synthetic_initial_operational_failure")
    asyncio.run(original.journal.commit(original.requests[SpecialistRole.TAXONOMY],
        (failed,), receipt_ids=(), model_settings_digest=digest(settings)))
    command = store.admit_retry(durable, "taxon", expected_generation=1,
        expected_field_revision=1, idempotency_key="independent-worker-command",
        execution_class="offline")
    seen = SimpleNamespace(factories=0, models=0, providers=0)
    blobs = ImmutableFileBlobs(tmp_path / "actual-offline-blobs")

    class NoSourceCalls:
        async def query_source(self, *_):
            raise AssertionError("Unexpected source call")
        async def invoke_utility(self, *_):
            raise AssertionError("Unexpected utility call")

    def factory(scope, lease, claimed):
        seen.factories += 1
        assert claimed["id"] == command["id"]
        def model(request):
            seen.models += 1
            assert request.field_keys == (FieldKey.TAXON,)
            assert request.field_revisions == {FieldKey.TAXON:1}
            assert request.retry_command_id == command["id"]
            async def respond(messages, info):
                seen.providers += 1
                if provider is not None:
                    await provider(messages, info)
                output = SpecialistOutput(role=request.role,
                    resolutions=(FieldResolution(field_key=FieldKey.TAXON,
                        work_state=WorkState.WAITING_SOURCE, value=FieldValue(),
                        reason="synthetic_qualified_source_prerequisite"),))
                return ModelResponse([ToolCallPart(info.output_tools[0].name,
                    output.model_dump(mode="json"), tool_call_id="independent-output")],
                    usage=RequestUsage(input_tokens=1, output_tokens=1))
            return FunctionModel(respond)
        return build_research_engine(profile=original.profile, requests=original.requests,
            store=store, scope=scope, lease=lease, blobs=blobs,
            tool_broker=NoSourceCalls(), bindings=bindings, settings=settings,
            base_model_factory=model, actual_cost=lambda _:2)
    worker = ResearchRetryWorker(store=store, engine_factory=factory)
    return SimpleNamespace(store=store, durable=durable, lease=original.journal.lease,
        original=original, command_id=command["id"], seen=seen,
        worker=worker, factory=factory)


def saved(rig):
    return rig.store._read(rig.durable).state["outbox"]["retry/" + rig.command_id]


def assert_one_cost(rig):
    budget = rig.store.budget(rig.durable)
    assert budget["settled_micro_usd"] == 2 and budget["held_micro_usd"] == 0
    assert rig.seen.providers == 1
    assert len(rig.store._read(rig.durable).state["effects"]) == 1


@pytest.mark.parametrize("literal", [None, "Ædes synthetic échantillon"])
def test_actual_worker_replay_acknowledges_without_repeated_model_cost(tmp_path, literal):
    rig = worker_rig(tmp_path, literal=literal)
    outcome = asyncio.run(rig.worker.consume(rig.durable, rig.lease, rig.command_id))
    assert outcome.status == "completed" and outcome.checkpoint_id
    assert saved(rig)["delivered"] and saved(rig)["command"]["result_checkpoint_id"] == outcome.checkpoint_id
    first_factories = rig.seen.factories
    replay = asyncio.run(rig.worker.consume(rig.durable, rig.lease, rig.command_id))
    assert replay == outcome and rig.seen.factories == first_factories == 1
    assert rig.store.job(rig.durable)["fields"]["taxon"]["revision"] == 2
    assert_one_cost(rig)


def test_lost_checkpoint_ack_recovers_native_bound_result(tmp_path, monkeypatch):
    rig = worker_rig(tmp_path)
    checkpoint = rig.store.checkpoint
    def ack_lost(*args, **kwargs):
        result = checkpoint(*args, **kwargs)
        if kwargs.get("retry_command_id"):
            raise RuntimeError("SYNTHETIC_PRIVATE_CHECKPOINT_ACK")
        return result
    monkeypatch.setattr(rig.store, "checkpoint", ack_lost)
    outcome = asyncio.run(rig.worker.consume(rig.durable, rig.lease, rig.command_id))
    assert outcome.status == "completed" and outcome.checkpoint_id
    assert "SYNTHETIC_PRIVATE" not in outcome.model_dump_json()
    assert_one_cost(rig)


@pytest.mark.parametrize("ack_after_commit", [False, True])
def test_restart_replacement_acknowledges_committed_result_without_runtime(tmp_path, monkeypatch, ack_after_commit):
    rig = worker_rig(tmp_path)
    complete = rig.store.complete_retry_command
    def interrupted(*args, **kwargs):
        if ack_after_commit:
            complete(*args, **kwargs)
        raise RuntimeError("SYNTHETIC_PRIVATE_COMPLETION_ACK")
    monkeypatch.setattr(rig.store, "complete_retry_command", interrupted)
    with pytest.raises(RuntimeError):
        asyncio.run(rig.worker.consume(rig.durable, rig.lease, rig.command_id))
    proof = saved(rig)["command"]["result_checkpoint_id"]
    assert proof
    restarted = ResearchStore(SqliteStateBackend(rig.store.backend.path), rig.store.program_key)
    restarted.backend._time = lambda _db:rig.lease.expires_at + 1
    lease = restarted.claim(rig.durable, "independent-replacement-ack", ttl_seconds=120)
    def forbidden(*_):
        pytest.fail("Acknowledgment recovery rebuilt runtime")
    recovered = asyncio.run(ResearchRetryWorker(store=restarted,
        engine_factory=forbidden).consume(rig.durable, lease, rig.command_id))
    assert recovered.status == "completed" and recovered.checkpoint_id == proof
    assert restarted._read(rig.durable).state["outbox"]["retry/" + rig.command_id]["delivered"]
    assert_one_cost(rig)


def test_replacement_after_inflight_send_reuses_capture_without_second_provider_request(tmp_path):
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        async def provider(_messages, _info):
            started.set()
            await release.wait()
        rig = worker_rig_async(tmp_path, provider)
        rig = await rig
        task = asyncio.create_task(rig.worker.consume(rig.durable, rig.lease, rig.command_id))
        await asyncio.wait_for(started.wait(), timeout=3)
        rig.store.backend._time = lambda _db:rig.lease.expires_at + 1
        replacement = rig.store.claim(rig.durable, "inflight-replacement", ttl_seconds=120)
        with pytest.raises(HeldUnknown):
            await rig.worker.consume(rig.durable, replacement, rig.command_id)
        assert rig.seen.factories == 1
        release.set()
        with pytest.raises(StaleWork):
            await asyncio.wait_for(task, timeout=3)
        assert rig.store.job(rig.durable)["fields"]["taxon"]["revision"] == 1
        outcome = await asyncio.wait_for(rig.worker.consume(rig.durable, replacement, rig.command_id), timeout=3)
        assert outcome.status == "completed" and outcome.checkpoint_id
        assert_one_cost(rig)
    asyncio.run(scenario())


async def worker_rig_async(tmp_path, provider=None):
    # Fixture setup calls asyncio.run only in a separate synchronous thread.
    return await asyncio.to_thread(worker_rig, tmp_path, provider=provider)


def test_cancelled_sent_request_retains_hold_and_denies_new_factory(tmp_path):
    async def scenario():
        started = asyncio.Event()
        async def provider(_messages, _info):
            started.set()
            await asyncio.Event().wait()
        rig = await worker_rig_async(tmp_path, provider)
        task = asyncio.create_task(rig.worker.consume(rig.durable, rig.lease, rig.command_id))
        await asyncio.wait_for(started.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert saved(rig)["command"]["status"] == "running" and not saved(rig)["delivered"]
        assert rig.store.budget(rig.durable)["held_micro_usd"] == 10
        assert rig.store.budget(rig.durable)["settled_micro_usd"] == 0
        with pytest.raises(HeldUnknown):
            await rig.worker.consume(rig.durable, rig.lease, rig.command_id)
        assert rig.seen.factories == rig.seen.providers == 1
    asyncio.run(scenario())


def test_same_lease_duplicate_claim_before_send_cannot_block_first_inflight_scientific_result(tmp_path):
    async def scenario():
        both_claimed, started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def provider(_messages, _info):
            started.set()
            await release.wait()
        rig = await worker_rig_async(tmp_path, provider)
        factory_calls = 0
        claimed_tasks = {}
        def interleaved_factory(scope, lease, claimed):
            nonlocal factory_calls
            factory_calls += 1
            order = factory_calls
            claimed_tasks[order] = asyncio.current_task()
            engine = rig.factory(scope, lease, claimed)
            actual_run = engine.run
            async def run(**kwargs):
                if order == 1:
                    await both_claimed.wait()
                else:
                    both_claimed.set()
                    await started.wait()
                return await actual_run(**kwargs)
            engine.run = run
            return engine
        worker = ResearchRetryWorker(store=rig.store, engine_factory=interleaved_factory)
        first = asyncio.create_task(worker.consume(rig.durable, rig.lease, rig.command_id))
        second = asyncio.create_task(worker.consume(rig.durable, rig.lease, rig.command_id))
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            # Both claims happened before sending. The later runtime begins
            # while the first provider call is still in flight, a legitimate
            # duplicate-delivery interleaving for the same current lease.
            await asyncio.wait_for(claimed_tasks[2], timeout=3)
        finally:
            release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second,
            return_exceptions=True), timeout=3)
        native = rig.store.job(rig.durable)["fields"]["taxon"]["checkpoint"]
        assert native["revision"] == 2, (results, saved(rig)["command"]["status"])
        assert native["payload"]["resolution"]["work_state"] == "waiting_source", results
        assert saved(rig)["command"]["status"] == "completed", results
        assert_one_cost(rig)
    asyncio.run(scenario())


@pytest.mark.parametrize("denial", ["revoked", "viewer", "lock", "paused", "halted", "scope", "generation", "lease"])
def test_claim_denials_precede_runtime_and_model_cost(tmp_path, denial):
    rig = worker_rig(tmp_path)
    scope, lease = rig.durable, rig.lease
    if denial == "revoked":
        rig.store.backend.revoke(scope)
    elif denial == "viewer":
        rig.store.backend.grant(scope, role="viewer")
    elif denial in {"lock", "paused", "halted"}:
        def change(state, _now):
            job = state["jobs"][scope.key]
            if denial == "lock":
                job["fields"]["taxon"]["locked"] = True
            elif denial == "paused":
                job["paused"] = True
            else:
                state["halted"] = True
        rig.store._mutate(scope, change)
    elif denial == "scope":
        scope = replace(scope, specimen_id="other-synthetic-specimen")
    elif denial == "generation":
        scope = replace(scope, generation=2)
    else:
        lease = replace(lease, owner="unclaimed-owner")
    with pytest.raises((PermissionError, StaleWork, BudgetExceeded)):
        asyncio.run(rig.worker.consume(scope, lease, rig.command_id))
    assert rig.seen.factories == rig.seen.models == rig.seen.providers == 0
    if denial not in {"revoked", "viewer"}:
        assert rig.store._read(rig.durable).state["effects"] == {}
