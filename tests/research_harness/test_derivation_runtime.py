"""A human-command runtime composes capture authority without a model engine."""
import asyncio
from types import SimpleNamespace

import pytest

from specimen_digitization.research_harness import production_runtime as module
from specimen_digitization.research_harness import canonical_evidence_provider_v2 as captures
from specimen_digitization.research_harness.contracts import SpecialistRole
from specimen_digitization.research_harness.persistence import HeldUnknown
from specimen_digitization.research_harness.program_budget import ProgramEffectBroker

import test_production_e2e as e2e
from test_production_e2e import rig, no_network  # noqa: F401


def test_command_runtime_retains_registered_inputs_and_guarded_capture_but_no_models(rig, monkeypatch):
    workflow = e2e.compose(rig, geolocate=False)
    parsed = e2e.to_plan(workflow, rig)
    asyncio.run(workflow.provision(rig.principal, parsed))
    factory = workflow.native_worker.runtime_factory
    def forbidden(*args, **kwargs):
        pytest.fail("a human derivation constructed a model")
    factory.model_factory = forbidden
    monkeypatch.setattr(module, "_gateway_models", forbidden)
    monkeypatch.setattr(module, "build_research_engine", forbidden)
    adapter, broker = object(), object()
    monkeypatch.setattr(module, "_georeferencing_adapter", lambda repository: adapter)
    original_registry = module.registered_registry
    def with_local_adapter(pins):
        registry = original_registry(pins)
        # This fixture changes only capability detection after normal pin
        # verification; the Geo integration owns the actual registry entry.
        if not any(policy.id == "georeference_history" for policy in registry.policies):
            registry._policies += (SimpleNamespace(id="georeference_history"),)
        return registry
    monkeypatch.setattr(module, "registered_registry", with_local_adapter)
    constructed = []
    def captured(**kwargs):
        constructed.append(kwargs)
        assert kwargs["georeferencing_adapter"] is adapter
        assert kwargs["derivation_context"] is trusted_context
        assert isinstance(kwargs["effect_broker"], ProgramEffectBroker)
        assert kwargs["effect_broker"].binding_guard is not None
        assert kwargs["effect_broker"].send_authorization("live") is not None
        return broker, None
    monkeypatch.setattr(captures, "build_captured_research_services_v2", captured)
    trusted_context = object()  # Production caller supplies its verified command.
    with e2e.supervised():
        runtime = asyncio.run(factory.open(rig.principal, rig.specimen_id,
            owner="offline-derivation", derivation_context=trusted_context))
    services = runtime.derivation_services
    assert services.broker is broker and services.adapter is adapter and services.context is trusted_context
    assert set(services.requests) == set(SpecialistRole)
    assert len(constructed) == 1 and runtime.role_window == 0 and not runtime.publication_only
    with pytest.raises(TypeError):
        services.requests[SpecialistRole.GEOGRAPHY] = None
    with pytest.raises(HeldUnknown, match="research_derivation_model_dispatch_forbidden"):
        asyncio.run(runtime.engine.run())
    assert rig.model_calls == [] and rig.source_urls == []
    assert runtime.store._read(runtime.scope).state["effects"] == {}
