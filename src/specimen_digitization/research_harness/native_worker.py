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
from .contracts import (
    ROLE_FIELDS, CollectionProfile, Digest, FrozenRecord, ResearchScope, SpecialistRole, WorkState, digest,
)
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


def _delivered_receipt_id(event):
    """The receipt id of a publication its outbox entry records as delivered, else None.

    PublishCanonicalResearchV2 inserts the receipt and sets this entry's ``delivered`` and
    ``canonical_commit`` in one SQL transaction (the connector requires the state to change by
    exactly that delta), and no other code sets ``delivered`` on a publication entry. The pair
    therefore stands for the receipt. An entry with only one of the two is not trusted: the
    caller verifies it against the receipt as it verifies a pending one."""
    commit = event.get("canonical_commit")
    if event.get("delivered") is True and type(commit) is dict and type(commit.get("id")) is str and commit["id"]:
        return commit["id"]
    return None


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


def _publication_order(checkpoints):
    """The order a pass offers its checkpoints: the specialists in roster order, and within one
    specialist the journal's key order with a derived value after its source (_sources_first).

    A pass ends at its first refusal. One role per window offered each role's fields in turn; with
    several roles in a window this order does the same, so a refusal on a later role's field
    (geography's) never strands an earlier role's committed field (taxonomy's). No role depends on
    another. If a dependency pin ever names a field of another role, the whole list is ordered
    sources first instead, so a derived value still follows its source."""
    items = tuple(checkpoints)
    role_of = {key: role for role, keys in ROLE_FIELDS.items() for key in keys}
    if any(role_of[pin.field_key] != role_of[item.field_key]
           for item in items for pin in item.resolution.dependencies):
        return _sources_first(items)
    return tuple(item for role in SpecialistRole
                 for item in _sources_first([item for item in items if role_of[item.field_key] == role]))


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
        # A retained pre-publication can consume one window without running a
        # role: its canonical commit requires reopening the exact send binding.
        maximum = 1 if retry_command_id is not None else len(SpecialistRole) + 1
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
                # unknown publication never relinquishes custody. A window that
                # ended blocked is released as well when nothing is in doubt (no
                # sending, held_unknown or reserved effect, no publication prepared
                # and not delivered): a lease left for its whole length would turn
                # an immediate step of the record into the drain-ending "already
                # claimed" instead of the record's own hold. That release is best
                # effort: if the round trip itself fails, the blocked outcome stands
                # (it is the record's hold) and the lease is simply kept, as it was
                # before. After a window that did not block, a failed release still
                # raises, as before.
                if outcome is not None:
                    blocked = outcome.reason_code is not None
                    try:
                        await asyncio.to_thread(runtime.store.release, runtime.scope, runtime.lease,
                            blocked=blocked)
                        released = True
                    except (HeldUnknown, StaleWork):
                        pass
                    except Exception as error:
                        if not blocked:
                            raise
                        LOGGER.warning("lease release after a blocked window failed: %s %s (record ...%s)",
                            *_described(error), str(specimen_id)[-6:])
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
            publications = []
            prior = await self._publish_committed(runtime, principal, specimen_id,
                publication_progress=publications)
            if prior.reason_code is not None:
                return prior
            if publications:
                # Publishing an already-paid checkpoint advances the canonical
                # tuple. End this known window and reopen before another effect;
                # never reuse or weaken the old immutable send authorization.
                return prior
            if getattr(runtime, "publication_only", False):
                job = await asyncio.to_thread(runtime.store.job, runtime.scope)
                pending = any(field["work_state"] == "pending" and not field["locked"]
                    for field in job["fields"].values())
                return prior.model_copy(update={"status": "blocked",
                    "reason_code": "research_program_headroom_unavailable"}) if pending else prior
            # One lease window: the next role_window pending specialists, at once.
            await runtime.engine.run(role_limit=runtime.role_window)
        return await self._publish_committed(runtime, principal, specimen_id)

    async def _publish_committed(self, runtime, principal, specimen_id, *, publication_progress=None):
        scope = runtime.binding.research_scope()
        # Only committed current checkpoints are eligible. A legacy/historical
        # body or a failed engine run is not scientific publication authority.
        typed = _publication_order(await runtime.journal.load(scope))
        # A supported value without the evidence relations the V2 projection
        # requires (today the evidence.py date and elevation helper values), and
        # any value that depends on one, is not offered: publication would
        # refuse it. The field keeps its prior record value, and each later
        # publication gives it the review reason mandatory_unresolved:{key}
        # (canonical_materialization_v2) instead of an operational block.
        unpublishable = relation_unproved_fields(item for item in typed if item.resolution.work_state in PUBLISHABLE)
        # The state is read once for the whole pass: the job and the outbox come out of
        # the same read, one snapshot, not two. A publication
        # rewrites neither a job field nor the job's record_revision (it only marks
        # its own two outbox events delivered), and a checkpoint's own pending guard
        # is created only when this loop prepares that checkpoint, so nothing the
        # loop reads for one checkpoint is changed by publishing another. Every pass
        # walks every earlier checkpoint again, so reading per checkpoint grew with
        # each window of a lease.
        document = await asyncio.to_thread(runtime.store._read, runtime.scope)
        job = runtime.store._job(document.state, runtime.scope)
        events = [event for event in document.state["outbox"].values()
            if event.get("kind") == "canonical_publication_required"]
        receipts, checkpoint_ids = [], []
        for checkpoint in typed:
            if checkpoint.resolution.work_state not in PUBLISHABLE or checkpoint.field_key in unpublishable:
                continue
            native = job["fields"][str(checkpoint.field_key)]["checkpoint"]
            checkpoint_ids.append(native["id"])
            pending = [event for event in events if event.get("guard", {}).get("checkpoint_id") == native["id"]]
            # A checkpoint the state document records as delivered was published by an
            # earlier pass: nothing to verify or read again (the proof, the receipt and
            # the intent are immutable and were checked when it was published).
            if len(pending) == 1 and (delivered := _delivered_receipt_id(pending[0])) is not None:
                receipts.append(delivered)
                continue
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
            if len(pending) > 1:
                raise StaleWork("native_publication_operation_ambiguous")
            if pending:
                winner = await runtime.canonical_service.winning_receipt(principal, specimen_id,
                    idempotency_key=pending[0]["guard"]["idempotency_key"], request_identity_digest=identity)
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
            if publication_progress is not None:
                publication_progress.append(str(published.causal.receipt_id))
        thread = await self._thread(runtime)
        from .status import ResearchStatusV1
        profile = CollectionProfile.model_validate(job["pins"]["profile"])
        status = ResearchStatusV1.from_thread(thread, missing_policy_fields=frozenset(
            row.field_key for row in profile.fields if row.missing_policy))
        return NativeResearchWorkerOutcomeV2(scope=scope, status=status.status,
            checkpoint_ids=tuple(checkpoint_ids), publication_receipt_ids=tuple(receipts))

    @staticmethod
    async def _thread(runtime):
        from .thread_view import ResearchThreadReader
        return await ResearchThreadReader(runtime.journal).read(runtime.binding.research_scope())
