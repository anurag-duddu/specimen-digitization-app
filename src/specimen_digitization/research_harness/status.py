"""Private progress/output DTOs projected from the same authorized thread."""
from __future__ import annotations
from typing import Literal
from pydantic import Field
from .contracts import FieldCheckpoint, FieldKey, FrozenRecord, ResearchScope, WorkState
from .thread_view import ResearchThread


class ResearchStatusV1(FrozenRecord):
    contract_version: Literal["research-status/v1"] = "research-status/v1"
    scope: ResearchScope
    status: Literal["blocked", "waiting_input", "pending", "completed"]
    paused: bool = Field(strict=True)
    resolved_count: int = Field(strict=True, ge=0)
    exception_count: int = Field(strict=True, ge=0)
    field_count: int = Field(strict=True, ge=0)
    # Completeness does not declare canonical clearance or exportability.
    canonical_acceptance: Literal["read_canonical_workspace"] = "read_canonical_workspace"

    @classmethod
    def from_thread(cls, thread: ResearchThread):
        states = {item.work_state for item in thread.fields}
        operational = {WorkState.OPERATIONAL_FAILED, WorkState.CANCELLED,
            WorkState.WAITING_POLICY, WorkState.WAITING_SOURCE}
        unknown = any(item.status in {"sending", "held_unknown"}
            or (item.status == "completed" and item.actual_micro_usd is None) for item in thread.effects)
        status = ("blocked" if thread.paused or unknown or states & operational
            else "waiting_input" if WorkState.WAITING_HUMAN in states
            else "pending" if not states <= {WorkState.RESOLVED, WorkState.NONBLOCKING_EXCEPTION}
            else "completed")
        return cls(scope=thread.scope, status=status, paused=thread.paused,
            resolved_count=thread.resolved_count, exception_count=thread.exception_count,
            field_count=len(thread.fields))


class ResearchOutputV1(FrozenRecord):
    contract_version: Literal["research-output/v1"] = "research-output/v1"
    scope: ResearchScope
    status: ResearchStatusV1
    checkpoints: tuple[FieldCheckpoint, ...]

    @classmethod
    def from_thread(cls, thread: ResearchThread):
        return cls(scope=thread.scope, status=ResearchStatusV1.from_thread(thread),
            checkpoints=tuple(item.checkpoint for item in thread.fields if item.checkpoint is not None))
