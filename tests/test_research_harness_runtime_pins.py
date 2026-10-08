"""Actual offline Harness requests must use the runtime bindings admitted earlier."""
import asyncio
from dataclasses import asdict, replace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.research_harness.agents import SpecialistOutput, specialist_output_schema_digest
from specimen_digitization.research_harness.contracts import ALL_FIELDS, SpecialistRole
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, ImmutableFileBlobs, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.runtime import build_research_engine, runtime_pins
from test_research_harness_boundaries import admitted, waiting


def actual_offline_engine(tmp_path, *, serialization_version=None):
    profile, scope, all_requests, _, _ = admitted(tmp_path)
    original = all_requests[SpecialistRole.TAXONOMY]
    request = original.model_copy(update={"prompt":original.prompt.model_copy(update={
        "output_schema_digest":specialist_output_schema_digest()})})
    requests = {request.role:request}
    bindings = {request.role:ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 10, "admitted-price-v1")}
    settings = {"max_tokens":128, "temperature":0.1}
    durable = DurabilityScope(scope.organization_id, scope.collection_id,
        scope.specimen_id, scope.job_id, scope.generation, "review-actor", False)
    backend = SqliteStateBackend(tmp_path / "actual-offline-runtime.sqlite")
    backend.grant(durable)
    store = ResearchStore(backend, "same-offline-runtime-program")
    store.initialize(durable, BudgetPolicy(100))
    pins = runtime_pins(profile, requests,
        model={role:{"route":binding.route_id, **asdict(binding)} for role,binding in bindings.items()},
        settings=settings)
    if serialization_version is not None:
        pins = replace(pins, serialization_version=serialization_version)
    store.create_job(durable, pins, list(ALL_FIELDS))
    lease = store.claim(durable, "runtime-review-worker", ttl_seconds=120)
    observed = []

    class NoSourceCalls:
        async def query_source(self, *_):
            raise AssertionError("Fixture should make no source call")
        async def invoke_utility(self, *_):
            raise AssertionError("Fixture should make no utility call")

    def base_model(request):
        def respond(_messages, info):
            observed.append(dict(info.model_settings))
            output = SpecialistOutput(role=request.role,
                resolutions=tuple(waiting(key) for key in request.field_keys))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="synthetic-final")],
                usage=RequestUsage(input_tokens=1, output_tokens=1))
        return FunctionModel(respond)

    engine = build_research_engine(profile=profile, requests=requests,
        store=store, scope=durable, lease=lease,
        blobs=ImmutableFileBlobs(tmp_path / "actual-offline-blobs"),
        tool_broker=NoSourceCalls(), bindings=bindings, settings=settings,
        base_model_factory=base_model, actual_cost=lambda _response:0)
    return engine, store, durable, bindings, settings, observed


@pytest.mark.parametrize("serialization_version", [
    "harness-0.36.0/core-2.51.0",
    "pydantic-ai-2.51.0+harness-0.36.0/v1",
])
def test_previous_runtime_serialization_requires_new_generation_admission(tmp_path, serialization_version):
    with pytest.raises(StaleWork, match="runtime_factory_binding_differs_from_persisted_generation"):
        actual_offline_engine(tmp_path, serialization_version=serialization_version)


def test_settings_are_snapshotted_at_runtime_admission(tmp_path):
    engine, store, durable, _, settings, observed = actual_offline_engine(tmp_path)
    settings["temperature"] = 0.9
    result = asyncio.run(engine.run())
    assert len(result.checkpoints) == 1
    assert store.job(durable)["pins"]["settings"]["temperature"] == 0.1
    assert observed == [{"max_tokens":128, "temperature":0.1}]


def test_model_reservation_binding_is_snapshotted_at_runtime_admission(tmp_path):
    engine, store, durable, bindings, _, _ = actual_offline_engine(tmp_path)
    bindings[SpecialistRole.TAXONOMY] = replace(bindings[SpecialistRole.TAXONOMY],
        reservation_micro_usd=1, price_version="changed-after-admission")
    result = asyncio.run(engine.run())
    assert len(result.checkpoints) == 1
    assert store.job(durable)["pins"]["model"][str(SpecialistRole.TAXONOMY)]["reservation_micro_usd"] == 10
    effects = list(store._read(durable).state["effects"].values())
    assert len(effects) == 1
    assert effects[0]["reservation_micro_usd"] == 10
