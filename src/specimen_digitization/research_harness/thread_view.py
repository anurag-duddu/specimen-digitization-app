"""Authorized persisted field progress, independent of package message internals."""

import asyncio
from typing import Literal

from pydantic import Field

from specimen_digitization.application.domain import FieldValue

from .contracts import ALL_FIELDS, FieldCheckpoint, FieldKey, FrozenRecord, ResearchScope, WorkState, digest
from .journal import DurableResearchJournal
from .persistence import StaleWork


class FieldThread(FrozenRecord):
    field_key: FieldKey
    work_state: WorkState
    value: FieldValue
    checkpoint: FieldCheckpoint | None = None
    blocker_code: str | None = None
    actions: tuple[Literal["retry_field", "supply_information", "review_proposal"], ...] = ()


class EffectThread(FrozenRecord):
    effect_id: str
    generation: int = Field(strict=True, ge=1)
    kind: Literal["model", "tool"]
    status: Literal["reserved", "sending", "held_unknown", "completed"]
    attempt_ids: tuple[str, ...]
    actual_micro_usd: int | None = Field(default=None, strict=True, ge=0)
    held_micro_usd: int = Field(strict=True, ge=0)
    capture_locator: str | None = None


class ResearchThread(FrozenRecord):
    contract_version: Literal["research-thread-v1"] = "research-thread-v1"
    scope: ResearchScope
    paused: bool
    fields: tuple[FieldThread, ...]
    effects: tuple[EffectThread, ...]
    resolved_count: int
    exception_count: int
    trace_ids: tuple[str, ...] = ()


class ResearchThreadReader:
    """Re-check membership on every read; never returns raw models or credentials."""

    def __init__(self, journal: DurableResearchJournal):
        self.journal = journal

    async def read(self, scope: ResearchScope) -> ResearchThread:
        checkpoints = {item.field_key:item for item in await self.journal.load(scope)}
        document = await asyncio.to_thread(self.journal.store._read, self.journal.scope)
        job = self.journal.store._job(document.state, self.journal.scope)
        fields = []
        for key in ALL_FIELDS:
            checkpoint = checkpoints.get(key)
            work_state = checkpoint.resolution.work_state if checkpoint else WorkState.PENDING
            stored = job["fields"].get(str(key), {})
            if stored.get("locked") and checkpoint is None:
                work_state = WorkState.WAITING_POLICY
            command_id = stored.get("retry_command_id")
            if command_id is not None:
                command = document.state["outbox"].get("retry/" + command_id, {}).get("command", {})
                if (command.get("scope") != self.journal.scope.identity() or command.get("field_key") != str(key)
                    or command.get("binding_digest") != job["binding_digest"]
                    or command.get("expected_field_revision") != stored.get("revision")
                    or checkpoint is None or checkpoint.revision != stored.get("revision")
                    or command.get("checkpoint_digest") != digest(stored["checkpoint"])):
                    raise StaleWork("thread_retry_command_binding_mismatch")
                if command.get("status") == "queued":
                    work_state = WorkState.RETRY_SCHEDULED
                elif command.get("status") == "running":
                    work_state = WorkState.RESEARCHING
            blocked_retry = False
            if checkpoint is not None and command_id is None:
                for event in document.state["outbox"].values():
                    command = event.get("command", {})
                    if (event.get("kind") == "research_field_retry"
                        and command.get("status") == "blocked"
                        and command.get("scope") == self.journal.scope.identity()
                        and command.get("field_key") == str(key)
                        and command.get("expected_field_revision") == stored.get("revision")
                        and command.get("binding_digest") == job["binding_digest"]
                        and command.get("checkpoint_digest") == digest(stored["checkpoint"])):
                        blocked_retry = True
                        break
            actions = []
            if not job["paused"] and not stored.get("locked"):
                if command_id is None and not blocked_retry and work_state in {WorkState.OPERATIONAL_FAILED, WorkState.RETRY_SCHEDULED}:
                    if await self.journal.retry_eligible(scope, key):
                        actions.append("retry_field")
                if checkpoint and work_state == WorkState.WAITING_HUMAN and checkpoint.resolution.question:
                    actions.append("supply_information")
            blocker = {
                WorkState.WAITING_SOURCE:"source_prerequisite",
                WorkState.WAITING_POLICY:"policy_prerequisite",
                WorkState.OPERATIONAL_FAILED:"research_operational_failure",
                WorkState.WAITING_HUMAN:"human_decision_required",
            }.get(work_state)
            if blocked_retry:
                blocker = "research_retry_blocked"
            fields.append(FieldThread(field_key=key, work_state=work_state,
                value=checkpoint.resolution.value if checkpoint else FieldValue(),
                checkpoint=checkpoint, blocker_code=blocker, actions=tuple(actions)))
        used = {effect for checkpoint in checkpoints.values() for effect in checkpoint.effect_receipt_ids}
        effects = []
        for effect in document.state["effects"].values():
            if effect["job_key"] != self.journal.scope.key:
                continue
            if effect["scope"]["generation"] != scope.generation and effect["effect_id"] not in used:
                continue
            receipt = effect["receipt"]
            effects.append(EffectThread(effect_id=effect["effect_id"],
                generation=effect["scope"]["generation"],
                kind="model" if effect["operation_key"].startswith("model:") else "tool",
                status=effect["status"], attempt_ids=tuple(item["attempt_id"] for item in effect["attempts"]),
                actual_micro_usd=effect["actual_micro_usd"], held_micro_usd=effect["held_micro_usd"],
                capture_locator=receipt["capture"]["locator"] if receipt else None))
        saved_trace = job.get("trace_context")
        trace_ids = tuple(dict.fromkeys(
            tuple(cp.trace_id for cp in checkpoints.values() if cp.trace_id)
            + ((saved_trace["trace_id"],) if saved_trace else ())))
        return ResearchThread(scope=scope, paused=job["paused"], fields=tuple(fields),
            effects=tuple(effects), trace_ids=trace_ids,
            resolved_count=sum(item.work_state == WorkState.RESOLVED for item in fields),
            exception_count=sum(item.work_state == WorkState.NONBLOCKING_EXCEPTION for item in fields))
