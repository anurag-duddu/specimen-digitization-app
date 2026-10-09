"""Deterministic field scheduling over the official agents and durable journal."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from specimen_digitization.application.domain import FieldValue

from .contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldCheckpoint, FieldKey,
    FieldResolution, ResearchScope, SourceResult, SpecialistRequest, SpecialistRole,
    WorkState, digest,
)
from .accepted_output import AcceptedOutputProofV1, validation_boundary_pins
from .telemetry import ResearchTrace, TraceIdentity, TraceParent, current_trace_parent

_SAFE_TERMINATIONS = frozenset({WorkState.RESOLVED, WorkState.NONBLOCKING_EXCEPTION})
_BLOCKING_STATES = frozenset({
    WorkState.PENDING, WorkState.RESEARCHING, WorkState.WAITING_SOURCE,
    WorkState.WAITING_POLICY, WorkState.RETRY_SCHEDULED, WorkState.OPERATIONAL_FAILED,
    WorkState.CANCELLED,
})


RESEARCH_ROLE_ORDER = (SpecialistRole.TEMPORAL, SpecialistRole.PARTIES,
    SpecialistRole.MEASUREMENT, SpecialistRole.COLLECTION,
    SpecialistRole.TAXONOMY, SpecialistRole.GEOGRAPHY)


class ResearchJournal(Protocol):
    async def validate_request(self, request: SpecialistRequest, *, model_settings_digest: str) -> None: ...

    async def field_revisions(self, scope: ResearchScope) -> Mapping[FieldKey, int]: ...

    async def protected_fields(self, scope: ResearchScope) -> tuple[FieldKey, ...]: ...

    async def trace_context(self, scope: ResearchScope) -> TraceParent | None: ...

    async def bind_trace(self, scope: ResearchScope, parent: TraceParent) -> None: ...

    async def load(self, scope: ResearchScope) -> tuple[FieldCheckpoint, ...]: ...

    async def commit(
        self, request: SpecialistRequest, resolutions: Sequence[FieldResolution], *,
        receipt_ids: Sequence[str], model_settings_digest: str,
        accepted_output: AcceptedOutputProofV1 | None = None,
    ) -> tuple[FieldCheckpoint, ...]: ...

    async def retry_eligible(self, scope: ResearchScope, field_key: FieldKey) -> bool: ...


class RunStatus(StrEnum):
    BLOCKED = "blocked"
    WAITING_INPUT = "waiting_input"
    COMPLETE = "complete"


@dataclass(frozen=True)
class EngineResult:
    scope: ResearchScope
    fields: Mapping[FieldKey, FieldResolution]
    checkpoints: tuple[FieldCheckpoint, ...]
    status: RunStatus
    clearance_eligible: bool
    exception_count: int
    resolved_count: int
    preserved_human_outcomes: Mapping[str, object] | None = None


def _pending(key: FieldKey) -> FieldResolution:
    return FieldResolution(
        field_key=key, work_state=WorkState.PENDING, value=FieldValue(),
        reason="field_not_yet_investigated",
    )


def _failure(key: FieldKey) -> FieldResolution:
    return FieldResolution(
        field_key=key, work_state=WorkState.OPERATIONAL_FAILED, value=FieldValue(),
        reason="specialist_operational_failure",
    )


def _validate(
    request: SpecialistRequest, resolution: FieldResolution,
    source_results: Sequence[SourceResult],
) -> FieldResolution:
    from .evidence import validate_resolution

    return validate_resolution(request, resolution, source_results)


class ResearchEngine:
    """Never pays for enumeration; prior accepted fields are not re-investigated.

    ``clearance_eligible`` is a research completeness gate consumed by the
    existing deterministic queue policy. It is not a second queue writer.
    """

    def __init__(
        self, *, profile: CollectionProfile,
        requests: Mapping[SpecialistRole, SpecialistRequest],
        journal: ResearchJournal,
        harness_factory: Callable[[Mapping[SpecialistRole, SpecialistRequest]], object],
        model_settings_digest: str,
        validate: Callable = _validate,
        max_concurrency: int = 1,
    ) -> None:
        if type(max_concurrency) is not int or not 1 <= max_concurrency <= 2:
            raise ValueError("bounded_concurrency_required")
        if not requests:
            raise ValueError("explicit_specialist_requests_required")
        if len(model_settings_digest) != 64 or any(c not in "0123456789abcdef" for c in model_settings_digest):
            raise ValueError("invalid_model_settings_pin")
        profile = CollectionProfile.model_validate(profile.model_dump(mode="json"))
        first = next(iter(requests.values()))
        self.scope = first.scope
        if self.scope.sensitive:
            raise ValueError("sensitive_research_not_authorized")
        if (
            profile.organization_id != self.scope.organization_id
            or profile.collection_id != self.scope.collection_id
            or digest(profile) != self.scope.profile_digest
        ):
            raise ValueError("immutable_profile_binding_mismatch")
        checked_requests = {}
        for role, request in requests.items():
            # Revalidate even model_copy-made requests; frozen objects are not
            # evidence that their nested data was validated by their caller.
            checked = SpecialistRequest.model_validate(request.model_dump(mode="json"))
            if role != checked.role or checked.scope != self.scope:
                raise ValueError("request_scope_or_role_mismatch")
            checked_requests[role] = checked
        self.profile = profile
        self.requests = checked_requests
        self.journal = journal
        self.harness_factory = harness_factory
        self.model_settings_digest = model_settings_digest
        self.validation_boundary = validation_boundary_pins()
        self.validate = validate
        self.max_concurrency = max_concurrency
        self.trace = ResearchTrace(TraceIdentity(
            specimen_id=self.scope.specimen_id, job_id=self.scope.job_id,
            generation=self.scope.generation,
        ))

    def _exception_valid(self, resolution: FieldResolution) -> bool:
        configured = next(p for p in self.profile.fields if p.field_key == resolution.field_key)
        return configured.exception is not None and configured.exception == resolution.exception

    def _checkpoint_valid(self, checkpoint: FieldCheckpoint) -> None:
        if checkpoint.scope != self.scope or checkpoint.field_key != checkpoint.resolution.field_key:
            raise ValueError("checkpoint_scope_mismatch")
        role = next(role for role, keys in ROLE_FIELDS.items() if checkpoint.field_key in keys)
        request = self.requests.get(role)
        if request is not None and (
            checkpoint.prompt_digest != request.prompt.digest
            or checkpoint.source_registry_digest != request.prompt.source_registry_digest
            or checkpoint.model_settings_digest != self.model_settings_digest
        ):
            raise ValueError("checkpoint_pins_changed_requires_new_generation")
        if checkpoint.resolution.work_state == WorkState.NONBLOCKING_EXCEPTION and not self._exception_valid(checkpoint.resolution):
            raise ValueError("unconfigured_policy_exception")

    def _batches(self, selected: Mapping[SpecialistRole, SpecialistRequest]):
        dependencies = {
            role: {
                dependency_role for dependency in request.dependencies
                for dependency_role, keys in ROLE_FIELDS.items()
                if dependency.field_key in keys and dependency_role in selected
                and dependency_role != role
            }
            for role, request in selected.items()
        }
        while dependencies:
            ready = tuple(role for role in RESEARCH_ROLE_ORDER if role in dependencies and not dependencies[role])
            if not ready:
                raise ValueError("research_dependency_cycle")
            yield ready
            dependencies = {role:deps - set(ready) for role,deps in dependencies.items() if role not in ready}

    async def run(self, *, retry_fields: Sequence[FieldKey] = (), retry_command_id: str | None = None,
                  role_limit: int | None = None) -> EngineResult:
        if role_limit is not None and (type(role_limit) is not int or not 1 <= role_limit <= len(SpecialistRole)):
            raise ValueError("bounded_specialist_role_limit_required")
        if retry_command_id is not None and (len(retry_fields) != 1 or len(retry_command_id) != 64
            or any(c not in "0123456789abcdef" for c in retry_command_id)):
            raise ValueError("retry_command_requires_one_field_and_valid_identity")
        # Capture before reading progress, so a competing settlement cannot
        # silently become the revision this investigation is allowed to replace.
        revisions = await self.journal.field_revisions(self.scope)
        fields = {key:_pending(key) for key in ALL_FIELDS}
        checkpoints: dict[FieldKey, FieldCheckpoint] = {}
        for checkpoint in await self.journal.load(self.scope):
            self._checkpoint_valid(checkpoint)
            previous = checkpoints.get(checkpoint.field_key)
            if previous is None or checkpoint.revision > previous.revision:
                checkpoints[checkpoint.field_key] = checkpoint
                fields[checkpoint.field_key] = checkpoint.resolution
        protected = set(await self.journal.protected_fields(self.scope))
        reader = getattr(self.journal, "preserved_human_outcomes", None)
        preserved = {} if reader is None else await reader(self.scope)
        for key in preserved:
            fields.pop(FieldKey(key), None)
        if any(str(pin.field_key) in preserved for request in self.requests.values() for pin in request.dependencies):
            raise ValueError("preserved_human_native_dependency_unsupported")
        for key in protected - set(checkpoints) - {FieldKey(k) for k in preserved}:
            fields[key] = FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
                value=FieldValue(), reason="canonical_human_decision_pending")
        retry = set(retry_fields)
        if not retry <= set(ALL_FIELDS):
            raise ValueError("unknown_retry_field")
        for key in retry:
            if (fields[key].work_state not in {WorkState.OPERATIONAL_FAILED, WorkState.RETRY_SCHEDULED, WorkState.WAITING_SOURCE}
                or not await self.journal.retry_eligible(self.scope, key)):
                raise ValueError("field_retry_requires_safe_current_effect_state")

        selected = {}
        for role, request in self.requests.items():
            keys = tuple(key for key in request.field_keys if key not in protected
                and (key in retry if retry else fields[key].work_state == WorkState.PENDING))
            if keys:
                from .temporal_context import temporal_dependency_pins
                selected[role] = SpecialistRequest.model_validate({
                    **request.model_dump(mode="json"), "field_keys":keys,
                    "field_revisions":{key:revisions[key] for key in keys},
                    "retry_command_id":retry_command_id,
                    "dependencies":temporal_dependency_pins(request, keys, checkpoints, preserved),
                })
        batches = tuple(self._batches(selected))  # Reject a cycle before any effect.
        if role_limit is not None:
            # A native worker step fits one existing fenced lease. Retained
            # progress handles later specialists; no lease is widened or reset.
            roles = tuple(role for batch in batches for role in batch)[:role_limit]
            selected = {role:selected[role] for role in roles}
            batches = tuple(self._batches(selected))
        for request in selected.values():
            await self.journal.validate_request(request, model_settings_digest=self.model_settings_digest)
        harness = self.harness_factory(selected) if selected else None
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def investigate(role):
            request = selected[role]
            async with semaphore:
                with self.trace.span("specialist", role=str(role), prompt_digest=request.prompt.digest) as specialist_span:
                    receipt_ids: tuple[str, ...] = ()
                    accepted_output = None
                    try:
                        await self.journal.validate_request(request, model_settings_digest=self.model_settings_digest)
                        # Exact consumed revisions/digests must still match,
                        # including after sibling publication. No paid rebase.
                        for dependency in request.dependencies:
                            checkpoint = checkpoints.get(dependency.field_key)
                            if checkpoint is None or checkpoint.revision != dependency.revision or digest(checkpoint.resolution) != dependency.digest:
                                raise ValueError("consumed_dependency_changed")
                        result = await harness.run_specialist(role)
                        resolutions = tuple(result.resolutions)
                        if len(resolutions) != len(request.field_keys) or {x.field_key for x in resolutions} != set(request.field_keys):
                            raise ValueError("specialist_field_coverage_mismatch")
                        source_results = tuple(getattr(result, "source_results", ()))
                        accepted = tuple(self.validate(request, resolution, source_results) for resolution in resolutions)
                        if any(x.work_state == WorkState.NONBLOCKING_EXCEPTION and not self._exception_valid(x) for x in accepted):
                            raise ValueError("unconfigured_policy_exception")
                        receipts = tuple(item.receipt for item in source_results if item.receipt is not None)
                        # Compatibility for an already-recovered application DTO.
                        receipts += tuple(getattr(result, "tool_receipts", ()))
                        if any(receipt.scope != self.scope for receipt in receipts):
                            raise ValueError("receipt_scope_mismatch")
                        receipt_ids = tuple(dict.fromkeys(
                            tuple(receipt.effect_id for receipt in receipts)
                            + tuple(getattr(result, "model_effect_ids", ()))
                        ))
                        if getattr(result, "native_run_id", None) is not None:
                            accepted_output = AcceptedOutputProofV1(
                                original_request=request, native_run_id=result.native_run_id,
                                conversation_id=result.conversation_id, resolutions=accepted,
                                source_results=source_results, effect_ids=receipt_ids,
                                model_settings_digest=self.model_settings_digest,
                                **self.validation_boundary,
                            )
                    except asyncio.CancelledError:
                        raise  # Cancellation never disguises an uncertain effect.
                    except Exception:
                        # Only a fixed application code crosses the boundary;
                        # provider/validator strings remain private.
                        accepted = tuple(_failure(key) for key in request.field_keys)
                    from .telemetry import resolution_outcome
                    try:
                        self.trace.annotate(specialist_span, **resolution_outcome(accepted))
                    except Exception:
                        pass  # Diagnostics cannot prevent durable completed work.
                    with self.trace.span("checkpoint", role=str(role)) as checkpoint_span:
                        persisted = await self.journal.commit(
                            request, accepted, receipt_ids=receipt_ids,
                            model_settings_digest=self.model_settings_digest,
                            **({"accepted_output": accepted_output} if accepted_output is not None else {}),
                        )
                        try:
                            self.trace.annotate(checkpoint_span,
                                **resolution_outcome(tuple(item.resolution for item in persisted), durable=True))
                        except Exception:
                            pass
                    for checkpoint in persisted:
                        self._checkpoint_valid(checkpoint)
                        checkpoints[checkpoint.field_key] = checkpoint
                        fields[checkpoint.field_key] = checkpoint.resolution

        async def run_batches():
            for batch in batches:
                # Journal failures block only their own fields; independent
                # domains still capture their completed work.
                outcomes = await asyncio.gather(*(investigate(role) for role in batch), return_exceptions=True)
                for role, outcome in zip(batch, outcomes):
                    if isinstance(outcome, asyncio.CancelledError):
                        raise outcome
                    if isinstance(outcome, BaseException):
                        for key in selected[role].field_keys:
                            fields[key] = _failure(key)
                # A multi-field commit can fail after publishing a sibling.
                # The returned progress always reflects those durable successes.
                for checkpoint in await self.journal.load(self.scope):
                    self._checkpoint_valid(checkpoint)
                    checkpoints[checkpoint.field_key] = checkpoint
                    fields[checkpoint.field_key] = checkpoint.resolution

        parent = await self.journal.trace_context(self.scope)
        self.trace = ResearchTrace(self.trace.identity, parent=parent)
        with self.trace.span("research"):
            active = current_trace_parent()
            retained_winner = None
            if parent is None and active is not None:
                from .persistence import TraceContextConflict
                try:
                    await self.journal.bind_trace(self.scope, active)
                except TraceContextConflict:
                    # Two valid workers can both observe an absent first root.
                    # Never overwrite the CAS winner or terminally block shared
                    # scientific work merely because telemetry lost this race.
                    retained_winner = await self.journal.trace_context(self.scope)
                    if retained_winner is None:
                        raise
            if retained_winner is not None:
                # Attach every scientific/model/checkpoint span to the retained
                # generation parent before running any batch or paid effect.
                self.trace = ResearchTrace(self.trace.identity, parent=retained_winner)
                with self.trace.span("research"):
                    await run_batches()
            else:
                await run_batches()

        required = tuple(fields[item.field_key] for item in self.profile.fields if item.mandatory and str(item.field_key) not in preserved)
        blocked = any(item.work_state in _BLOCKING_STATES for item in required)
        input_needed = bool(preserved) or any(item.work_state == WorkState.WAITING_HUMAN for item in required)
        eligible = not preserved and all(item.work_state in _SAFE_TERMINATIONS for item in required)
        status = RunStatus.BLOCKED if blocked else RunStatus.WAITING_INPUT if input_needed else RunStatus.COMPLETE
        return EngineResult(
            scope=self.scope, fields=fields, checkpoints=tuple(checkpoints[key] for key in ALL_FIELDS if key in checkpoints),
            status=status, clearance_eligible=eligible,
            exception_count=sum(item.work_state == WorkState.NONBLOCKING_EXCEPTION for item in fields.values()),
            resolved_count=sum(item.work_state == WorkState.RESOLVED for item in fields.values()),
            preserved_human_outcomes=preserved,
        )
