"""Consume one durable retry without creating authority, leases or allowances."""

from __future__ import annotations

import asyncio
import copy
import re
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import Field

from .contracts import FieldKey, FrozenRecord, ResearchScope, digest
from .engine import ResearchEngine
from .persistence import DurabilityScope, HeldUnknown, Lease, ResearchStore, StaleWork


class RetryOutcome(FrozenRecord):
    command_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    field_key: FieldKey
    status: Literal["running", "completed", "blocked"]
    checkpoint_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blocked_reason: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,80}$")


EngineFactory = Callable[[DurabilityScope, Lease, Mapping[str, Any]], ResearchEngine]


class ResearchRetryWorker:
    """Use a trusted, fully pinned runtime factory after atomic command claim.

    The command's offline classification cannot classify an actual provider:
    model and source adapters independently enforce their transport admission.
    Live work needs the store's live research authority (persistence.py).
    The caller supplies an existing fenced lease; this consumer never releases
    a lease, creates a job, resets a budget or writes canonical specimen values.
    """

    def __init__(self, *, store: ResearchStore, engine_factory: EngineFactory) -> None:
        self.store = store
        self.engine_factory = engine_factory

    @staticmethod
    def _outcome(command: Mapping[str, Any]) -> RetryOutcome:
        return RetryOutcome(
            command_id=command["id"], field_key=FieldKey(command["field_key"]),
            status=command["status"], checkpoint_id=command.get("result_checkpoint_id"),
            blocked_reason=command.get("blocked_reason"),
        )

    def _read_command(self, scope: DurabilityScope, command_id: str) -> dict[str, Any]:
        document = self.store._read(scope)
        job = self.store._job(document.state, scope)
        command = self.store._retry_command(document.state, scope, command_id)
        if command["binding_digest"] != job["binding_digest"]:
            raise StaleWork("retry_worker_binding_changed")
        return copy.deepcopy(command)

    async def consume(
        self, scope: DurabilityScope, lease: Lease, command_id: str,
    ) -> RetryOutcome:
        if not isinstance(command_id, str) or not re.fullmatch(r"[a-f0-9]{64}", command_id):
            raise ValueError("retry_worker_requires_valid_command_identity")
        command = await asyncio.to_thread(self.store.claim_retry_command, scope, lease, command_id)
        if command["status"] in {"completed", "blocked"}:
            return self._outcome(command)
        # A committed native result is an acknowledgment-only recovery, even
        # when the worker restarted or the shared program has since halted.
        if command.get("result_checkpoint_id") is None:
            failure = "retry_checkpoint_missing"
            try:
                engine = self.engine_factory(scope, lease, copy.deepcopy(command))
                job = await asyncio.to_thread(self.store.job, scope)
                expected_scope = ResearchScope(
                    **scope.identity(), sensitive=scope.sensitive,
                    input_digest=job["pins"]["input_digest"],
                    profile_digest=digest(job["pins"]["profile"]),
                )
                if not isinstance(engine, ResearchEngine) or engine.scope != expected_scope:
                    raise StaleWork("retry_worker_runtime_scope_changed")
                await engine.run(retry_fields=(FieldKey(command["field_key"]),),
                    retry_command_id=command_id)
            except asyncio.CancelledError:
                # Cancellation can follow a provider send. Preserve durable
                # work and holds for reconciliation rather than claim failure.
                raise
            except Exception:
                failure = "retry_worker_failed"
            # A lost checkpoint acknowledgment may have raised after commit.
            # Only the native command-bound result can complete this command.
            command = await asyncio.to_thread(self._read_command, scope, command_id)
            if command.get("result_checkpoint_id") is None:
                try:
                    command = await asyncio.to_thread(self.store.complete_retry_command,
                        scope, lease, command_id, blocked_reason=failure)
                except HeldUnknown:
                    # Another consumer can have claimed this same lease before
                    # its provider send began. Its active send owns settlement;
                    # this duplicate only reports the durable nonterminal state.
                    command = await asyncio.to_thread(self._read_command, scope, command_id)
                return self._outcome(command)
        command = await asyncio.to_thread(self.store.complete_retry_command,
            scope, lease, command_id, checkpoint_id=command["result_checkpoint_id"])
        return self._outcome(command)
