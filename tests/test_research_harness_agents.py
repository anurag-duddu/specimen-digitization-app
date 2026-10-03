"""Offline execution against real Agent, Harness, journal and SQL effect APIs."""

import asyncio
import json
from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
from pydantic_ai_harness import ManagedPrompt
from pydantic_ai_harness.step_persistence import InMemoryStepStore

from specimen_digitization.application.domain import FieldValue, LookupStatus
from specimen_digitization.model_gateway import HuggingFaceModelGateway
from specimen_digitization.research_harness.agents import (
    HarnessLimits, PinnedManagedPrompt, SpecialistHarness, SpecialistOutput,
    capture_managed_prompt_pin, request_model_pins, specialist_output_schema_digest,
)
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, FieldKey, FieldResolution, ResearchScope, SourceCoverageReceipt,
    SourceCoverageState, SourceResult, SpecialistRequest, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.gateway import EffectModel, ModelBinding, ModelGatewayBlocked
from specimen_digitization.research_harness.package_qualification import qualify_packages
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, DurableEffectBroker, HeldUnknown, ImmutableFileBlobs,
    PinnedRuntime, ResearchStore, SqliteStateBackend,
)
from specimen_digitization.research_harness.prompts import resolve_prompt


def requests():
    scope = ResearchScope(organization_id="org", collection_id="insects", specimen_id="synthetic",
                          job_id="job", generation=1, input_digest="a" * 64, profile_digest="b" * 64)
    return {
        role: SpecialistRequest(scope=scope, role=role, field_keys=ROLE_FIELDS[role],
                                prompt=resolve_prompt(role, profile_digest=scope.profile_digest,
                                                      source_registry_digest="c" * 64,
                                                      toolset_digest="d" * 64,
                                                      model_route="harness-deepseek",
                                                      output_schema_digest=specialist_output_schema_digest()))
        for role in SpecialistRole
    }


def sql_broker(tmp_path):
    scope = DurabilityScope("org", "insects", "synthetic", "job", 1, "worker")
    backend = SqliteStateBackend(tmp_path / "research.sqlite")
    backend.grant(scope, can_view_sensitive=True)
    store = ResearchStore(backend, "existing-program-ledger")
    store.initialize(scope, BudgetPolicy(10000))
    store.create_job(scope, PinnedRuntime("a" * 64, {"digest": "b" * 64}, {"version": "v1"},
                                         {"digest": "c" * 64}, {"route": "harness-deepseek"},
                                         {"max_tokens": 128}, "specialist_harness_v2"),
                     [key.value for fields in ROLE_FIELDS.values() for key in fields])
    lease = store.claim(scope, "worker", ttl_seconds=120)
    return store, scope, lease, DurableEffectBroker(store, ImmutableFileBlobs(tmp_path / "blobs"))


def model(wrapped, *, request, broker, scope, lease, known_cost=True, request_guard=None):
    return EffectModel(wrapped, broker=broker, scope=scope, lease=lease, role=request.role.value,
                       binding=ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
                                            "deepinfra", 128, 10, "offline-price-fixture-v1"),
                       pins=request_model_pins(request),
                       actual_cost=(lambda _: 3) if known_cost else None, request_guard=request_guard)


class FixtureTools:
    def __init__(self):
        self.calls = []

    async def query_source(self, request, query):
        assert query.field_key in request.field_keys
        self.calls.append((request.role, request.scope, query.field_key))
        return SourceResult(status=LookupStatus.POLICY,
                            coverage=SourceCoverageReceipt(source_id=query.source_id,
                                                           field_key=query.field_key,
                                                           state=SourceCoverageState.UNQUALIFIED,
                                                           source_version="fixture-v1",
                                                           coverage_limit="offline fixture",
                                                           reason="source_requires_qualification"))

    async def invoke_utility(self, request, tool_id, arguments):
        return await self.query_source(request, type("Query", (), {
            "field_key": request.field_keys[0], "source_id": tool_id,
        })())


def output(request):
    return SpecialistOutput(role=request.role, resolutions=tuple(
        FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY if key == FieldKey.VERBATIM_DTS else WorkState.WAITING_SOURCE,
                        value=FieldValue(), reason="source_requires_qualification")
        for key in request.field_keys
    ))


def scripted(request, *, delegate=None):
    calls = []

    def respond(messages, info):
        calls.append((messages, info))
        tools = [part for message in messages for part in message.parts
                 if getattr(part, "part_kind", None) == "tool-return"]
        if not tools:
            if delegate:
                part = ToolCallPart("delegate_task", {"agent_name": delegate.value,
                                                      "task": "Use only your frozen request and approved tools"},
                                    tool_call_id="delegate-fixture")
            else:
                part = ToolCallPart("lookup_source", {"query": {
                    "source_id": "fixture-source", "field_key": request.field_keys[0].value,
                    "query_text": "private_label_canary",
                }}, tool_call_id="lookup-fixture")
            return ModelResponse([part], usage=RequestUsage(input_tokens=11, output_tokens=7))
        return ModelResponse([ToolCallPart(info.output_tools[0].name,
                                          output(request).model_dump(mode="json"),
                                          tool_call_id="output-fixture")],
                             usage=RequestUsage(input_tokens=11, output_tokens=7))

    return FunctionModel(respond), calls


def harness(tmp_path, *, delegate=None, limits=HarnessLimits()):
    pinned = requests()
    store, scope, lease, broker = sql_broker(tmp_path)
    tools, journal, calls = FixtureTools(), InMemoryStepStore(), {}

    def factory(request):
        wrapped, calls[request.role] = scripted(request, delegate=delegate if request.role == SpecialistRole.TAXONOMY else None)
        return model(wrapped, request=request, broker=broker, scope=scope, lease=lease)

    runtime = SpecialistHarness(requests=pinned, model_factory=factory, tool_broker=tools,
                                step_store_factory=lambda _: journal, limits=limits)
    return runtime, store, scope, tools, journal, calls


def test_exact_package_surface_qualified_without_network():
    result = qualify_packages()
    assert result.packages["pydantic-ai-harness"] == "0.36.0"
    assert result.provider_qualification == result.cloud_qualification == "not_run"


@pytest.mark.parametrize("role", list(SpecialistRole))
def test_six_specialists_execute_registered_tool_and_typed_output(tmp_path, role):
    runtime, store, scope, tools, journal, calls = harness(tmp_path)
    run = asyncio.run(runtime.run_specialist(role))
    assert {resolution.field_key for resolution in run.resolutions} == set(ROLE_FIELDS[role])
    assert len(calls[role]) == 2
    assert tools.calls[0][0] == role
    assert len(run.tool_results) == 1
    assert len(run.model_effect_ids) == 2
    assert store.budget(scope)["settled_micro_usd"] == 6
    assert store.budget(scope)["held_micro_usd"] == 0
    records = asyncio.run(journal.list_runs())
    assert len(records) == 1 and records[0].agent_name == role.value
    snapshot = asyncio.run(journal.latest_snapshot(run_id=records[0].run_id))
    assert snapshot is not None and snapshot.state == "complete"
    for capability in runtime.delegation.values():
        assert capability.agent_folders is None
        assert capability.inherit_tools is False
        assert len(capability.agents) == 5


def test_actual_official_delegation_uses_child_role_tools_and_shared_sql_budget(tmp_path):
    runtime, store, scope, tools, journal, calls = harness(tmp_path, delegate=SpecialistRole.GEOGRAPHY)
    run = asyncio.run(runtime.run_specialist(SpecialistRole.TAXONOMY))
    assert len(calls[SpecialistRole.GEOGRAPHY]) == 2
    assert tools.calls[0][0] == SpecialistRole.GEOGRAPHY
    assert tools.calls[0][2] in ROLE_FIELDS[SpecialistRole.GEOGRAPHY]
    records = asyncio.run(journal.list_runs())
    child = next(record for record in records if record.agent_name == SpecialistRole.GEOGRAPHY)
    assert child.parent_run_id == run.native_run_id
    assert store.budget(scope)["settled_micro_usd"] == 12
    # Child's explicit UsageLimits do not aggregate its requests into the parent.
    # The durable SQL budget above does aggregate all four model effects.
    assert run.usage.requests == 2


def test_model_receipt_replay_ignores_transport_timestamp_and_retains_unknown_cost(tmp_path):
    store, scope, lease, broker = sql_broker(tmp_path)
    request = requests()[SpecialistRole.TAXONOMY]
    calls = []

    def respond(messages, info):
        calls.append(messages)
        return ModelResponse([TextPart("private_response_canary")],
                             usage=RequestUsage(input_tokens=11, output_tokens=7))

    gateway = model(FunctionModel(respond), request=request, broker=broker, scope=scope,
                    lease=lease, known_cost=False)
    from pydantic_ai.models import ModelRequestParameters
    parameters = ModelRequestParameters()
    first = [ModelRequest([UserPromptPart("private_label_canary", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))])]
    second = [ModelRequest([UserPromptPart("private_label_canary", timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc))])]
    one = asyncio.run(gateway.request(first, {"max_tokens": 128}, parameters))
    two = asyncio.run(gateway.request(second, {"max_tokens": 128}, parameters))
    assert one == two
    assert len(calls) == 1
    assert store.budget(scope)["held_micro_usd"] == 10


def test_provider_failure_sanitized_and_sent_unknown_is_not_reissued(tmp_path, capfire):
    store, scope, lease, broker = sql_broker(tmp_path)
    request = requests()[SpecialistRole.TAXONOMY]
    calls = []

    def respond(messages, info):
        calls.append(1)
        raise RuntimeError("private_provider_body_canary")

    gateway = model(FunctionModel(respond), request=request, broker=broker, scope=scope, lease=lease)
    agent = Agent(gateway)
    from specimen_digitization.provider_privacy import private_instrumentation
    agent.instrument = private_instrumentation()
    with pytest.raises(RuntimeError, match="provider_request_failed"):
        agent.run_sync("private_label_canary")
    with pytest.raises(HeldUnknown):
        agent.run_sync("private_label_canary")
    assert len(calls) == 1
    exported = json.dumps(capfire.exporter.exported_spans_as_dict(), default=str)
    assert "private_provider_body_canary" not in exported
    assert "private_label_canary" not in exported
    assert store.budget(scope)["held_micro_usd"] == 10


def test_prompt_capability_never_resolves_mutable_label_on_run(tmp_path, monkeypatch):
    runtime, *_ = harness(tmp_path)
    for agent in runtime.agents.values():
        capability = next(item for item in agent.root_capability.capabilities if isinstance(item, PinnedManagedPrompt))
        assert isinstance(capability, ManagedPrompt)
        monkeypatch.setattr(capability._variable, "get", lambda **_: pytest.fail("Continuation re-resolved a mutable label"))
    asyncio.run(runtime.run_specialist(SpecialistRole.TAXONOMY))


def test_ungated_models_and_unqualified_external_model_paths_rejected(tmp_path):
    runtime, *_ = harness(tmp_path)
    model = runtime.models[SpecialistRole.TAXONOMY]
    with pytest.raises(ModelGatewayBlocked):
        asyncio.run(model.count_tokens([], None, None))
    with pytest.raises(ModelGatewayBlocked):
        asyncio.run(model.compact_messages(None))
    async def stream():
        async with model.request_stream([], None, None):
            pytest.fail("ungated streaming")
    with pytest.raises(ModelGatewayBlocked):
        asyncio.run(stream())


def test_malformed_final_output_retry_does_not_export_private_arguments(tmp_path, capfire):
    runtime, *_ = harness(tmp_path)
    role = SpecialistRole.TAXONOMY
    calls = []

    def invalid(messages, info):
        calls.append(1)
        return ModelResponse([ToolCallPart(info.output_tools[0].name,
                                          {"role": "private_invalid_role_canary", "resolutions": []})])

    runtime.models[role].wrapped.wrapped = FunctionModel(invalid)
    with pytest.raises(Exception):
        asyncio.run(runtime.run_specialist(role))
    assert len(calls) == 2
    exported = json.dumps(capfire.exporter.exported_spans_as_dict(), default=str)
    assert "private_invalid_role_canary" not in exported
    assert "private_label_canary" not in exported


def test_tool_failure_body_sanitized_before_sdk_or_child_logs(tmp_path, capfire):
    runtime, *_ = harness(tmp_path)

    async def broken(*_):
        raise RuntimeError("private_source_body_canary")

    runtime.tool_broker.query_source = broken
    with pytest.raises(RuntimeError, match="research_source_tool_failed"):
        asyncio.run(runtime.run_specialist(SpecialistRole.TAXONOMY))
    exported = json.dumps(capfire.exporter.exported_spans_as_dict(), default=str)
    assert "private_source_body_canary" not in exported


def test_actual_240_serialized_tool_history_reads_and_continues_on_251(tmp_path):
    # Generated with an isolated official pydantic-ai-slim==2.40.0 environment,
    # not reconstructed by the 2.51 reader under test.
    historical_json = r'''[{"parts":[{"content":"historical synthetic input","timestamp":"2026-09-29T00:00:00Z","part_kind":"user-prompt"}],"timestamp":null,"instructions":null,"kind":"request","run_id":null,"conversation_id":null,"metadata":null,"state":"complete"},{"parts":[{"tool_name":"lookup","args":{"name":"alpha"},"tool_call_id":"old-call","tool_kind":null,"id":null,"provider_name":null,"provider_details":null,"part_kind":"tool-call"}],"usage":{"input_tokens":0,"cache_write_tokens":0,"cache_read_tokens":0,"output_tokens":0,"input_audio_tokens":0,"cache_audio_read_tokens":0,"output_audio_tokens":0,"details":{},"cost":null},"model_name":null,"timestamp":"2026-09-29T00:00:00Z","kind":"response","provider_name":null,"provider_url":null,"provider_details":null,"provider_response_id":null,"finish_reason":null,"run_id":null,"conversation_id":null,"metadata":null,"state":"complete"},{"parts":[{"tool_name":"lookup","content":"code 7","tool_call_id":"old-call","tool_kind":null,"metadata":null,"timestamp":"2026-09-29T00:00:00Z","outcome":"success","part_kind":"tool-return"}],"timestamp":null,"instructions":null,"kind":"request","run_id":null,"conversation_id":null,"metadata":null,"state":"complete"}]'''
    messages = ModelMessagesTypeAdapter.validate_json(historical_json)
    store, scope, lease, broker = sql_broker(tmp_path)
    request = requests()[SpecialistRole.TAXONOMY]

    def continue_history(history, info):
        call = next(part for message in history for part in message.parts if isinstance(part, ToolCallPart))
        assert call.args_as_dict() == {"name": "alpha"}
        return ModelResponse([TextPart("history compatible")], usage=RequestUsage(input_tokens=3, output_tokens=2))

    gated = model(FunctionModel(continue_history), request=request, broker=broker, scope=scope, lease=lease)
    result = Agent(gated).run_sync("Continue the existing history", message_history=messages)
    assert result.output == "history compatible"
    assert store.budget(scope)["settled_micro_usd"] == 3


def test_child_timeout_retains_hold_and_parent_finishes_independently(tmp_path):
    limits = HarnessLimits(delegate_timeout_seconds=0.03, run_timeout_seconds=3)
    runtime, store, scope, _, journal, _ = harness(tmp_path, delegate=SpecialistRole.GEOGRAPHY,
                                                 limits=limits)
    child_calls = []

    async def stuck(messages, info):
        child_calls.append(1)
        await asyncio.Event().wait()

    runtime.models[SpecialistRole.GEOGRAPHY].wrapped.wrapped = FunctionModel(stuck)
    result = asyncio.run(runtime.run_specialist(SpecialistRole.TAXONOMY))
    assert result.resolutions[0].work_state == WorkState.WAITING_SOURCE
    assert len(child_calls) == 1
    assert store.budget(scope)["held_micro_usd"] == 10
    assert store.budget(scope)["settled_micro_usd"] == 6
    records = asyncio.run(journal.list_runs())
    assert {item.agent_name for item in records} == {"specimen_taxonomy", "specimen_geography"}


def test_tree_cancellation_preserves_child_unknown_effect_and_parent_receipt(tmp_path):
    runtime, store, scope, *_ = harness(tmp_path, delegate=SpecialistRole.GEOGRAPHY)

    async def cancel_tree():
        started = asyncio.Event()

        async def stuck(messages, info):
            started.set()
            await asyncio.Event().wait()

        runtime.models[SpecialistRole.GEOGRAPHY].wrapped.wrapped = FunctionModel(stuck)
        running = asyncio.create_task(runtime.run_specialist(SpecialistRole.TAXONOMY))
        await asyncio.wait_for(started.wait(), timeout=3)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    asyncio.run(cancel_tree())
    assert store.budget(scope)["settled_micro_usd"] == 3
    assert store.budget(scope)["held_micro_usd"] == 10


def test_complete_tree_trace_readback_has_true_effect_and_child_metadata(tmp_path, capfire):
    runtime, *_ = harness(tmp_path, delegate=SpecialistRole.GEOGRAPHY)
    result = asyncio.run(runtime.run_specialist(SpecialistRole.TAXONOMY))
    spans = capfire.exporter.exported_spans_as_dict()
    model_spans = [item for item in spans if item["name"] == "research_harness.model"]
    assert len(model_spans) == 4
    observed = {item["attributes"]["research.effect_id"] for item in model_spans}
    assert observed == set(result.model_effect_ids)
    assert {item["attributes"]["research.role"] for item in model_spans} == {
        "specimen_taxonomy", "specimen_geography",
    }
    assert all(item["attributes"]["research.attempt_id"] for item in model_spans)
    exported = json.dumps(spans, default=str)
    assert "private_label_canary" not in exported
    assert "Owned fields:" not in exported
    assert "model_request_parameters" not in exported


def test_registered_real_gateway_cannot_use_offline_allowance(tmp_path, monkeypatch):
    store, scope, lease, broker = sql_broker(tmp_path)
    request = requests()[SpecialistRole.TAXONOMY]
    real_model = HuggingFaceModelGateway(token="synthetic-no-live-access").model_for("harness-deepseek")

    async def forbidden(*_):
        pytest.fail("Real provider was dispatched under an unqualified allowance")

    monkeypatch.setattr(real_model, "request", forbidden)
    observed = []
    def inert_serialization_probe(messages, parameters, settings):
        # This observes serialized input only; it supplies no price, token bound
        # or live authority. The actual broker must still refuse this allowance.
        observed.append((messages,parameters,settings))
        return {"contract_version":"synthetic-no-liability-authority/v1"}
    gated = model(real_model, request=request, broker=broker, scope=scope, lease=lease,
        request_guard=inert_serialization_probe)
    assert gated.execution_class == "live"
    with pytest.raises(PermissionError, match="research_live_authority_required|program HOLD"):
        Agent(gated).run_sync("Synthetic offline admission test")
    assert len(observed) == 1 and observed[0][0]
    assert store._read(scope).state["effects"] == {}
    assert store.budget(scope)["settled_micro_usd"] == store.budget(scope)["held_micro_usd"] == 0


def test_official_managed_prompt_resolution_captured_once_before_effect(tmp_path, capfire):
    store, scope, lease, broker = sql_broker(tmp_path)
    request = requests()[SpecialistRole.TAXONOMY]
    captured = []

    class CaptureDuringCreation(ManagedPrompt):
        async def wrap_run(self, ctx, *, handler):
            async def before_dispatch():
                captured.append(capture_managed_prompt_pin(
                    request.prompt, self, {request.prompt.digest: request.prompt.version}))
                return await handler()
            return await super().wrap_run(ctx, handler=before_dispatch)

    capability = CaptureDuringCreation(request.role.value, default=request.prompt.text, label="production")
    gated = model(FunctionModel(lambda *_: ModelResponse([TextPart("synthetic resolved prompt")],
                                                        usage=RequestUsage(input_tokens=3, output_tokens=2))),
                  request=request, broker=broker, scope=scope, lease=lease)
    from pydantic_ai.capabilities import Instrumentation
    from specimen_digitization.provider_privacy import private_instrumentation
    Agent(gated, capabilities=[capability, Instrumentation(settings=private_instrumentation())]).run_sync("Synthetic")
    assert len(captured) == 1
    assert captured[0].text == request.prompt.text
    assert captured[0].digest == request.prompt.digest
    assert capability.resolved is None
    assert store.budget(scope)["settled_micro_usd"] == 3
    assert "Owned fields:" not in json.dumps(capfire.exporter.exported_spans_as_dict(), default=str)


def test_real_gateway_missing_liability_guard_refuses_construction(tmp_path,monkeypatch):
    store,scope,lease,broker = sql_broker(tmp_path)
    request = requests()[SpecialistRole.TAXONOMY]
    real_model = HuggingFaceModelGateway(token="synthetic-no-live-access").model_for("harness-deepseek")
    async def forbidden(*_):
        pytest.fail("Missing-guard real provider was dispatched")
    monkeypatch.setattr(real_model,"request",forbidden)
    with pytest.raises(ModelGatewayBlocked,match="^live_request_liability_guard_missing$"):
        model(real_model,request=request,broker=broker,scope=scope,lease=lease)
    assert store._read(scope).state["effects"] == {}
    assert store.budget(scope)["held_micro_usd"] == store.budget(scope)["settled_micro_usd"] == 0


@pytest.mark.parametrize(("mode", "content"), [("approved-content", True), ("metadata", False), (None, False)])
def test_harness_agents_record_content_only_under_approved_content(tmp_path, monkeypatch, mode, content):
    from pydantic_ai.capabilities import Instrumentation
    from specimen_digitization import observability

    monkeypatch.setattr(observability, "_configured_settings", None if mode is None else
        observability.ObservabilitySettings(environment="test", service_name="specimen-worker",
            capture_mode=observability.CaptureMode(mode), head_sample_rate=1.0,
            distributed_tracing=False))
    runtime, *_ = harness(tmp_path)
    for agent in runtime.agents.values():
        instrumentation = next(item for item in agent.root_capability.capabilities
            if isinstance(item, Instrumentation))
        assert instrumentation.settings.include_content is content
        assert instrumentation.settings.include_binary_content is False
