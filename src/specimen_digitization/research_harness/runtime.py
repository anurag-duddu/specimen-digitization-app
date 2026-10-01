"""Construct immutable generation bindings from the actual configured inputs."""

from collections.abc import Mapping
from dataclasses import asdict
import json

from .contracts import CollectionProfile, SpecialistRequest, SpecialistRole, digest
from .persistence import PinnedRuntime


def runtime_pins(
    profile: CollectionProfile,
    requests: Mapping[SpecialistRole, SpecialistRequest],
    *, model: Mapping[SpecialistRole, Mapping], settings: Mapping, source_pins: Mapping | None = None,
) -> PinnedRuntime:
    if not requests or set(requests) != set(model):
        raise ValueError("runtime_requires_explicit_matching_model_bindings")
    first = next(iter(requests.values()))
    for role, request in requests.items():
        if (
            request.scope != first.scope or request.role != role
            or request.scope.profile_digest != digest(profile)
            or request.prompt.source_registry_digest != first.prompt.source_registry_digest
            or model[role].get("route") != request.prompt.model_route
        ):
            raise ValueError("runtime_binding_mismatch")
    sources = json.loads(json.dumps(dict(source_pins or {"registry_digest":first.prompt.source_registry_digest}),
        ensure_ascii=False, allow_nan=False))
    if sources.get("registry_digest") != first.prompt.source_registry_digest:
        raise ValueError("source_registry_binding_mismatch")
    return PinnedRuntime(
        input_digest=first.scope.input_digest, profile=profile.model_dump(mode="json"),
        prompts={str(role):request.prompt.model_dump(mode="json") for role,request in requests.items()},
        sources=sources,
        model={str(role):dict(binding) for role,binding in model.items()},
        settings=dict(settings), engine_version="research_harness_v1",
    )


def build_research_engine(
    *, profile: CollectionProfile, requests: Mapping[SpecialistRole, SpecialistRequest],
    store, scope, lease, blobs, tool_broker, bindings: Mapping, settings: Mapping,
    base_model_factory, actual_cost=None, request_guard=None, limits=None, max_concurrency: int = 1, source_pins=None,
):
    """Wire the production interfaces without creating or resetting an allowance.

    Admission creates the scoped job from ``runtime_pins`` beforehand. This
    factory requires that exact persisted job, a fenced lease, qualified tools,
    and explicit model factories; it performs no credential discovery or live
    execution during construction.
    """
    from .agents import HarnessLimits, SpecialistHarness, request_model_pins
    from .engine import ResearchEngine
    from .gateway import EffectModel, ModelBinding
    from .journal import DurableResearchJournal
    from .persistence import DurableEffectBroker, SqlConnectStepStore, StaleWork

    # Factories execute later; retain owned validated snapshots rather than
    # allowing the caller to change an admitted generation through aliases.
    settings = json.loads(json.dumps(dict(settings), ensure_ascii=False, allow_nan=False))
    bindings = {role:ModelBinding(**asdict(binding)) for role,binding in bindings.items()}
    model = {role:{"route":binding.route_id, **asdict(binding)} for role,binding in bindings.items()}
    pins = runtime_pins(profile, requests, model=model, settings=settings, source_pins=source_pins)
    if store.job(scope)["pins"] != pins.payload():
        raise StaleWork("runtime_factory_binding_differs_from_persisted_generation")
    journal = DurableResearchJournal(store, scope, lease, blobs)
    effects = DurableEffectBroker(store, blobs)

    def harness_factory(selected):
        def model_factory(request):
            return EffectModel(base_model_factory(request), broker=effects, scope=scope, lease=lease,
                role=str(request.role), binding=bindings[request.role],
                pins=request_model_pins(request), model_settings=settings,
                actual_cost=actual_cost.get(request.role) if isinstance(actual_cost, Mapping) else actual_cost,
                request_guard=request_guard.get(request.role) if isinstance(request_guard, Mapping) else request_guard)

        return SpecialistHarness(requests=selected, model_factory=model_factory,
            tool_broker=tool_broker,
            step_store_factory=lambda request:SqlConnectStepStore(store, scope, blobs,
                agent_name=str(request.role)), limits=limits or HarnessLimits())

    return ResearchEngine(profile=profile, requests=requests, journal=journal,
        harness_factory=harness_factory, model_settings_digest=digest(dict(settings)),
        max_concurrency=max_concurrency)
