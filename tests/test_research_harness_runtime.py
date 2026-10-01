"""Production composition uses actual official agents and persisted SQL journals."""

import asyncio
import hashlib
from dataclasses import asdict

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness.agents import SpecialistOutput, specialist_output_schema_digest
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldProfile, FieldResolution,
    ResearchScope, SpecialistRequest, WorkState, digest, SourceFragment, EventHypothesis, EventKind, FieldKey, SpecialistRole,
)
from specimen_digitization.research_harness.evidence import assemble_field
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, ImmutableFileBlobs, ResearchStore, SqliteStateBackend,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import build_research_engine, runtime_pins
from specimen_digitization.research_harness.sources import SourceBroker, insects_registry
from specimen_digitization.research_harness.thread_view import ResearchThreadReader


def test_all_six_agents_use_persisted_journals_and_reopen_without_effects(tmp_path):
    registry = insects_registry()
    profile = CollectionProfile(id="insects", version="fixture-v1", organization_id="org-test",
        collection_id="collection-test", ancestry=("org-test", "collection-test"),
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS), knowledge_version="fixture-v1")
    scope = ResearchScope(organization_id="org-test", collection_id="collection-test",
        specimen_id="specimen-test", job_id="job-test", generation=1, input_digest="a"*64,
        profile_digest=digest(profile), sensitive=False)
    requests = {role:SpecialistRequest(scope=scope, role=role, field_keys=fields,
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest,
            source_registry_digest=registry.digest, toolset_digest="b"*64,
            model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()))
        for role,fields in ROLE_FIELDS.items()}
    fragment = SourceFragment(id="measurement-fragment", scope=scope, asset_id="asset-test",
        asset_generation="1", asset_digest="e"*64, label_id="label-test", region_id="region-test",
        observation_id="observation-test", reader="fixture-reader", model_id="fixture-model",
        prompt_digest="f"*64, observation_text="100 ft",
        observation_digest=hashlib.sha256(b"100 ft").hexdigest(), start=0, end=6, literal="100 ft", order=0)
    event = EventHypothesis(id="collecting-test", scope=scope, kind=EventKind.COLLECTING,
        fragment_ids=(fragment.id,), evidence_ids=("event-fixture",), reason="Independent fixture annotation",
        status="accepted", validator_version="fixture-v1")
    assembly = assemble_field(assembly_id="assembly-test", scope=scope, field_key=FieldKey.ELEVATION_FROM_FT,
        fragments=(fragment,), event=event)
    requests[SpecialistRole.MEASUREMENT] = requests[SpecialistRole.MEASUREMENT].model_copy(update={
        "fragments":(fragment,), "events":(event,), "assemblies":(assembly,)})
    bindings = {role:ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 10, "offline-v1") for role in requests}
    settings = {"max_tokens":128}
    pins = runtime_pins(profile, requests,
        model={role:{"route":b.route_id, **asdict(b)} for role,b in bindings.items()}, settings=settings)
    durable = DurabilityScope(scope.organization_id, scope.collection_id, scope.specimen_id,
        scope.job_id, scope.generation, "operator-test", False)
    backend = SqliteStateBackend(tmp_path / "research.sqlite")
    backend.grant(durable)
    store = ResearchStore(backend, "same-existing-program")
    store.initialize(durable, BudgetPolicy(1000))
    store.create_job(durable, pins, list(ALL_FIELDS))
    lease = store.claim(durable, "worker-test", ttl_seconds=120)
    calls = []

    def base_model(request):
        def respond(messages, info):
            calls.append(request.role)
            returns = [part for message in messages for part in message.parts
                       if getattr(part, "part_kind", None) == "tool-return"]
            if not returns:
                if request.role == SpecialistRole.MEASUREMENT:
                    return ModelResponse(parts=[ToolCallPart("invoke_utility", {"tool_id":"parse_measurement",
                        "arguments":{"field_key":"elevation_from_ft", "text":"100 ft"}}, tool_call_id="parse-fixture")],
                        usage=RequestUsage(input_tokens=1, output_tokens=1))
                return ModelResponse(parts=[ToolCallPart("lookup_source", {"query":{
                    "source_id":"field_museum_ipt", "field_key":request.field_keys[0],
                    "query_text":"synthetic"}}, tool_call_id="lookup-fixture")],
                    usage=RequestUsage(input_tokens=1, output_tokens=1))
            output = SpecialistOutput(role=request.role, resolutions=tuple(FieldResolution(
                field_key=key, work_state=WorkState.WAITING_POLICY if str(key)=="verbatim_dts" else WorkState.WAITING_SOURCE,
                value=FieldValue(), reason="source_qualification_required") for key in request.field_keys))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="final-fixture")],
                usage=RequestUsage(input_tokens=1, output_tokens=1))
        return FunctionModel(respond)

    engine = build_research_engine(profile=profile, requests=requests, store=store, scope=durable,
        lease=lease, blobs=ImmutableFileBlobs(tmp_path / "blobs"), tool_broker=SourceBroker(registry),
        bindings=bindings, settings=settings, base_model_factory=base_model, actual_cost=lambda response:3)
    result = asyncio.run(engine.run())
    assert len(result.checkpoints) == 20 and not result.clearance_eligible
    assert all(item.work_state in {WorkState.WAITING_SOURCE, WorkState.WAITING_POLICY} for item in result.fields.values()), {str(k):str(v.work_state) for k,v in result.fields.items()}
    assert len(calls) == 12
    assert store.budget(durable)["settled_micro_usd"] == 36
    assert store.budget(durable)["held_micro_usd"] == 0
    thread = asyncio.run(ResearchThreadReader(engine.journal).read(scope))
    assert len(thread.fields) == 20 and len(thread.effects) == 12
    assert len(store._read(durable).state["journal"]) == 6
    calls.clear()
    assert asyncio.run(engine.run()).fields == result.fields
    assert calls == []
