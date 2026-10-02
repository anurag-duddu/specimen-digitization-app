"""Causal V2 discovery over the authenticated ordinary repository.

V1 remains unchanged. No job, allowance, lease or model is created by a GET.
"""
from __future__ import annotations

import asyncio

from .canonical_binding import (
    CanonicalIdentity, CanonicalResearchBinding, ScopedReadBundle,
)
from typing import Literal

from .contracts import FieldKey, FrozenRecord, ResearchScope
from .discovery import (
    DiscoveryCapabilities, ResearchDiscovery, ScopedCanonicalReadStore,
)
from .persistence import ResearchStore, SqlConnectStateBackend, StaleWork, HeldUnknown
from .service import ResearchService


class CanonicalReadBindingV2:
    """Read facade whose immutable base/current ancestry was proved by V2."""
    def __init__(self, native):
        from .native_canonical_v2 import CanonicalBindingV2
        self.native = CanonicalBindingV2.model_validate(native.model_dump(mode="json"))
        self.registration = self.native.registration
        self.read_bundle = ScopedReadBundle.model_validate(self.registration.read_bundle)
        self.canonical = CanonicalIdentity.model_validate({
            **self.native.canonical.model_dump(mode="json"),
            "organization_id":str(self.native.organization_id),
            "collection_id":str(self.native.collection_id),
            "specimen_id":str(self.native.specimen_id), "sensitive":self.native.sensitive,
        })
        self.validate_scoped_rows()
        self.validate_job(self.job, program_key=self.program_key)

    def __getattr__(self, name):
        return getattr(self.registration, name)

    @property
    def research_locks(self):
        return tuple(key for key in FieldKey if self.human_locks[self.field_mapping[key]])

    def durability_identity(self):
        return CanonicalResearchBinding.durability_identity(self)

    def accepts_effect_scope(self, scope, binding_digest):
        return CanonicalResearchBinding.accepts_effect_scope(self, scope, binding_digest)

    def validate_scoped_rows(self):
        return CanonicalResearchBinding.validate_scoped_rows(self)

    def validate_job(self, job, *, program_key):
        return CanonicalResearchBinding.validate_job(self, job, program_key=program_key)

    def durability_scope(self, principal):
        return CanonicalResearchBinding.durability_scope(self, principal)

    def research_scope(self):
        return CanonicalResearchBinding.research_scope(self)

    def stable_snapshot(self):
        value = self.native.model_dump(mode="json")
        value["registration"]["read_bundle"].pop("server_time")
        return value

    def same_snapshot(self, other):
        return isinstance(other, CanonicalReadBindingV2) and self.stable_snapshot() == other.stable_snapshot()


class ResearchDiscoveryResultV2(FrozenRecord):
    contract_version: Literal["canonical-binding/v2"] = "canonical-binding/v2"
    canonical: CanonicalIdentity
    scope: ResearchScope
    human_locked_fields: tuple[FieldKey, ...]
    capabilities: DiscoveryCapabilities
    retry_blocked_reason: str | None = None
    review_blocked_reason: str = "use_canonical_review_endpoint"


class ResearchDiscoveryV2(ResearchDiscovery):
    def __init__(self, repository, *, verify_access, worker_dispatcher=None):
        self.native_repository = repository
        self.worker_dispatcher = worker_dispatcher
        super().__init__(repository, store_factory=lambda binding: ScopedCanonicalReadStore(
            binding, verified_actor=self._actor()), verify_access=verify_access)

    @staticmethod
    def _actor():
        from specimen_digitization.application.production import actor_uid
        return actor_uid.get()

    async def binding(self, principal, specimen_id):
        from .native_canonical import SqlConnectNativeOperationClient
        from .native_canonical_v2 import CanonicalBindingV2
        from specimen_digitization.application.domain import Principal
        principal = Principal.model_validate(principal.model_dump(mode="json"))
        variables = dict(self.native_repository.variables(principal.scope), specimenId=specimen_id)
        if variables.get("actorUid") != principal.user_id:
            raise PermissionError("research_access_denied")
        data = await asyncio.to_thread(self.native_repository.execute,
            "GetCanonicalResearchBindingV2", variables)
        SqlConnectNativeOperationClient._access_data(data, "GetCanonicalResearchBindingV1")
        binding = CanonicalReadBindingV2(CanonicalBindingV2.from_native(
            principal.scope, specimen_id, data["binding"]))
        binding.durability_scope(principal)
        await self.verify_access(principal, binding.canonical.sensitive)
        return binding

    def mutable_store(self, binding):
        # Uses the existing owner-installed shared program, never initialize().
        return ResearchStore(SqlConnectStateBackend(self.native_repository), binding.program_key)

    async def retry_available(self, principal, scope, field_key):
        binding = await self.binding(principal, scope.specimen_id)
        if (binding.research_scope() != scope or self.worker_dispatcher is None
            or principal.role not in {"operator", "reviewer", "manager", "admin"}
            or field_key in binding.research_locks):
            return False
        store = self.mutable_store(binding)
        bound = binding.durability_scope(principal)
        try:
            await asyncio.to_thread(store.require_live_authority, bound)
        except (PermissionError, HeldUnknown):
            return False
        document = await asyncio.to_thread(store._read, bound)
        job = store._job(document.state, bound)
        binding.validate_job(job, program_key=store.program_key)
        policy = document.state.get("budget_policy", {})
        if (job["paused"] or job["fields"][str(field_key)]["locked"]
            or document.state.get("halted") is not False
            or policy.get("live_authorized") is not True or policy.get("hold_reason") is not None):
            return False
        try:
            budget = await asyncio.to_thread(store.budget, bound)
        except HeldUnknown:
            return False
        return budget["remaining_micro_usd"] > 0

    async def discover(self, principal, specimen_id):
        binding, _, _, _, job = await self.bound_state(principal, specimen_id)
        if not binding.same_snapshot(await self.binding(principal, specimen_id)):
            raise StaleWork("research_state_changed")
        eligible = tuple(key for key in FieldKey if not job["fields"][str(key)]["locked"])
        available = bool(eligible) and await self.retry_available(principal, binding.research_scope(), eligible[0])
        return ResearchDiscoveryResultV2(canonical=binding.canonical, scope=binding.research_scope(),
            human_locked_fields=binding.research_locks,
            capabilities=DiscoveryCapabilities(read=True, retry=available, review=False),
            retry_blocked_reason=None if available else "retry_admission_unavailable")

    async def service(self, principal, locator):
        binding = await self.binding(principal, locator.specimen_id)
        if (binding.job_id, binding.generation) != (locator.job_id, locator.generation):
            raise StaleWork("research_state_changed")
        return ResearchService(store=self.mutable_store(binding), resolve_scope=self.resolve,
            retry_admission=self.mutable_store(binding).admit_retry,
            retry_available=self.retry_available, canonical_binding=self.binding,
            retry_queued=self.dispatch_retry)

    async def dispatch_retry(self, principal, scope, command_id):
        binding = await self.binding(principal, scope.specimen_id)
        if binding.research_scope() != scope or self.worker_dispatcher is None:
            raise StaleWork("research_retry_dispatch_unavailable")
        store = self.mutable_store(binding)
        bound = binding.durability_scope(principal)
        def claim(state, now):
            job = store._job(state, bound)
            binding.validate_job(job, program_key=store.program_key)
            command = store._retry_command(state, bound, command_id)
            if command["status"] != "queued":
                return False
            if command.get("dispatch_status") in {"sending", "requested", "unknown"}:
                return False
            command["dispatch_status"] = "sending"
            return True
        if not await asyncio.to_thread(store._mutate, bound, claim):
            return
        interrupted = None
        try:
            outcome = await asyncio.to_thread(self.worker_dispatcher.start)
        except BaseException as error:
            outcome = None
            interrupted = error
        def settle(state, now):
            command = store._retry_command(state, bound, command_id)
            if command.get("dispatch_status") != "sending":
                raise StaleWork("research_dispatch_receipt_changed")
            command["dispatch_status"] = "requested" if outcome is not None and outcome.status == "requested" else "unknown"
        await asyncio.to_thread(store._mutate, bound, settle)
        if interrupted is not None:
            raise interrupted
        if outcome is None or outcome.status != "requested":
            raise HeldUnknown("research_worker_start_unknown")
