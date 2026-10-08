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
from .persistence import ResearchStore, SqlConnectStateBackend, StaleWork, HeldUnknown, BudgetExceeded, Lease
from .journal import DurableResearchJournal
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
    def __init__(self, repository, *, verify_access, worker_dispatcher=None, worker_readiness=None):
        self.native_repository = repository
        self.worker_dispatcher = worker_dispatcher
        self.worker_readiness = worker_readiness
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

    def mutable_store(self, binding, *, authority=None):
        # Every caller uses the existing Run document. A read alone never
        # initializes an allowance, creates a job or starts a worker.
        return ResearchStore(SqlConnectStateBackend(self.native_repository), binding.program_key,
            live_authority=authority)

    def _current_specimen(self, principal, binding):
        from specimen_digitization.application.storage import digest as snapshot_digest
        specimen = self.native_repository.get(principal.scope, binding.canonical.specimen_id)
        from specimen_digitization.application.workflow import Workflow
        if (specimen.run.stage != "processing_blocked" or specimen.run.disposition is not None
            or specimen.run.human_approved or specimen.run.blocker == "external_outcome_unknown"
            or Workflow.next_step(specimen.run) != "plan"):
            raise StaleWork("research_retry_lifecycle_unavailable")
        info = self.native_repository.version_info(principal.scope, specimen.id, specimen.version)
        if (specimen.scope != principal.scope or specimen.id != binding.canonical.specimen_id
            or specimen.version != binding.canonical.record_revision
            or specimen.run.id != str(binding.base_canonical.canonical_run_id)
            or snapshot_digest(specimen.run.profile_snapshot) != binding.canonical_profile_digest
            or info.get("revision") != specimen.version or info.get("run_id") != specimen.run.id
            or info.get("sha256") != binding.canonical.snapshot_sha256):
            raise StaleWork("research_retry_current_run_changed")
        return specimen

    async def _authorized_store(self, principal, binding):
        from .workflow_bridge import authorize_live_research
        environment_reader = getattr(self.worker_readiness, "research_environment", None)
        if (self.worker_dispatcher is None or not callable(environment_reader)
            or principal.role not in {"operator", "reviewer", "manager", "admin"}):
            raise PermissionError("research_retry_unavailable")
        specimen = await asyncio.to_thread(self._current_specimen, principal, binding)
        environment = await asyncio.to_thread(environment_reader, principal, specimen)
        if environment is None:
            raise PermissionError("research_retry_worker_unavailable")
        authority = await authorize_live_research(principal, specimen, binding,
            actor_uid=principal.user_id, environ=environment, verify_access=self.verify_access)
        store = self.mutable_store(binding, authority=authority)
        bound = binding.durability_scope(principal)
        store.require_live_authority(bound)
        document = await asyncio.to_thread(store._read, bound)
        job = store._job(document.state, bound)
        binding.validate_job(job, program_key=store.program_key)
        from dataclasses import asdict, replace
        from .production_runtime import committed_job_pins, research_budget_policy, research_program_key
        from .contracts import digest
        expected = committed_job_pins(specimen.run.profile_snapshot,
            organization_id=bound.organization_id, collection_id=bound.collection_id,
            input_digest=binding.base_canonical.snapshot_sha256)
        policy = document.state["budget_policy"]
        seed = policy.get("external_settled_micro_usd")
        if type(seed) is not int or seed < 0:
            raise HeldUnknown("research_live_admission_unqualified")
        committed_policy = asdict(replace(research_budget_policy(specimen.run.profile_snapshot),
            external_settled_micro_usd=seed))
        if (binding.program_key != research_program_key(specimen.run.id)
            or job["pins"] != expected or policy != committed_policy
            or digest(policy) != binding.journal_budget_policy_digest):
            raise HeldUnknown("research_retry_current_runtime_unavailable")
        return store, specimen

    async def retry_available(self, principal, scope, field_key):
        try:
            binding = await self.binding(principal, scope.specimen_id)
            if binding.research_scope() != scope or field_key in binding.research_locks:
                return False
            store, specimen = await self._authorized_store(principal, binding)
            bound = binding.durability_scope(principal)
            document = await asyncio.to_thread(store._read, bound)
            job = store._job(document.state, bound)
            binding.validate_job(job, program_key=store.program_key)
            value = job["fields"][str(field_key)]
            if (job["paused"] or value["locked"] or binding.read_bundle.hold_reasons
                or value["work_state"] not in {"operational_failed", "retry_scheduled", "waiting_source"}):
                return False
            command_id = value.get("retry_command_id")
            command = document.state["outbox"].get("retry/" + (command_id or ""), {}).get("command", {})
            if command.get("dispatch_status") in {"sending", "unknown"}:
                return False
            store._source_retry_safety(document.state, bound, job, document.server_time,
                execution_class="live")
            budget = store._budget(document.state)
            seed = document.state["budget_policy"]["external_settled_micro_usd"]
            represented = max(seed, document.state.get("ordinary_cost_micros", seed))
            if budget["remaining_micro_usd"] <= max(0, specimen.run.usage.reserved_cost_micros - represented):
                return False
            journal = DurableResearchJournal(store, bound, Lease(bound.key, "http-read-only", 0, bound.generation, 0))
            return await journal.retry_eligible(scope, field_key)
        except (PermissionError, StaleWork, HeldUnknown, BudgetExceeded, ValueError):
            return False

    def _admit_retry(self, principal, binding, scope, field_key, **arguments):
        # This callback runs in the service's worker thread. Rebuild authority
        # after availability: a later deployment/access change grants nothing.
        store, specimen = asyncio.run(self._authorized_store(principal, binding))
        if field_key in binding.research_locks or binding.durability_scope(principal) != scope:
            raise StaleWork("research_retry_current_run_changed")
        document = store._read(scope)
        field = store._job(document.state, scope)["fields"][field_key]
        command = document.state["outbox"].get("retry/" + (field.get("retry_command_id") or ""), {}).get("command", {})
        if command.get("dispatch_status") in {"sending", "unknown"}:
            raise HeldUnknown("research_retry_dispatch_requires_reconciliation")
        # Later ordinary calls retain their high-water liability before the
        # existing atomic command reducer checks this Run's remainder.
        store.reconcile_ordinary_spend(scope, specimen.run.usage.reserved_cost_micros)
        return store.admit_retry(scope, field_key, **arguments)

    async def discover(self, principal, specimen_id):
        binding, _, _, _, job = await self.bound_state(principal, specimen_id)
        if not binding.same_snapshot(await self.binding(principal, specimen_id)):
            raise StaleWork("research_state_changed")
        eligible = tuple(key for key in FieldKey if not job["fields"][str(key)]["locked"]
            and job["fields"][str(key)].get("work_state") in {"operational_failed", "retry_scheduled", "waiting_source"})
        available = False
        for key in eligible:
            if await self.retry_available(principal, binding.research_scope(), key):
                available = True
                break
        return ResearchDiscoveryResultV2(canonical=binding.canonical, scope=binding.research_scope(),
            human_locked_fields=binding.research_locks,
            capabilities=DiscoveryCapabilities(read=True, retry=available, review=False),
            retry_blocked_reason=None if available else "retry_admission_unavailable")

    async def service(self, principal, locator):
        binding = await self.binding(principal, locator.specimen_id)
        if (binding.job_id, binding.generation) != (locator.job_id, locator.generation):
            raise StaleWork("research_state_changed")
        # Reads remain available when deployment or live admission is held.
        # Only a capability-qualified call gets a store with live authority.
        try:
            store, _ = await self._authorized_store(principal, binding)
        except (PermissionError, StaleWork, HeldUnknown, ValueError):
            store = self.mutable_store(binding)
        def admit(scope, field_key, **arguments):
            return self._admit_retry(principal, binding, scope, field_key, **arguments)
        return ResearchService(store=store, resolve_scope=self.resolve,
            retry_admission=admit, retry_available=self.retry_available,
            canonical_binding=self.binding, retry_queued=self.dispatch_retry)

    async def dispatch_retry(self, principal, scope, command_id):
        binding = await self.binding(principal, scope.specimen_id)
        if binding.research_scope() != scope or self.worker_dispatcher is None:
            raise StaleWork("research_retry_dispatch_unavailable")
        store, _ = await self._authorized_store(principal, binding)
        bound = binding.durability_scope(principal)
        document = await asyncio.to_thread(store._read, bound)
        command = store._retry_command(document.state, bound, command_id)
        if (command["status"] != "queued"
            or command.get("dispatch_status") in {"sending", "requested", "unknown"}):
            return
        from .retry_work_queue import schedule_research_retry
        await asyncio.to_thread(schedule_research_retry, self.native_repository,
            principal, binding, command_id)
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
