"""Concurrent roots and delegated helpers keep causal cost and scientific lineage apart."""

import asyncio
from types import SimpleNamespace

from specimen_digitization.research_harness.contracts import ResearchScope
from specimen_digitization.research_harness.gateway import (
    capture_model_run_effects, record_model_run_effect,
)


def test_overlapping_root_and_delegated_model_effect_scopes():
    scope = ResearchScope(organization_id="org", collection_id="collection", specimen_id="specimen",
        job_id="job", generation=1, input_digest="1" * 64,
        profile_digest="2" * 64, sensitive=False)

    async def exercise():
        ready = asyncio.Event()
        started = 0

        async def root(role, helper=None):
            nonlocal started
            with capture_model_run_effects(scope) as collected:
                started += 1
                if started == 2:
                    ready.set()
                await ready.wait()

                async def complete(served_role, identity, cost):
                    await asyncio.sleep(0)
                    record_model_run_effect(scope, served_role, (served_role,),
                        SimpleNamespace(effect_id=identity, actual_micro_usd=cost))

                calls = [complete(role, "own:" + role, 3)]
                if helper:
                    calls.append(asyncio.create_task(complete(helper, "helper:" + helper, 5)))
                await asyncio.gather(*calls)
                owned = collected.owned(role, (role,))
                costs = collected.costs()
            # A detached child that inherited the old ContextVar must not add
            # an effect to a completed specialist invocation.
            record_model_run_effect(scope, role, (role,),
                SimpleNamespace(effect_id="late:" + role, actual_micro_usd=99))
            return owned, costs, collected.entries

        return await asyncio.gather(root("specimen_geography", "specimen_taxonomy"),
                                    root("specimen_taxonomy"))

    geography, taxonomy = asyncio.run(exercise())
    assert geography[0] == ("own:specimen_geography",)
    assert taxonomy[0] == ("own:specimen_taxonomy",)
    assert sorted(geography[1]) == [3, 5] and taxonomy[1] == (3,)
    assert "late:specimen_geography" not in [item[0] for item in geography[2]]
