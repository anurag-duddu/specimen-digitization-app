"""Independent specialists in one harness: own effects, own tools, no delegation.

Several specialists run at once in a lease window (native_worker, one role window).
Each is its own agent with its own model: its model effects are its own model's
effects, whoever else is in flight, and it is never handed a delegate_task tool
for another specialist's role. Offline: scripted models behind the real
EffectModel, the SQLite state store and the real Agent/Harness capabilities.
"""
import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
from pydantic_ai_harness.step_persistence import InMemoryStepStore

from specimen_digitization.research_harness.agents import SpecialistHarness
from specimen_digitization.research_harness.contracts import SpecialistRole
from specimen_digitization.research_harness.gateway import ModelGatewayBlocked

from test_research_harness_agents import FixtureTools, model, output, requests, sql_broker

TAXONOMY, GEOGRAPHY, TEMPORAL = SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY, SpecialistRole.TEMPORAL


class Rig:
    """A harness over ``roles`` whose scripted model for each role is held by a gate.

    ``gates[role]`` is an event the role's model waits for before it answers;
    ``entered[role]`` is set when that model request is in flight. ``seen[role]``
    keeps the tool names and the instructions the model was shown."""

    def __init__(self, tmp_path, roles, *, delegation=False):
        tmp_path.mkdir(exist_ok=True)
        pinned = {role: request for role, request in requests().items() if role in roles}
        self.store, self.scope, lease, broker = sql_broker(tmp_path)
        self.gates = {role: asyncio.Event() for role in roles}
        self.entered = {role: asyncio.Event() for role in roles}
        self.seen = {}
        for gate in self.gates.values():
            gate.set()

        def factory(request):
            role = request.role

            async def respond(messages, info):
                self.seen[role] = (sorted(tool.name for tool in info.function_tools), info.instructions or "")
                self.entered[role].set()
                await self.gates[role].wait()
                return ModelResponse([ToolCallPart(info.output_tools[0].name,
                    output(request).model_dump(mode="json"), tool_call_id="output-fixture")],
                    usage=RequestUsage(input_tokens=11, output_tokens=7))
            return model(FunctionModel(respond), request=request, broker=broker, scope=self.scope, lease=lease)

        self.runtime = SpecialistHarness(requests=pinned, model_factory=factory, tool_broker=FixtureTools(),
            step_store_factory=lambda _: InMemoryStepStore(), **({"delegation": True} if delegation else {}))

    def operation_keys(self, run):
        return [self.store.effect(self.scope, effect)["operation_key"] for effect in run.model_effect_ids]


def test_a_specialist_collects_only_its_own_model_effects_while_another_is_in_flight(tmp_path):
    rig = Rig(tmp_path, (TAXONOMY, GEOGRAPHY))
    rig.gates[TAXONOMY].clear()

    async def scenario():
        taxonomy = asyncio.create_task(rig.runtime.run_specialist(TAXONOMY))
        await rig.entered[TAXONOMY].wait()
        # Geography runs to its end while taxonomy's request is still in flight.
        geography = await rig.runtime.run_specialist(GEOGRAPHY)
        rig.gates[TAXONOMY].set()
        return await taxonomy, geography
    taxonomy, geography = asyncio.run(scenario())
    # Before: taxonomy's run collected every model's new effects, geography's included,
    # so its checkpoints named another specialist's receipt and publication refused them
    # (native_publication_receipt_binding_changed).
    assert rig.operation_keys(taxonomy) == ["model:specimen_taxonomy"]
    assert rig.operation_keys(geography) == ["model:specimen_geography"]


def test_the_specialist_that_finishes_first_does_not_collect_the_one_still_running(tmp_path):
    rig = Rig(tmp_path, (TAXONOMY, GEOGRAPHY))
    rig.gates[GEOGRAPHY].clear()

    async def scenario():
        geography = asyncio.create_task(rig.runtime.run_specialist(GEOGRAPHY))
        await rig.entered[GEOGRAPHY].wait()
        taxonomy = await rig.runtime.run_specialist(TAXONOMY)
        # Taxonomy has finished; geography's request is still unanswered, then answers.
        assert not geography.done()
        rig.gates[GEOGRAPHY].set()
        return taxonomy, await geography
    taxonomy, geography = asyncio.run(scenario())
    assert rig.operation_keys(taxonomy) == ["model:specimen_taxonomy"]
    assert rig.operation_keys(geography) == ["model:specimen_geography"]


def test_a_specialist_in_a_window_has_the_tools_and_instructions_it_has_alone(tmp_path):
    alone = Rig(tmp_path / "alone", (TAXONOMY,))
    asyncio.run(alone.runtime.run_specialist(TAXONOMY))
    shared = Rig(tmp_path / "shared", tuple(SpecialistRole))

    async def every_role():
        for role in SpecialistRole:
            await shared.runtime.run_specialist(role)
    asyncio.run(every_role())
    tools, instructions = alone.seen[TAXONOMY]
    assert tools == ["invoke_utility", "lookup_source"]
    for role in SpecialistRole:
        # No delegate_task tool and no sub-agent listing in the instructions, whatever
        # roles share the harness: the tools and instructions each model request carries
        # are the ones a lone specialist's carry (apart from the role's own prompt).
        assert shared.seen[role][0] == tools, role
        assert "delegate" not in shared.seen[role][1].lower() and "sub-agent" not in shared.seen[role][1].lower(), role
    assert shared.seen[TAXONOMY] == alone.seen[TAXONOMY]
    assert shared.runtime.delegation == {} and shared.runtime.helpers == {}


def test_delegation_is_opt_in_and_lists_only_the_other_roles(tmp_path):
    rig = Rig(tmp_path, (TAXONOMY, GEOGRAPHY, TEMPORAL), delegation=True)
    asyncio.run(rig.runtime.run_specialist(TAXONOMY))
    tools, instructions = rig.seen[TAXONOMY]
    assert tools == ["delegate_task", "invoke_utility", "lookup_source"]
    listing = instructions.split("Available sub-agents:")[1].split("\n\n")[0]
    assert "specimen_geography" in listing and "specimen_temporal" in listing and "specimen_taxonomy" not in listing
    assert {role: len(item.agents) for role, item in rig.runtime.delegation.items()} == {
        TAXONOMY: 2, GEOGRAPHY: 2, TEMPORAL: 2}


def test_a_delegating_harness_refuses_a_second_specialist_while_one_runs(tmp_path):
    """Delegated requests go through another role's model, so the effects of a run are found
    by looking at every model. That is exact only if nothing else runs: refuse, do not misattribute."""
    rig = Rig(tmp_path, (TAXONOMY, GEOGRAPHY), delegation=True)
    rig.gates[TAXONOMY].clear()

    async def scenario():
        first = asyncio.create_task(rig.runtime.run_specialist(TAXONOMY))
        await rig.entered[TAXONOMY].wait()
        with pytest.raises(ModelGatewayBlocked, match="delegation_requires_one_specialist_run_at_a_time"):
            await rig.runtime.run_specialist(GEOGRAPHY)
        rig.gates[TAXONOMY].set()
        done = await first
        # Once it ends, the next specialist may run (the counter is released).
        return done, await rig.runtime.run_specialist(GEOGRAPHY)
    first, second = asyncio.run(scenario())
    assert rig.operation_keys(first) == ["model:specimen_taxonomy"]
    assert rig.operation_keys(second) == ["model:specimen_geography"]
