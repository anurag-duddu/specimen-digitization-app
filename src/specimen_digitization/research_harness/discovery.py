"""Fresh canonical discovery and lifecycle reads; this module admits no effects."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

from pydantic import Field

from specimen_digitization.application.domain import Principal

from .canonical_binding import (
    BindingUnavailable, CanonicalBindingSnapshot, CanonicalIdentity,
    CanonicalResearchBinding, strict_durability_identity,
)
from .contracts import FieldKey, FrozenRecord, ResearchScope
from .persistence import HeldUnknown, ResearchStore, StateDocument, StaleWork
from .service import ResearchLocator


class BindingRepository(Protocol):
    def current_research_binding(self, scope, specimen_id: str) -> CanonicalBindingSnapshot: ...


class DiscoveryCapabilities(FrozenRecord):
    read: bool = Field(strict=True)
    retry: bool = Field(strict=True)
    review: bool = Field(strict=True)


class ResearchDiscoveryResult(FrozenRecord):
    contract_version: Literal["canonical-binding/v1"] = "canonical-binding/v1"
    canonical: CanonicalIdentity
    scope: ResearchScope
    human_locked_fields: tuple[FieldKey, ...]
    capabilities: DiscoveryCapabilities
    # Fixed reason only; raw source failures, policy and program state stay private.
    retry_blocked_reason: Literal["retry_admission_uninstalled"] = "retry_admission_uninstalled"
    review_blocked_reason: Literal["review_endpoint_uninstalled"] = "review_endpoint_uninstalled"


class _ScopedReadBackend:
    def __init__(self, binding: CanonicalResearchBinding, verified_actor: str):
        if binding.read_bundle is None:
            raise BindingUnavailable("research_state_unavailable")
        if not isinstance(verified_actor, str) or not verified_actor:
            raise PermissionError("research_access_denied")
        try:
            binding.validate_scoped_rows()
        except ValueError:
            raise BindingUnavailable("research_state_unavailable") from None
        self.binding = binding
        self.actor = verified_actor
        bundle = binding.read_bundle
        # A projection of real returned scoped rows, never an initialized budget
        # or a manufactured revision. No unrelated program job is present.
        self.document = StateDocument(bundle.state_revision, bundle.server_time, {
            "jobs": {binding.job_key: copy.deepcopy(bundle.job)},
            "effects": copy.deepcopy(bundle.effects), "outbox": copy.deepcopy(bundle.outbox),
            "halted": bundle.halted, "hold_reasons": tuple(bundle.hold_reasons),
        })

    def load(self, scope, program_key):
        from specimen_digitization.application.production import actor_uid

        if actor_uid.get() != self.actor or scope.actor_uid != self.actor:
            raise PermissionError("research_access_denied")
        try:
            identity = strict_durability_identity(scope.identity())
        except ValueError:
            raise StaleWork("research_state_changed") from None
        if (identity != {**self.binding.durability_identity(), "generation": self.binding.generation}
            or scope.key != self.binding.job_key
            or scope.sensitive is not self.binding.canonical.sensitive
            or program_key != self.binding.program_key):
            raise StaleWork("research_state_changed")
        return copy.deepcopy(self.document)

    def create(self, *args, **kwargs):
        raise PermissionError("Read-only canonical research snapshot")

    def cas(self, *args, **kwargs):
        raise PermissionError("Read-only canonical research snapshot")


class ScopedCanonicalReadStore(ResearchStore):
    """Read the exact native bundle through existing checkpoint validators."""

    def __init__(self, binding: CanonicalResearchBinding, *, verified_actor: str):
        super().__init__(_ScopedReadBackend(binding, verified_actor), binding.program_key)
        self.binding = binding

    def _read(self, scope):
        return self.backend.load(scope, self.program_key)

    def initialize(self, *args, **kwargs):
        raise PermissionError("Read-only canonical research snapshot")

    def _mutate(self, *args, **kwargs):
        raise PermissionError("Read-only canonical research snapshot")

    def budget(self, *args, **kwargs):
        raise HeldUnknown("Verified cumulative budget import is not installed")


class ResearchDiscovery:
    def __init__(self, repository: BindingRepository | None, *,
                 store_factory: Callable[[CanonicalResearchBinding], ResearchStore] | None,
                 verify_access: Callable[[Principal, bool], Awaitable[None]] | None = None):
        self.repository = repository
        self.store_factory = store_factory
        self.verify_access = verify_access

    async def binding(self, principal: Principal, specimen_id: str) -> CanonicalResearchBinding:
        if self.repository is None:
            raise BindingUnavailable("canonical_binding_unavailable")
        snapshot = await asyncio.to_thread(
            self.repository.current_research_binding, principal.scope, specimen_id,
        )
        if not isinstance(snapshot, CanonicalBindingSnapshot):
            raise BindingUnavailable("canonical_binding_unavailable")
        binding = snapshot.current(
            organization_id=principal.scope.organization_id,
            collection_id=principal.scope.collection_id, specimen_id=specimen_id,
        )
        binding.durability_scope(principal)
        if self.verify_access is not None:
            await self.verify_access(principal, binding.canonical.sensitive)
        return binding

    async def bound_state(self, principal: Principal, specimen_id: str):
        binding = await self.binding(principal, specimen_id)
        if self.store_factory is None:
            raise BindingUnavailable("research_state_unavailable")
        # Constructing a scoped repository is not initialize/create/lease/claim.
        store = self.store_factory(binding)
        if not isinstance(store, ScopedCanonicalReadStore) or store.program_key != binding.program_key:
            raise BindingUnavailable("research_state_unavailable")
        bound = binding.durability_scope(principal)
        document = await asyncio.to_thread(store._read, bound)
        job = store._job(document.state, bound)
        binding.validate_job(job, program_key=store.program_key)
        return binding, store, bound, document, job

    async def discover(self, principal: Principal, specimen_id: str) -> ResearchDiscoveryResult:
        binding, _, _, _, job = await self.bound_state(principal, specimen_id)
        # Recheck canonical pointer/registration after the independent journal
        # read. This rejects observed movement, and does not claim a cross-store
        # SQL snapshot or authorize a later publication/dispatch.
        if not binding.same_snapshot(await self.binding(principal, specimen_id)):
            raise StaleWork("research_state_changed")
        locks = tuple(k for k in FieldKey if k in binding.research_locks
                      or job["fields"].get(str(k), {}).get("locked") is True)
        return ResearchDiscoveryResult(
            canonical=binding.canonical, scope=binding.research_scope(),
            human_locked_fields=locks,
            capabilities=DiscoveryCapabilities(read=True, retry=False, review=False),
        )

    async def resolve(self, principal: Principal, locator: ResearchLocator):
        binding, _, bound, _, _ = await self.bound_state(principal, locator.specimen_id)
        if (binding.job_id, binding.generation) != (locator.job_id, locator.generation):
            raise StaleWork("research_state_changed")
        return bound

    async def retry_available(self, principal: Principal, scope: ResearchScope,
                              field_key: FieldKey) -> bool:
        binding, _, _, document, job = await self.bound_state(principal, scope.specimen_id)
        if binding.research_scope() != scope:
            raise StaleWork("research_state_changed")
        field = job["fields"].get(str(field_key), {})
        if (principal.role not in {"operator", "reviewer", "manager", "admin"}
            or field_key in binding.research_locks or field.get("locked") is True
            or job.get("paused") is not False or document.state.get("halted") is not False
            or document.state["hold_reasons"]):
            return False
        # Native dynamic holds are preserved, not overwritten with a permanent
        # legacy hold. I1 has no installed mutation/worker/import-verifier bridge:
        # a clear native read bundle alone cannot authorize a live retry.
        return False

    async def service(self, principal: Principal, locator: ResearchLocator):
        from .service import ResearchService

        binding, store, _, _, _ = await self.bound_state(principal, locator.specimen_id)
        if (binding.job_id, binding.generation) != (locator.job_id, locator.generation):
            raise StaleWork("research_state_changed")
        return ResearchService(
            store=store, resolve_scope=self.resolve, retry_admission=store.admit_retry,
            retry_available=self.retry_available, canonical_binding=self.binding,
        )


class DiscoveredResearchService:
    """Per-request service selection uses only the owner-registered program ID."""

    def __init__(self, discovery: ResearchDiscovery):
        self.discovery = discovery

    async def thread(self, principal: Principal, locator: ResearchLocator):
        return await (await self.discovery.service(principal, locator)).thread(principal, locator)

    async def retry_field(self, principal: Principal, locator: ResearchLocator,
                          field_key: FieldKey, request: Any):
        return await (await self.discovery.service(principal, locator)).retry_field(
            principal, locator, field_key, request,
        )
