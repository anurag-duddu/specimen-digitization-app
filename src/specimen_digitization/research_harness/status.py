"""Private progress/output DTOs projected from the same authorized thread."""
from __future__ import annotations
from typing import Literal
from pydantic import Field, model_validator
from .contracts import FieldCheckpoint, FieldKey, FrozenRecord, ResearchScope, WorkState
from .thread_view import ResearchThread, PreservedHumanBase, preserved_base_matches
from specimen_digitization.application.human_field_carry import PreservedHumanFieldOutcome


class ResearchStatusV1(FrozenRecord):
    contract_version: Literal["research-status/v1"] = "research-status/v1"
    scope: ResearchScope
    status: Literal["blocked", "waiting_input", "pending", "completed"]
    paused: bool = Field(strict=True)
    historical: bool = Field(default=False, exclude_if=lambda value: value is False)
    canonical_revision: int | None = Field(default=None, exclude_if=lambda value: value is None)
    review_saved_revision: int | None = Field(default=None, exclude_if=lambda value: value is None)
    resolved_count: int = Field(strict=True, ge=0)
    exception_count: int = Field(strict=True, ge=0)
    field_count: int = Field(strict=True, ge=0)
    preserved_human_count: int = Field(default=0, strict=True, ge=0, le=20, exclude_if=lambda value: value == 0)
    # Completeness does not declare canonical clearance or exportability.
    canonical_acceptance: Literal["read_canonical_workspace"] = "read_canonical_workspace"

    @classmethod
    def from_thread(cls, thread: ResearchThread, *, missing_policy_fields: frozenset[FieldKey] = frozenset()):
        # missing_policy_fields are the fields whose pinned profile declares a
        # missing policy (verbatim_dts). A committed waiting_policy checkpoint on
        # one of them is that field's policy gate: it waits on people. Any other
        # waiting_policy, and a locked field with no checkpoint
        # (thread_view.py:61-62), still blocks.
        held = {item.field_key for item in thread.fields if item.work_state == WorkState.WAITING_POLICY
            and item.checkpoint is not None and item.field_key in missing_policy_fields}
        states = {item.work_state for item in thread.fields if item.field_key not in held}
        operational = {WorkState.OPERATIONAL_FAILED, WorkState.CANCELLED,
            WorkState.WAITING_POLICY, WorkState.WAITING_SOURCE}
        unknown = any(item.status in {"sending", "held_unknown"}
            or (item.status == "completed" and item.actual_micro_usd is None) for item in thread.effects)
        status = ("blocked" if thread.paused or unknown or states & operational
            else "pending" if thread.preserved_human_count and any(
                item.preserved_human is None and item.work_state in {WorkState.PENDING, WorkState.RESEARCHING, WorkState.RETRY_SCHEDULED}
                for item in thread.fields)
            else "waiting_input" if WorkState.WAITING_HUMAN in states or held
            else "pending" if not states <= {WorkState.RESOLVED, WorkState.NONBLOCKING_EXCEPTION}
            else "completed")
        return cls(scope=thread.scope, status=status, paused=thread.paused,
            historical=thread.historical, canonical_revision=thread.canonical_revision,
            review_saved_revision=thread.review_saved_revision,
            resolved_count=thread.resolved_count, exception_count=thread.exception_count,
            field_count=len(thread.fields), preserved_human_count=thread.preserved_human_count)


class ResearchOutputV1(FrozenRecord):
    contract_version: Literal["research-output/v1"] = "research-output/v1"
    scope: ResearchScope
    status: ResearchStatusV1
    checkpoints: tuple[FieldCheckpoint, ...]
    preserved_human_outcomes: tuple[PreservedHumanFieldOutcome, ...] = Field(default=(), exclude_if=lambda value: not value)
    preserved_human_base: PreservedHumanBase | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def valid_preserved_output(self):
        outcomes = {str(v.field_key): v for v in self.preserved_human_outcomes}
        base = self.preserved_human_base
        if not outcomes:
            if base is not None or self.status.preserved_human_count:
                raise ValueError("preserved_human_output_base_mismatch")
            return self
        if (self.scope != self.status.scope or len(outcomes) != len(self.preserved_human_outcomes)
                or self.status.preserved_human_count != len(outcomes)
                or not preserved_base_matches(base, outcomes)
                or base.registration_snapshot_sha256 != self.scope.input_digest
                or any((v.organization_id, v.collection_id, v.specimen_id) != (
                    self.scope.organization_id, self.scope.collection_id, self.scope.specimen_id)
                    or v.canonical_run_id != base.canonical_run_id or v.source_sha256 != base.source_sha256
                    or v.fresh_run_revision > base.registration_record_revision for v in outcomes.values())
                or any(str(cp.field_key) in outcomes for cp in self.checkpoints)):
            raise ValueError("preserved_human_output_base_mismatch")
        return self

    @classmethod
    def from_thread(cls, thread: ResearchThread):
        return cls(scope=thread.scope, status=ResearchStatusV1.from_thread(thread),
            checkpoints=tuple(item.checkpoint for item in thread.fields if item.checkpoint is not None),
            preserved_human_outcomes=tuple(item.preserved_human for item in thread.fields if item.preserved_human is not None),
            preserved_human_base=thread.preserved_human_base)
