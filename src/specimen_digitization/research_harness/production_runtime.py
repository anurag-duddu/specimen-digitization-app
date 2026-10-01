"""Registered production research runtime; no synthetic fallback or budget creation."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from specimen_digitization.application.domain import Principal
from .contracts import CollectionProfile, SpecialistRequest, SpecialistRole
from .discovery_v2 import ResearchDiscoveryV2
from .gateway import ModelBinding
from .journal import DurableResearchJournal
from .native_service import SqlConnectNativeCanonicalServiceV2
from .persistence import (DurableEffectBroker, GcsImmutableBlobs, HeldUnknown, ResearchStore,
    SqlConnectStateBackend, StaleWork, DurabilityScope, Lease)
from .runtime import build_research_engine
from .sources import BoundedHTTPTransport
from .registered_pins import (registered_registry, registered_capture_policies,
    registered_model_prices, registered_model_request_guards)


@dataclass(frozen=True)
class NativeResearchRuntime:
    principal: Principal
    binding: object
    store: ResearchStore
    scope: object
    lease: object
    journal: DurableResearchJournal
    engine: object
    canonical_service: SqlConnectNativeCanonicalServiceV2
    blobs: object


class NativeResearchRuntimeFactory:
    """Compose the actual repository, immutable inputs and genuine Harness.

    Pure construction creates no program, prompts, lease, allowance or effect.
    Source readiness, capture retention and numeric prices come only from the
    exact retained generation. Missing authority closes before dispatch.
    """
    def __init__(self, repository, *, verify_access, registry=None, request_factory=None,
                 materializer=None, evidence_provider=None, projection_services=None,
                 actual_cost=None, blobs=None, limits=None):
        self.repository, self.registry = repository, registry
        self.request_factory = request_factory
        # Retained optional services are only for immutable receipt reads. New
        # publication services are constructed from the registered binding.
        self.materializer, self.evidence_provider = materializer, evidence_provider
        self.projection_services, self.verify_access = projection_services, verify_access
        self.limits = limits
        self.blobs = blobs or GcsImmutableBlobs(repository.graph_blobs.bucket)
        self.discovery = ResearchDiscoveryV2(repository, verify_access=verify_access)

    def _receipt_service(self, principal, original_scope, program_key):
        scope = DurabilityScope(**{key:getattr(original_scope,key) for key in
            ("organization_id", "collection_id", "specimen_id", "job_id", "generation")},
            actor_uid=principal.user_id, sensitive=original_scope.sensitive)
        store = ResearchStore(SqlConnectStateBackend(self.repository), program_key)
        journal = DurableResearchJournal(store, scope, Lease(scope.key,"receipt-read-only",0,scope.generation,0), self.blobs)
        return SqlConnectNativeCanonicalServiceV2(self.repository, journal, blobs=self.blobs,
            materializer=self.materializer, evidence_provider=self.evidence_provider,
            projection_services=self.projection_services)

    async def retained_publication_locators(self, principal, specimen_id):
        # Authenticated immutable intents only: no current binding/job/lease or
        # mutable graph is consulted merely to recover winning receipts.
        principal = Principal.model_validate(principal.model_dump(mode="json"))
        service = SqlConnectNativeCanonicalServiceV2(self.repository, None, blobs=self.blobs,
            materializer=None, evidence_provider=None, projection_services=None)
        return await service.list_retained_publication_locators(principal, specimen_id)

    async def winning_receipt(self, principal, specimen_id, operation):
        principal = Principal.model_validate(principal.model_dump(mode="json"))
        original = operation.original_scope
        if (original.specimen_id != specimen_id
            or original.organization_id != principal.scope.organization_id
            or original.collection_id != principal.scope.collection_id):
            raise PermissionError("research_resume_scope_denied")
        service = self._receipt_service(principal, original, operation.program_key)
        return await service.winning_receipt(principal, specimen_id,
            idempotency_key=operation.idempotency_key,
            request_identity_digest=operation.request_identity_digest)

    async def open(self, principal, specimen_id, *, owner, ttl_seconds=300):
        principal = Principal.model_validate(principal.model_dump(mode="json"))
        if principal.role not in {"operator", "reviewer", "manager", "admin"}:
            raise PermissionError("research_worker_access_denied")
        binding = await self.discovery.binding(principal, specimen_id)
        scope = binding.durability_scope(principal)
        store = ResearchStore(SqlConnectStateBackend(self.repository), binding.program_key)
        await asyncio.to_thread(store.require_live_authority, scope)
        document = await asyncio.to_thread(store._read, scope)
        job = store._job(document.state, scope)
        binding.validate_job(job, program_key=store.program_key)
        policy = document.state["budget_policy"]
        if (type(policy.get("ceiling_micro_usd")) is not int
            or not 0 < policy["ceiling_micro_usd"] <= 12_000_000
            or policy.get("live_authorized") is not True or policy.get("hold_reason") is not None
            or document.state.get("halted") is not False or job["paused"]):
            raise HeldUnknown("research_live_admission_unqualified")
        budget = await asyncio.to_thread(store.budget, scope)
        if budget["remaining_micro_usd"] <= 0:
            raise HeldUnknown("research_program_headroom_unavailable")
        source_pins = job["pins"]["sources"]
        registry = registered_registry(source_pins)
        if self.registry is not None and registry.digest != self.registry.digest:
            raise StaleWork("research_source_registry_pin_changed")
        capture_policies = registered_capture_policies(source_pins, registry)
        from .accepted_output import validation_boundary_pins, VALIDATOR_VERSION, VALIDATOR_SOURCE_SHA256
        boundary = {"contract_version":"research-acceptance-boundary/v1",
            "validator_version":VALIDATOR_VERSION, "validator_source_sha256":VALIDATOR_SOURCE_SHA256,
            **validation_boundary_pins()}
        if source_pins.get("acceptance_boundary") != boundary:
            raise HeldUnknown("research_registered_acceptance_boundary_missing")
        from .initial_requests import NativeGenerationRequestFactory
        request_factory = self.request_factory or NativeGenerationRequestFactory(
            self.repository, verify_access=self.verify_access, registry=registry)
        raw_requests = await request_factory(principal, binding, job)
        requests = {SpecialistRole(role):SpecialistRequest.model_validate(
            request.model_dump(mode="json")) for role,request in raw_requests.items()}
        if not requests or any(request.scope != binding.research_scope() for request in requests.values()):
            raise StaleWork("research_original_request_scope_unproved")
        profile = CollectionProfile.model_validate(job["pins"]["profile"])
        bindings = {}
        for role in requests:
            data = dict(job["pins"]["model"][str(role)])
            route = data.pop("route")
            model = ModelBinding(**data)
            if model.route_id != route or requests[role].prompt.model_dump(mode="json") != job["pins"]["prompts"][str(role)]:
                raise StaleWork("research_model_or_prompt_pin_changed")
            bindings[role] = model
        prices = registered_model_prices(source_pins, bindings)
        request_guards = registered_model_request_guards(source_pins, bindings)
        from .canonical_materialization_v2 import ResearchCanonicalPolicyV2
        from .native_materialization_services_v2 import build_native_materialization_services_v2
        from .canonical_evidence_provider_v2 import build_captured_research_services_v2
        from specimen_digitization.model_gateway import HuggingFaceModelGateway
        effects = DurableEffectBroker(store, self.blobs)
        scientific_policy = ResearchCanonicalPolicyV2.from_registered_binding(binding)
        services = build_native_materialization_services_v2(
            self.repository, effects, registry, scientific_policy, request_factory)
        gateway = HuggingFaceModelGateway(timeout_seconds=120)
        lease = await asyncio.to_thread(store.claim, scope, owner, ttl_seconds=ttl_seconds)
        tools, _ = build_captured_research_services_v2(repository=self.repository,
            effect_broker=effects, scope=scope, lease=lease, registry=registry,
            policies=capture_policies, transport=BoundedHTTPTransport(), execution_class="live")
        engine = build_research_engine(profile=profile, requests=requests,
            store=store, scope=scope, lease=lease, blobs=self.blobs, tool_broker=tools,
            bindings=bindings, settings=job["pins"]["settings"], source_pins=source_pins,
            base_model_factory=lambda request:gateway.model_for(bindings[request.role].route_id),
            actual_cost=prices, request_guard=request_guards, limits=self.limits, max_concurrency=1)
        service = SqlConnectNativeCanonicalServiceV2(self.repository, engine.journal, blobs=self.blobs,
            materializer=services.materializer, evidence_provider=services.evidence_provider,
            projection_services=services.projection_services)
        return NativeResearchRuntime(principal, binding, store, scope, lease, engine.journal, engine, service, self.blobs)
