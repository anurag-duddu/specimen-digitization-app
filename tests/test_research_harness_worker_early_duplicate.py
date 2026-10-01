"""Additional early duplicate race, preserving the original 15/16 probes."""
import asyncio

from specimen_digitization.research_harness.worker import ResearchRetryWorker
from test_research_harness_worker_integrity import assert_one_cost, saved, worker_rig_async


def test_duplicate_after_both_runtime_guards_preserves_first_inflight_result(tmp_path):
    async def scenario():
        both_ready, started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def provider(_messages, _info):
            started.set()
            await release.wait()
        rig = await worker_rig_async(tmp_path, provider)
        factory_count = 0
        contenders = {}
        def interleaved_factory(scope, lease, claimed):
            nonlocal factory_count
            factory_count += 1
            order = factory_count
            contenders[order] = asyncio.current_task()
            engine = rig.factory(scope, lease, claimed)
            actual_factory = engine.harness_factory
            def harness_factory(selected):
                actual_harness = actual_factory(selected)
                class HarnessBarrier:
                    async def run_specialist(self, role):
                        # Entry occurs after both engine retry eligibility and
                        # final journal admission, before each actual SDK call.
                        if order == 1:
                            await both_ready.wait()
                        else:
                            both_ready.set()
                            await started.wait()
                        return await actual_harness.run_specialist(role)
                return HarnessBarrier()
            engine.harness_factory = harness_factory
            return engine
        worker = ResearchRetryWorker(store=rig.store, engine_factory=interleaved_factory)
        first = asyncio.create_task(worker.consume(rig.durable, rig.lease, rig.command_id))
        second = asyncio.create_task(worker.consume(rig.durable, rig.lease, rig.command_id))
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            await asyncio.wait_for(contenders[2], timeout=3)
        finally:
            release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(first, second,
            return_exceptions=True), timeout=3)
        checkpoint = rig.store.job(rig.durable)["fields"]["taxon"]["checkpoint"]
        assert checkpoint["revision"] == 2, outcomes
        assert checkpoint["payload"]["resolution"]["work_state"] == "waiting_source", outcomes
        assert saved(rig)["command"]["status"] == "completed", outcomes
        assert_one_cost(rig)
    asyncio.run(scenario())


def test_recording_trace_initial_race_reuses_immutable_parent(tmp_path,capfire):
    async def scenario():
        both_ready, started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def provider(_messages, _info):
            started.set()
            await release.wait()
        rig = await worker_rig_async(tmp_path, provider)
        factory_count = 0
        contenders = {}
        both_trace_reads = asyncio.Event()
        trace_read_count = 0
        def interleaved_factory(scope, lease, claimed):
            nonlocal factory_count
            factory_count += 1
            order = factory_count
            contenders[order] = asyncio.current_task()
            engine = rig.factory(scope, lease, claimed)
            original_trace_context = engine.journal.trace_context
            async def simultaneous_initial_trace_read(scope):
                nonlocal trace_read_count
                retained = await original_trace_context(scope)
                if retained is None:
                    trace_read_count += 1
                    if trace_read_count == 2:
                        both_trace_reads.set()
                    await both_trace_reads.wait()
                return retained
            engine.journal.trace_context = simultaneous_initial_trace_read
            actual_factory = engine.harness_factory
            def harness_factory(selected):
                actual_harness = actual_factory(selected)
                class HarnessBarrier:
                    async def run_specialist(self, role):
                        # Entry occurs after both engine retry eligibility and
                        # final journal admission, before each actual SDK call.
                        if order == 1:
                            await both_ready.wait()
                        else:
                            both_ready.set()
                            await started.wait()
                        return await actual_harness.run_specialist(role)
                return HarnessBarrier()
            engine.harness_factory = harness_factory
            return engine
        worker = ResearchRetryWorker(store=rig.store, engine_factory=interleaved_factory)
        first = asyncio.create_task(worker.consume(rig.durable, rig.lease, rig.command_id))
        second = asyncio.create_task(worker.consume(rig.durable, rig.lease, rig.command_id))
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            await asyncio.wait_for(contenders[2], timeout=3)
        finally:
            release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(first, second,
            return_exceptions=True), timeout=3)
        checkpoint = rig.store.job(rig.durable)["fields"]["taxon"]["checkpoint"]
        assert checkpoint["revision"] == 2, outcomes
        assert checkpoint["payload"]["resolution"]["work_state"] == "waiting_source", outcomes
        assert saved(rig)["command"]["status"] == "completed", outcomes
        assert_one_cost(rig)
        assert trace_read_count == 2
        parent = rig.store.job(rig.durable)["trace_context"]
        assert parent is not None and checkpoint["trace_context"] == parent
        import pytest
        conflicting = {**parent,"trace_id":"f"*32 if parent["trace_id"] != "f"*32 else "e"*32}
        with pytest.raises(ValueError,match="Trace context is immutable"):
            rig.store.bind_trace(rig.durable,rig.lease,conflicting)
        assert rig.store.job(rig.durable)["trace_context"] == parent
        spans = capfire.exporter.exported_spans_as_dict()
        scientific = [span for span in spans if span["name"] in {
            "research_harness.model","research_harness.specialist","research_harness.checkpoint"}]
        assert scientific
        assert {span["context"]["trace_id"] for span in scientific} == {int(parent["trace_id"],16)}
    asyncio.run(scenario())
