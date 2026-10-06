"""Actor-bound thread reads and server-approved durable retry admission.

This adapter never creates jobs, leases or model allowances. Scope resolution
and retry admission are trusted application wiring, not request parameters.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal, Protocol

from pydantic import Field

from specimen_digitization.application.domain import Principal

from .contracts import FieldKey, FrozenRecord, ResearchScope, WorkState, digest
from .canonical_binding import CanonicalResearchBinding
from .journal import DurableResearchJournal
from .persistence import DurabilityScope, Lease, ResearchStore, StaleWork
from .thread_view import ResearchThread, ResearchThreadReader


class ResearchLocator(FrozenRecord):
    organization_id: str = Field(min_length=1, max_length=100)
    collection_id: str = Field(min_length=1, max_length=100)
    specimen_id: str = Field(min_length=1, max_length=100)
    job_id: str = Field(min_length=1, max_length=256)
    generation: int = Field(strict=True, ge=1)


class RetryFieldRequest(FrozenRecord):
    expected_checkpoint_revision: int = Field(strict=True, ge=1)


class RetryAccepted(FrozenRecord):
    contract_version: Literal["research-retry-v1"] = "research-retry-v1"
    command_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    field_key: FieldKey
    generation: int = Field(strict=True, ge=1)
    expected_checkpoint_revision: int = Field(strict=True, ge=1)
    status: Literal["queued"] = "queued"


class RetryAdmission(Protocol):
    """A pure durable command reducer with atomic ACL and state preconditions.

    It must recheck the generation, revision, human lock, paused state, holds
    and server authorization inside the same transaction that records the
    command. Network/model execution does not belong in this callback.
    """

    def __call__(
        self, scope: DurabilityScope, field_key: str, *, expected_generation: int,
        expected_field_revision: int, idempotency_key: str,
    ) -> Mapping[str, Any]: ...


ScopeResolver = Callable[[Principal, ResearchLocator], Awaitable[DurabilityScope]]
RetryAvailability = Callable[[Principal, ResearchScope, FieldKey], Awaitable[bool]]


class ResearchService:
    def __init__(
        self, *, store: ResearchStore, resolve_scope: ScopeResolver,
        retry_admission: RetryAdmission,
        retry_available: RetryAvailability | None = None,
        canonical_binding: Callable[[Principal, str], Awaitable[CanonicalResearchBinding]] | None = None,
        retry_queued: Callable[[Principal, ResearchScope, str], Awaitable[None]] | None = None,
    ) -> None:
        self.store = store
        self.resolve_scope = resolve_scope
        self.retry_admission = retry_admission
        # Trusted server admission policy; absent means no retry capability.
        # In particular, ledger-import HOLD must not expose a retry UI action.
        self.retry_available = retry_available
        self.canonical_binding = canonical_binding
        self.retry_queued = retry_queued

    async def _bound_read(
        self, principal: Principal, locator: ResearchLocator, *, write: bool = False,
    ) -> tuple[DurabilityScope, ResearchScope, ResearchThreadReader, CanonicalResearchBinding | None]:
        principal = Principal.model_validate(principal.model_dump(mode="json"))
        if (
            principal.scope.organization_id != locator.organization_id
            or principal.scope.collection_id != locator.collection_id
            or not principal.user_id
            or (write and principal.role not in {"operator", "reviewer", "manager", "admin"})
        ):
            raise PermissionError("research_access_denied")
        bound = await self.resolve_scope(principal, locator)
        if not isinstance(bound, DurabilityScope) or (
            bound.organization_id, bound.collection_id, bound.specimen_id,
            bound.job_id, bound.generation, bound.actor_uid,
        ) != (
            locator.organization_id, locator.collection_id, locator.specimen_id,
            locator.job_id, locator.generation, principal.user_id,
        ):
            raise PermissionError("research_access_denied")
        # This actor-scoped read checks fresh membership, sensitive access,
        # generation and job identity. Persisted runtime pins never come from HTTP.
        binding = None
        if self.canonical_binding is None:
            job = await asyncio.to_thread(self.store.job, bound)
        else:
            binding = await self.canonical_binding(principal, locator.specimen_id)
            if binding.durability_scope(principal) != bound:
                raise StaleWork("research_state_changed")
            document = await asyncio.to_thread(self.store._read, bound)
            job = self.store._job(document.state, bound)
            binding.validate_job(job, program_key=self.store.program_key)
        scope = ResearchScope(
            organization_id=bound.organization_id, collection_id=bound.collection_id,
            specimen_id=bound.specimen_id, job_id=bound.job_id,
            generation=bound.generation, sensitive=bound.sensitive,
            input_digest=job["pins"]["input_digest"],
            profile_digest=digest(job["pins"]["profile"]),
        )
        # Thread reading needs no worker lease. An expired, unclaimed sentinel
        # permits the journal read interface and cannot authorize any effect.
        read_only = Lease(bound.key, "http-read-only", 0, bound.generation, 0)
        journal = DurableResearchJournal(self.store, bound, read_only)
        return bound, scope, ResearchThreadReader(journal), binding

    async def thread(self, principal: Principal, locator: ResearchLocator) -> ResearchThread:
        _, scope, reader, binding = await self._bound_read(principal, locator)
        thread = await reader.read(scope)
        if binding is not None and not binding.same_snapshot(
            await self.canonical_binding(principal, locator.specimen_id)):
            raise StaleWork("research_state_changed")
        fields = []
        for field in thread.fields:
            if "retry_field" in field.actions and not await self._retry_available(principal, scope, field.field_key):
                field = field.model_copy(update={"actions":tuple(
                    action for action in field.actions if action != "retry_field")})
            if binding is not None:
                if field.field_key in binding.research_locks:
                    changes = {"actions": ()}
                    # Verified carried decisions already have their required human state.
                    if field.checkpoint is None and field.preserved_human is None:
                        changes.update(work_state=WorkState.WAITING_POLICY,
                                       blocker_code="policy_prerequisite")
                    field = field.model_copy(update=changes)
                # Review/supply endpoints are not installed by I1. Capability
                # metadata must not advertise an executable human action.
                field = field.model_copy(update={"actions":tuple(
                    action for action in field.actions
                    if action not in {"supply_information", "review_proposal"})})
            fields.append(field)
        return thread.model_copy(update={"fields":tuple(fields)})

    async def _retry_available(self, principal: Principal, scope: ResearchScope, key: FieldKey) -> bool:
        return self.retry_available is not None and await self.retry_available(principal, scope, key) is True

    def _matching_queued_retry(
        self, scope: DurabilityScope, field_key: FieldKey, revision: int, idempotency_key: str,
    ) -> bool:
        """A lost ACK may revisit this exact queued command, never a running one."""
        document = self.store._read(scope)
        job = self.store._job(document.state, scope)
        field = job["fields"].get(str(field_key), {})
        checkpoint = field.get("checkpoint")
        command_id = field.get("retry_command_id")
        saved = document.state["outbox"].get("retry/" + command_id, {}) if command_id else {}
        command = saved.get("command", {})
        if checkpoint is None or field.get("revision") != revision or checkpoint.get("revision") != revision:
            return False
        checkpoint_digest = digest(checkpoint)
        expected_id = digest({
            "scope":scope.identity(), "field_key":str(field_key), "field_revision":revision,
            "checkpoint_digest":checkpoint_digest, "binding_digest":job["binding_digest"],
            "idempotency_key":idempotency_key,
        })
        return (
            not job["paused"] and not field.get("locked")
            and field.get("work_state") == "retry_scheduled"
            and saved.get("kind") == "research_field_retry" and saved.get("delivered") is False
            and command_id == expected_id and command.get("id") == expected_id
            and command.get("kind") == "retry_field" and command.get("status") == "queued"
            and command.get("scope") == scope.identity() and command.get("field_key") == str(field_key)
            and command.get("expected_generation") == scope.generation
            and command.get("expected_field_revision") == revision
            and command.get("checkpoint_digest") == checkpoint_digest
            and command.get("binding_digest") == job["binding_digest"]
            and command.get("idempotency_key") == idempotency_key
        )

    async def retry_field(
        self, principal: Principal, locator: ResearchLocator, field_key: FieldKey,
        request: RetryFieldRequest,
    ) -> RetryAccepted:
        bound, scope, reader, binding = await self._bound_read(principal, locator, write=True)
        thread = await reader.read(scope)
        field = next(item for item in thread.fields if item.field_key == field_key)
        if field.checkpoint is None or field.checkpoint.revision != request.expected_checkpoint_revision:
            raise StaleWork("research_state_changed")
        if binding is not None and field_key in binding.research_locks:
            raise PermissionError("research_retry_unavailable")
        if not await self._retry_available(principal, scope, field_key):
            raise PermissionError("research_retry_unavailable")
        # Deterministic retries of the same HTTP request reuse one durable command.
        # No client-controlled identifiers or budget/model settings enter it.
        key = digest({
            "scope":bound.identity(), "field_key":str(field_key),
            "checkpoint_revision":request.expected_checkpoint_revision,
        })
        if "retry_field" not in field.actions:
            matching = await asyncio.to_thread(self._matching_queued_retry,
                bound, field_key, request.expected_checkpoint_revision, key)
            if not matching or not await reader.journal.retry_eligible(scope, field_key):
                raise PermissionError("research_retry_unavailable")
        command = await asyncio.to_thread(
            self.retry_admission, bound, str(field_key),
            expected_generation=locator.generation,
            expected_field_revision=request.expected_checkpoint_revision,
            idempotency_key=key,
        )
        if (
            command.get("status") != "queued" or command.get("kind") != "retry_field"
            or command.get("scope") != bound.identity()
            or command.get("field_key") != str(field_key)
            or command.get("expected_generation") != locator.generation
            or command.get("expected_field_revision") != request.expected_checkpoint_revision
            or command.get("idempotency_key") != key
        ):
            raise StaleWork("research_retry_unavailable")
        # Do not acknowledge an in-memory callback result as durable acceptance.
        # Read the committed outbox again through this request's current actor.
        document = await asyncio.to_thread(self.store._read, bound)
        job = self.store._job(document.state, bound)
        saved = document.state["outbox"].get("retry/" + command["id"])
        if (
            saved is None or saved.get("kind") != "research_field_retry"
            or saved.get("command") != command
            or command.get("binding_digest") != job["binding_digest"]
        ):
            raise StaleWork("research_retry_unavailable")
        if self.retry_queued is not None:
            await self.retry_queued(principal, scope, command["id"])
        return RetryAccepted(
            command_id=command["id"], field_key=field_key,
            generation=locator.generation,
            expected_checkpoint_revision=request.expected_checkpoint_revision,
        )
