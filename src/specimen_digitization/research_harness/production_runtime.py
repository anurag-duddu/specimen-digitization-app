"""Registered production research runtime; no synthetic fallback or budget creation."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from uuid import UUID

from specimen_digitization.application.domain import Principal
from specimen_digitization.application.storage import digest as canonical_digest
from .committed_pins import build_committed_pins, committed_run_cost_limit_micros
from .contracts import CollectionProfile, SpecialistRequest, SpecialistRole
from .discovery_v2 import ResearchDiscoveryV2
from .gateway import ModelBinding
from .journal import DurableResearchJournal
from .native_service import SqlConnectNativeCanonicalServiceV2
from .persistence import (BudgetPolicy, DurableEffectBroker, GcsImmutableBlobs, HeldUnknown,
    MAX_LEASE_TTL_SECONDS, PinnedRuntime, ResearchStore, SqlConnectStateBackend, StaleWork,
    DurabilityScope, Lease)
from . import role_windows
from .runtime import build_research_engine
from .sources import BoundedHTTPTransport, FixtureSourceTransport
from .registered_pins import (registered_registry, registered_capture_policies,
    registered_model_prices, registered_model_request_guards)

WORKER_ROLES = {"operator", "reviewer", "manager", "admin"}


def research_program_key(run_id: str) -> str:
    """One research state document per run, so its budget is the run's own."""
    return "research-run:" + str(UUID(str(run_id)))


def research_budget_policy(profile) -> BudgetPolicy:
    """The run's research allowance: the profile's run cost limit, live."""
    return BudgetPolicy(committed_run_cost_limit_micros(profile), live_authorized=True, hold_reason=None)


def committed_job_pins(profile, *, organization_id: str, collection_id: str, input_digest: str) -> dict:
    """The job pins committed config gives this run; input_digest is the base snapshot."""
    pins = dict(build_committed_pins(profile, organization_id=organization_id,
        collection_id=collection_id))
    return PinnedRuntime(**{**pins, "input_digest": input_digest}).payload()


def _gateway_models():
    from specimen_digitization.model_gateway import HuggingFaceModelGateway
    gateway = HuggingFaceModelGateway(timeout_seconds=120)
    return lambda request, binding: gateway.model_for(binding.route_id)


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
    # Specialists this window runs at once: the engine's concurrency and the number
    # of roles a worker hands it per lease (role_windows.ROLE_CONCURRENCY).
    role_window: int = 1


class NativeResearchRuntimeFactory:
    """Compose the actual repository, immutable inputs and genuine Harness.

    Pure construction creates no program, prompts, lease, allowance or effect.
    Pins, source readiness, capture retention and prices are the committed
    ones for the run's profile. ``authorize`` builds the live authority at each
    open; without it the store refuses before any dispatch. The state backend,
    model factory and source transport default to production; the execution
    class follows from the transport's type and is never chosen by a caller.
    """
    def __init__(self, repository, *, verify_access, authorize=None, state_backend=None,
                 model_factory=None, source_transport=None, registry=None, request_factory=None,
                 materializer=None, evidence_provider=None, projection_services=None,
                 blobs=None, limits=None):
        self.repository, self.registry = repository, registry
        self.request_factory = request_factory
        # Retained optional services are only for immutable receipt reads. New
        # publication services are constructed from the registered binding.
        self.materializer, self.evidence_provider = materializer, evidence_provider
        self.projection_services, self.verify_access = projection_services, verify_access
        self.authorize, self.state_backend = authorize, state_backend
        self.model_factory, self.source_transport = model_factory, source_transport
        self.limits = limits
        self.blobs = blobs or GcsImmutableBlobs(repository.graph_blobs.bucket)
        self.discovery = ResearchDiscoveryV2(repository, verify_access=verify_access)

    def _backend(self):
        return self.state_backend if self.state_backend is not None else SqlConnectStateBackend(self.repository)

    def _receipt_service(self, principal, original_scope, program_key):
        scope = DurabilityScope(**{key:getattr(original_scope,key) for key in
            ("organization_id", "collection_id", "specimen_id", "job_id", "generation")},
            actor_uid=principal.user_id, sensitive=original_scope.sensitive)
        store = ResearchStore(self._backend(), program_key)
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

    async def open(self, principal, specimen_id, *, owner, ttl_seconds=MAX_LEASE_TTL_SECONDS):
        principal = Principal.model_validate(principal.model_dump(mode="json"))
        if principal.role not in WORKER_ROLES:
            raise PermissionError("research_worker_access_denied")
        binding = await self.discovery.binding(principal, specimen_id)
        scope = binding.durability_scope(principal)
        specimen = await asyncio.to_thread(self.repository.get, principal.scope, specimen_id)
        authority = None if self.authorize is None else await self.authorize(principal, specimen, binding)
        program_key = research_program_key(binding.base_canonical.canonical_run_id)
        if binding.program_key != program_key:
            raise StaleWork("research_program_key_unproved")
        store = ResearchStore(self._backend(), program_key, live_authority=authority)
        store.require_live_authority(scope)
        document = await asyncio.to_thread(store._read, scope)
        job = store._job(document.state, scope)
        binding.validate_job(job, program_key=store.program_key)
        profile_snapshot = specimen.run.profile_snapshot
        if (specimen.run.id != str(binding.base_canonical.canonical_run_id)
            or canonical_digest(profile_snapshot) != binding.canonical_profile_digest):
            raise StaleWork("research_run_profile_unproved")
        # The job keeps the pins committed config gave it at provisioning; a
        # change in config or installed code since then holds the run.
        try:
            committed = committed_job_pins(profile_snapshot, organization_id=scope.organization_id,
                collection_id=scope.collection_id, input_digest=binding.base_canonical.snapshot_sha256)
            policy = asdict(research_budget_policy(profile_snapshot))
        except (TypeError, ValueError):
            raise HeldUnknown("research_committed_pins_unavailable") from None
        if job["pins"] != committed:
            raise HeldUnknown("research_committed_pins_changed")
        if (document.state["budget_policy"] != policy
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
        effects = DurableEffectBroker(store, self.blobs)
        scientific_policy = ResearchCanonicalPolicyV2.from_registered_binding(binding)
        services = build_native_materialization_services_v2(
            self.repository, effects, registry, scientific_policy, request_factory)
        model_factory = self.model_factory or _gateway_models()
        transport = self.source_transport if self.source_transport is not None else BoundedHTTPTransport()
        execution_class = "offline" if type(transport) is FixtureSourceTransport else "live"
        lease = await asyncio.to_thread(store.claim, scope, owner, ttl_seconds=ttl_seconds)
        tools, _ = build_captured_research_services_v2(repository=self.repository,
            effect_broker=effects, scope=scope, lease=lease, registry=registry,
            policies=capture_policies, transport=transport, execution_class=execution_class)
        window = role_windows.window_size(budget["remaining_micro_usd"],
            max(binding.reservation_micro_usd for binding in bindings.values()))
        engine = build_research_engine(profile=profile, requests=requests,
            store=store, scope=scope, lease=lease, blobs=self.blobs, tool_broker=tools,
            bindings=bindings, settings=job["pins"]["settings"], source_pins=source_pins,
            base_model_factory=lambda request:model_factory(request, bindings[request.role]),
            actual_cost=prices, request_guard=request_guards, limits=self.limits, max_concurrency=window)
        service = SqlConnectNativeCanonicalServiceV2(self.repository, engine.journal, blobs=self.blobs,
            materializer=services.materializer, evidence_provider=services.evidence_provider,
            projection_services=services.projection_services)
        return NativeResearchRuntime(principal, binding, store, scope, lease, engine.journal, engine, service,
            self.blobs, window)
