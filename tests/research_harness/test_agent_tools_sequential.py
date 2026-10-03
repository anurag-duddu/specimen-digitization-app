"""A specialist that asks for several lookups in one response must not poison its run.

pydantic-ai runs the tool calls of one model response concurrently unless a tool is
registered ``sequential=True``. The taxonomy specialist has three ready sources
(gbif, global_names_verifier, catalogue_of_life) for the one field ``taxon``; asked
for all three at once, the durable effect broker sees sibling effects on the same
field (SourceCaptureEffectsV2.validate_current), holds them as ``held_unknown`` and
the run ends ``research_worker_custody_requires_reconciliation`` with no retry.

The end-to-end test drives the production composer with a scripted FunctionModel
that makes all three lookups in its first response. The other two tests are the
cheap agent-level checks: the tool definitions the model is shown, and that the
calls of one response never overlap.

Offline only: scripted models and recorded sources. This is not a production
observation.
"""
from __future__ import annotations

import asyncio

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness.agents import (
    ResearchDeps, SpecialistHarness, specialist_output_schema_digest,
)
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, FieldKey, ResearchScope, SourceCoverageReceipt, SourceCoverageState, SourceResult,
    SpecialistRequest, SpecialistRole,
)
from specimen_digitization.research_harness.persistence import DurabilityScope
from specimen_digitization.research_harness.production_runtime import research_program_key
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

# Fixtures of the production end-to-end rig, reused unchanged.
from test_production_e2e import SWITCH_ON, no_network, rig, supervised, to_plan  # noqa: F401

TOOLS = ("lookup_source", "invoke_utility")
# The three sources' hosts, in the order the scripted model asks for them.
SOURCE_HOSTS = ["api.gbif.org", "verifier.globalnames.org", "api.checklistbank.org"]


def parallel_taxonomy_factory(log, seen_tools):
    """The e2e scripted model, except that the taxonomy specialist's first response
    asks for every taxonomy source at once; later turns and other roles are unchanged."""
    base = support.scripted_model_factory(log)

    def factory(request, binding):
        scripted = base(request, binding)
        if request.role != SpecialistRole.TAXONOMY:
            return scripted
        proceed = scripted.function

        def respond(messages, info):
            first_turn = not any(isinstance(message, ModelResponse) for message in messages)
            rows = support._assemblies(request, FieldKey.TAXON)
            if not (first_turn and rows):
                return proceed(messages, info)
            seen_tools.update({tool.name: tool.sequential for tool in info.function_tools})
            log.append((str(request.role), "all-three-lookups-in-one-response"))
            return ModelResponse(parts=[
                ToolCallPart("lookup_source", {"query": {
                    "source_id": source, "field_key": str(FieldKey.TAXON),
                    "query_text": rows[0].interpreted_text}}, tool_call_id=f"one-response-{source}")
                for source in support.TAXONOMY_SOURCES], usage=support.USAGE)

        return FunctionModel(respond)

    factory.fallbacks, factory.errors = base.fallbacks, base.errors
    return factory


def test_three_taxonomy_lookups_in_one_response_leave_the_run_healthy(rig):  # noqa: F811
    seen_tools, plan_outcome = {}, None
    workflow = compose_production_research_workflow(
        rig.ordinary, repository=rig.repository, environ=SWITCH_ON, actor_uid=support.WORKER,
        state_backend=rig.backend, model_factory=parallel_taxonomy_factory(rig.model_calls, seen_tools),
        source_transport=support.fixture_source_transport(rig.source_urls), blobs=rig.research_blobs)
    parsed = to_plan(workflow, rig)
    try:
        with supervised():
            workflow.step(rig.principal, rig.specimen_id)
    except OperationalBlock as block:
        plan_outcome = str(block)

    # The scripted model really asked for all three at once.
    assert ("specimen_taxonomy", "all-three-lookups-in-one-response") in rig.model_calls
    state = rig.backend.load(
        DurabilityScope(support.ORG, support.COLLECTION, rig.specimen_id, f"{parsed.run.id}-r3", 1,
                        support.WORKER, False),
        research_program_key(parsed.run.id)).state
    effects = list(state["effects"].values())
    job = next(iter(state["jobs"].values()))
    # Not poisoned: no effect is held or still sending, the taxon resolved, and the
    # tick did not end in the custody hold (whether it ends in an ordinary operational
    # hold for fields whose sources are not ready is not asserted).
    assert plan_outcome != "research_worker_custody_requires_reconciliation"
    assert [effect["status"] for effect in effects if effect["status"] != "completed"] == []
    assert job["fields"]["taxon"]["work_state"] == "resolved"
    # Only the taxonomy field is asserted: other roles (geography's GEOLocate lookups)
    # also fetch URLs and capture sources.
    assert [host for host in (url.split("/")[2] for url in rig.source_urls) if host in SOURCE_HOSTS] == SOURCE_HOSTS
    assert sum(effect["operation_key"].startswith("source_capture_v2:") and effect["field_keys"] == ["taxon"]
               for effect in effects) == 3
    # The production specialist was offered both tools as sequential barriers (the
    # flag survives the Instrumentation, StepPersistence and SubAgents wrappers).
    assert {name: seen_tools[name] for name in TOOLS} == {"lookup_source": True, "invoke_utility": True}


def specialist_request():
    scope = ResearchScope(organization_id="org", collection_id="insects", specimen_id="synthetic",
                          job_id="job", generation=1, input_digest="a" * 64, profile_digest="b" * 64)
    role = SpecialistRole.TAXONOMY
    prompt = resolve_prompt(role, profile_digest=scope.profile_digest, source_registry_digest="c" * 64,
                            toolset_digest="d" * 64, model_route="harness-deepseek",
                            output_schema_digest=specialist_output_schema_digest())
    return SpecialistRequest(scope=scope, role=role, field_keys=ROLE_FIELDS[role], prompt=prompt)


def finish():
    return ModelResponse(parts=[TextPart("done")], usage=support.USAGE)


class OverlapProbe:
    """A tool broker that records how many tool calls are in flight at once."""

    def __init__(self):
        self.in_flight = self.most_in_flight = 0
        self.started = []

    async def query_source(self, request, query):
        return await self._call(query.source_id)

    async def invoke_utility(self, request, tool_id, arguments):
        return await self._call(tool_id)

    async def _call(self, name):
        self.started.append(name)
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        return SourceResult(status=LookupStatus.POLICY, coverage=SourceCoverageReceipt(
            source_id=name, field_key=FieldKey.TAXON, state=SourceCoverageState.UNQUALIFIED,
            source_version="fixture-v1", coverage_limit="offline fixture",
            reason="source_requires_qualification"))


def bare_specialist_agent(respond):
    """The production tool registration on an agent whose model is the given function."""
    agent = Agent(FunctionModel(respond), name=SpecialistRole.TAXONOMY.value, deps_type=ResearchDeps)
    SpecialistHarness._register_tools(agent)
    return agent


def test_both_specialist_tools_are_registered_sequential():
    seen = {}

    def respond(messages, info):
        seen.update({tool.name: tool.sequential for tool in info.function_tools})
        return finish()

    bare_specialist_agent(respond).run_sync("go")
    assert {name: seen[name] for name in TOOLS} == {"lookup_source": True, "invoke_utility": True}


def test_tool_calls_of_one_response_never_overlap_and_keep_the_models_order():
    request, probe = specialist_request(), OverlapProbe()
    sources = ("gbif", "global_names_verifier", "catalogue_of_life")

    def respond(messages, info):
        if any(isinstance(message, ModelResponse) for message in messages):
            return finish()
        lookups = [ToolCallPart("lookup_source", {"query": {"source_id": source, "field_key": "taxon"}},
                                tool_call_id=f"lookup-{source}") for source in sources]
        utility = ToolCallPart("invoke_utility", {"tool_id": "utility-x", "arguments": {}},
                               tool_call_id="utility-x")
        return ModelResponse(parts=[*lookups, utility], usage=support.USAGE)

    deps = ResearchDeps({SpecialistRole.TAXONOMY: request}, probe)
    bare_specialist_agent(respond).run_sync("go", deps=deps)
    assert probe.started == [*sources, "utility-x"]
    assert probe.most_in_flight == 1
