"""Actual registered Harness -> retained checkpoints -> sole native V2 publication."""
from __future__ import annotations

import asyncio
import logging
import re
import traceback
from pathlib import Path
from typing import Literal
from pydantic import Field

from .accepted_output import read_accepted_checkpoint_proof
from .canonical_projection_v2 import relation_unproved_fields
from .contracts import CollectionProfile, Digest, FrozenRecord, ResearchScope, WorkState, digest
from .persistence import HeldUnknown, StaleWork
from .publication import prepare_native_publication
from .worker import ResearchRetryWorker

LOGGER = logging.getLogger(__name__)
# The publication layers refuse with lower-case snake_case codes (every one has
# an underscore). Any other message (a validation error, a connector's text, a
# bare word or number) can carry values and is never logged.
CODE = re.compile(r"(?=.{1,80}\Z)[a-z][a-z0-9]*(?:_[a-z0-9]+)+")

# Only terminal work publishes (canonical_materialization_v2 target gate,
# research_publication_v2.gql field work_state check). Waiting work reaches the
# record through the job's whole-20 field state on a terminal publication.
PUBLISHABLE = frozenset({WorkState.RESOLVED, WorkState.WAITING_HUMAN, WorkState.NONBLOCKING_EXCEPTION})


def _described(error):
    """What a publication failure may put in a log: its class, then its message
    when that is a code, else the file and line that raised it. Never other text."""
    message = str(error)
    if CODE.fullmatch(message):
        return type(error).__name__, "code=" + message
    frames = traceback.extract_tb(error.__traceback__)
    where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else "-"
    return type(error).__name__, "at=" + where


def _sources_first(checkpoints):
    """Journal order, except that a checkpoint follows the checkpoints its
    resolution's dependency pins name. The V2 projection publishes a derived
    value only after its source field's value is on the record
    (canonical_projection_v2._source_lineage), and the journal lists fields in
    key order, so elevation_from_ft would come before elevation_from_m."""
    remaining, ordered = list(checkpoints), []
    loaded = {item.field_key for item in remaining}
    placed = set()
    while remaining:
        ready = [item for item in remaining if all(pin.field_key in placed or pin.field_key not in loaded
            for pin in item.resolution.dependencies)]
        if not ready:
            # A cycle has no source-first order: keep journal order and let
            # publication refuse it.
            ordered.extend(remaining)
            break
        ordered.extend(ready)
        placed.update(item.field_key for item in ready)
        remaining = [item for item in remaining if item.field_key not in placed]
    return tuple(ordered)


class ImmutablePublicationLocatorV2(FrozenRecord):
    contract_version: Literal["native-publication-locator/v2"] = "native-publication-locator/v2"
    original_scope: ResearchScope
    program_key: str = Field(min_length=1, max_length=200)
    idempotency_key: Digest
    request_identity_digest: Digest


class NativeResearchWorkerOutcomeV2(FrozenRecord):
    contract_version: Literal["native-research-worker/v2"] = "native-research-worker/v2"
    scope: ResearchScope
    status: Literal["completed", "waiting_input", "pending", "blocked"]
    checkpoint_ids: tuple[str, ...] = ()
    publication_receipt_ids: tuple[str, ...] = ()
    reason_code: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,80}$")


class NativeResearchWorker:
    def __init__(self, runtime_factory):
        self.runtime_factory = runtime_factory

    async def run_registered(self, principal, specimen_id, *, owner, retry_command_id=None,
                             resume_operation: ImmutablePublicationLocatorV2 | None = None):
        if resume_operation is not None:
            resume_operation = ImmutablePublicationLocatorV2.model_validate(resume_operation.model_dump(mode="json"))
            winner = await self.runtime_factory.winning_receipt(principal, specimen_id, resume_operation)
            if winner is not None:
                return NativeResearchWorkerOutcomeV2(scope=winner.published.scope, status="pending",
                    publication_receipt_ids=(str(winner.causal.receipt_id),),
                    reason_code="publication_replayed_read_current_progress")
        # Every retained immutable operation is read before mutable discovery or
        # a new lease/model. Historical winners do not mean whole20 completion.
        locators = await self.runtime_factory.retained_publication_locators(principal, specimen_id)
        replayed = []
        for locator in locators:
            winner = await self.runtime_factory.winning_receipt(principal, specimen_id, locator)
            if winner is not None:
                replayed.append(str(winner.causal.receipt_id))
        from .contracts import SpecialistRole
        receipts, checkpoints = list(replayed), []
        maximum = 1 if retry_command_id is not None else len(SpecialistRole)
        for _ in range(maximum):
            self._deadline_check()
            runtime = await self.runtime_factory.open(principal, specimen_id, owner=owner)
            outcome, released = None, False
            try:
                outcome = await self._run_runtime(runtime, principal, specimen_id,
                    retry_command_id=retry_command_id)
                receipts.extend(outcome.publication_receipt_ids)
                checkpoints.extend(outcome.checkpoint_ids)
                self._deadline_check()
            finally:
                # A positively known completed role may close its exact lease;
                # release itself refuses unknown outcomes/costs. Cancellation or
                # unknown publication never relinquishes custody.
                if outcome is not None and outcome.reason_code is None:
                    try:
                        await asyncio.to_thread(runtime.store.release, runtime.scope, runtime.lease)
                        released = True
                    except (HeldUnknown, StaleWork):
                        pass
            if not released and outcome.reason_code is None:
                outcome = outcome.model_copy(update={"status":"blocked",
                    "reason_code":"research_worker_custody_requires_reconciliation"})
            if not released or outcome.reason_code is not None:
                return outcome.model_copy(update={
                    "checkpoint_ids":tuple(dict.fromkeys(checkpoints)),
                    "publication_receipt_ids":tuple(dict.fromkeys(receipts))})
            job = await asyncio.to_thread(runtime.store.job, runtime.scope)
            pending = any(field["work_state"] == "pending" and not field["locked"] for field in job["fields"].values())
            if not pending or retry_command_id is not None:
                break
            # The same original bounded worker invocation completes independent
            # pending roles. No retry of an operational field, new generation,
            # allowance or enlarged lease is created by this continuation.
        return outcome.model_copy(update={"checkpoint_ids":tuple(dict.fromkeys(checkpoints)),
            "publication_receipt_ids":tuple(dict.fromkeys(receipts))})

    @staticmethod
    def _deadline_check():
        from specimen_digitization.application.worker_deadline import current_deadline
        deadline = current_deadline()
        if deadline is not None:
            deadline.check()

    async def _run_runtime(self, runtime, principal, specimen_id, *, retry_command_id):
        scope = runtime.binding.research_scope()
        if retry_command_id is None:
            document = await asyncio.to_thread(runtime.store._read, runtime.scope)
            queued = [event["command"] for event in document.state["outbox"].values()
                if event.get("kind") == "research_field_retry" and event.get("delivered") is False
                and event.get("command", {}).get("scope") == runtime.scope.identity()
                and event["command"]["status"] in {"queued", "running"}]
            if queued:
                retry_command_id = min(queued, key=lambda command:(command["created_at"],command["id"]))["id"]
        if retry_command_id is not None:
            consumer = ResearchRetryWorker(store=runtime.store,
                engine_factory=lambda bound,lease,command:runtime.engine)
            retry = await consumer.consume(runtime.scope, runtime.lease, retry_command_id)
            if retry.status != "completed":
                return NativeResearchWorkerOutcomeV2(scope=scope, status="blocked",
                    reason_code="research_retry_not_completed")
        else:
            prior = await self._publish_committed(runtime, principal, specimen_id)
            if prior.reason_code is not None:
                return prior
            await runtime.engine.run(role_limit=1)
        return await self._publish_committed(runtime, principal, specimen_id)

    async def _publish_committed(self, runtime, principal, specimen_id):
        scope = runtime.binding.research_scope()
        # Only committed current checkpoints are eligible. A legacy/historical
        # body or a failed engine run is not scientific publication authority.
        typed = _sources_first(await runtime.journal.load(scope))
        # A supported value without the evidence relations the V2 projection
        # requires (today the evidence.py date and elevation helper values), and
        # any value that depends on one, is not offered: publication would
        # refuse it. The field keeps its prior record value, and each later
        # publication gives it the review reason mandatory_unresolved:{key}
        # (canonical_materialization_v2) instead of an operational block.
        unpublishable = relation_unproved_fields(item for item in typed if item.resolution.work_state in PUBLISHABLE)
        receipts, checkpoint_ids = [], []
        for checkpoint in typed:
            if checkpoint.resolution.work_state not in PUBLISHABLE or checkpoint.field_key in unpublishable:
                continue
            job = await asyncio.to_thread(runtime.store.job, runtime.scope)
            native = job["fields"][str(checkpoint.field_key)]["checkpoint"]
            checkpoint_ids.append(native["id"])
            try:
                await asyncio.to_thread(read_accepted_checkpoint_proof, runtime.store,
                    runtime.scope, runtime.blobs, native["id"])
            except StaleWork:
                return NativeResearchWorkerOutcomeV2(scope=scope, status="blocked",
                    checkpoint_ids=tuple(checkpoint_ids), publication_receipt_ids=tuple(receipts),
                    reason_code="accepted_output_proof_unavailable")
            # Preserve the first immutable operation key and request identity for
            # receipt-first restarts, independent of later state/lease changes.
            identity = digest({"contract_version":"native-research-worker-request/v2",
                "scope":native["scope"], "checkpoint_id":native["id"],
                "checkpoint_payload_digest":digest(native["payload"])})
            document = await asyncio.to_thread(runtime.store._read, runtime.scope)
            pending = [event["guard"] for event in document.state["outbox"].values()
                if event.get("kind") == "canonical_publication_required"
                and event.get("guard", {}).get("checkpoint_id") == native["id"]]
            if len(pending) > 1:
                raise StaleWork("native_publication_operation_ambiguous")
            if pending:
                winner = await runtime.canonical_service.winning_receipt(principal, specimen_id,
                    idempotency_key=pending[0]["idempotency_key"], request_identity_digest=identity)
                if winner is not None:
                    receipts.append(str(winner.causal.receipt_id))
                    continue
            try:
                prepared = await prepare_native_publication(runtime.journal, scope, checkpoint.field_key,
                    principal=principal, expected_record_revision=job["record_revision"], blobs=runtime.blobs)
                published = await runtime.canonical_service.publish_checkpoint(principal, prepared,
                    server_request_identity_digest=identity)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Do not classify an unknown commit/operational failure as a
                # quality question or attempt a generic specimen save fallback.
                # The one code below stands for every cause, so the cause is
                # logged here (no payload, no label text, a short record suffix).
                LOGGER.warning("native publication failed: %s %s field=%s (record ...%s)",
                    *_described(error), checkpoint.field_key, str(specimen_id)[-6:])
                return NativeResearchWorkerOutcomeV2(scope=scope, status="blocked",
                    checkpoint_ids=tuple(checkpoint_ids), publication_receipt_ids=tuple(receipts),
                    reason_code="native_publication_requires_reconciliation")
            receipts.append(str(published.causal.receipt_id))
        thread = await self._thread(runtime)
        from .status import ResearchStatusV1
        job = await asyncio.to_thread(runtime.store.job, runtime.scope)
        profile = CollectionProfile.model_validate(job["pins"]["profile"])
        status = ResearchStatusV1.from_thread(thread, missing_policy_fields=frozenset(
            row.field_key for row in profile.fields if row.missing_policy))
        return NativeResearchWorkerOutcomeV2(scope=scope, status=status.status,
            checkpoint_ids=tuple(checkpoint_ids), publication_receipt_ids=tuple(receipts))

    @staticmethod
    async def _thread(runtime):
        from .thread_view import ResearchThreadReader
        return await ResearchThreadReader(runtime.journal).read(runtime.binding.research_scope())
