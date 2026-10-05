"""G38 queues one ordinary canonical save; only the native worker computes proposals."""
from __future__ import annotations

import asyncio
import inspect
import json

from specimen_digitization.application.domain import AuditEvent, ValueState
from specimen_digitization.application.storage import Conflict, Missing
from .candidate_selection import retained_candidate
from .canonical_binding import BindingUnavailable
from .compatibility import PublicationUnavailable
from .contracts import FieldKey, digest
from .derivation_contracts import (
    DERIVABLE_FIELDS, DERIVATION_RULE_VERSION, DerivationAccepted, DerivationCapability, DerivationCommand,
    DerivationProposal, DerivationRequest, DerivationResultRead, DerivationScheduleReceipt, derivation_input_digest,
)
from .derivation_inputs import collect_settled_inputs, inspect_settled_inputs, genuine_human_locked_fields
from .persistence import StaleWork
from .thread_view import candidate_selection_id

DEPENDENCY_KEY = "research_derivation_request"
RESULT_KEY = "derivation_result"
REVIEW_ROLES = {"reviewer", "manager", "admin"}


async def _call(function, *args):
    result = await asyncio.to_thread(function, *args)
    return await result if inspect.isawaitable(result) else result


def saved_derivation_command(specimen) -> DerivationCommand | None:
    raw = specimen.run.dependencies.get(DEPENDENCY_KEY)
    if raw is None:
        return None
    command = DerivationCommand.model_validate(raw)
    if command.canonical_run_id != specimen.run.id:
        raise StaleWork("derivation_run_changed")
    return command


class ResearchDerivationService:
    """The readiness callback is trusted deployed worker composition, never a user flag.

    Both readiness and operational scheduling callbacks are required. Enqueue
    uses the canonical CAS, then a native schedule operation bound to the saved
    revision; the dispatcher only wakes that durable queue. No budget state,
    source client, model or stale binding is used.
    """
    def __init__(self, *, repository, blobs, discovery, load_specimen,
                 ready=None, schedule_derivation=None, wake_worker=None, capture_blobs=None):
        self.repository, self.blobs, self.discovery = repository, blobs, discovery
        self.load_specimen, self.ready, self.wake_worker = load_specimen, ready, wake_worker
        self.schedule_derivation = schedule_derivation
        self.capture_blobs = capture_blobs

    async def _load(self, principal, specimen_id):
        specimen = await _call(self.load_specimen, principal, specimen_id)
        if (specimen.scope != principal.scope or specimen.id != specimen_id
                or not principal.user_id):
            raise PermissionError("derivation_access_denied")
        return specimen

    async def _available(self, principal, specimen):
        if (self.schedule_derivation is None or self.ready is None
                or await _call(self.ready, principal, specimen) is not True):
            return "derivation_worker_unavailable"
        if specimen.asset.sensitive is not False:
            return "derivation_sensitive_denied"
        if principal.role not in REVIEW_ROLES:
            return "derivation_review_required"
        if specimen.run.stage not in {"finalized", "waiting_for_review"}:
            return "derivation_record_busy"
        if specimen.run.lease_until or specimen.run.blocker:
            return "derivation_record_blocked"
        existing = saved_derivation_command(specimen)
        if existing is not None and specimen.version == existing.queued_revision:
            progress = await self.result(principal, specimen.id, existing.id)
            if progress.status in {"queued", "running"}:
                return "derivation_record_busy"
        return None

    async def _eligible(self, specimen):
        inputs = await asyncio.to_thread(inspect_settled_inputs,
            self.repository, specimen, self.blobs)
        if not inputs:
            return (), (), "derivation_settled_input_required"
        locks = await asyncio.to_thread(genuine_human_locked_fields, self.repository, specimen)
        eligible = tuple(key for key in FieldKey if key in DERIVABLE_FIELDS
            and key not in locks and key not in inputs
            and str(key) in specimen.run.fields
            and specimen.run.fields[str(key)].state != ValueState.SUPPORTED)
        return eligible, locks, None if eligible else "derivation_no_remaining_fields"

    async def capability(self, principal, specimen_id):
        specimen = await self._load(principal, specimen_id)
        reason = await self._available(principal, specimen)
        eligible = ()
        if reason is None:
            try:
                eligible, _, reason = await self._eligible(specimen)
            except (ValueError, PermissionError, Missing):
                reason = "derivation_input_proof_unavailable"
        return DerivationCapability(available=reason is None, blocked_reason=reason,
            canonical_revision=specimen.version, eligible_fields=eligible)

    async def enqueue(self, principal, specimen_id, request: DerivationRequest, idempotency_key):
        if (not isinstance(idempotency_key, str) or not idempotency_key.strip()
                or len(idempotency_key) > 200):
            raise StaleWork("derivation_idempotency_key_required")
        specimen = await self._load(principal, specimen_id)
        if principal.role not in REVIEW_ROLES or specimen.asset.sensitive is not False:
            raise PermissionError("derivation_access_denied")
        body_digest = digest(request)
        replay = specimen
        if specimen.version > request.expected_record_revision + 1:
            try:
                replay = await asyncio.to_thread(self.repository.version, principal.scope,
                    specimen_id, request.expected_record_revision + 1)
            except Missing:
                raise StaleWork("derivation_record_changed") from None
        prior = saved_derivation_command(replay)
        if prior is not None and prior.actor_uid == principal.user_id and prior.idempotency_key == idempotency_key:
            if prior.request_digest != body_digest:
                raise StaleWork("derivation_idempotency_changed")
            saved = await asyncio.to_thread(self.repository.save, principal, replay,
                prior.source_revision, "derive-rest:" + idempotency_key, body_digest)
            retained = saved_derivation_command(saved)
            await self._schedule(principal, saved, retained)
            await self._wake()
            return self._accepted(retained)
        if (specimen.version != request.expected_record_revision
                or request.base_record_version_id != f"{specimen.run.id}:{specimen.version}"):
            raise StaleWork("derivation_record_changed")
        reason = await self._available(principal, specimen)
        if reason is not None:
            raise PermissionError(reason)
        try:
            eligible, locks, reason = await self._eligible(specimen)
        except ValueError:
            raise StaleWork("derivation_input_proof_unavailable") from None
        if reason is not None or not set(request.requested_fields) <= set(eligible):
            raise StaleWork("derivation_targets_unavailable")
        inputs = await asyncio.to_thread(collect_settled_inputs,
            self.repository, specimen, self.blobs)
        info = await asyncio.to_thread(self.repository.version_info,
            principal.scope, specimen_id, specimen.version)
        command = DerivationCommand(id=digest({"actor":principal.user_id,
                "scope":principal.scope.model_dump(mode="json"), "specimen_id":specimen_id,
                "run_id":specimen.run.id, "revision":specimen.version,
                "snapshot_sha256":info["sha256"], "key":idempotency_key, "request":body_digest}),
            actor_uid=principal.user_id, reason=request.reason,
            source_revision=specimen.version, queued_revision=specimen.version + 1,
            canonical_run_id=specimen.run.id, source_snapshot_sha256=info["sha256"],
            inputs=inputs, input_digest=derivation_input_digest(inputs),
            human_locked_fields=tuple(key for key in FieldKey if key in set(locks) | {i.field_key for i in inputs}),
            requested_fields=request.requested_fields, idempotency_key=idempotency_key,
            request_digest=body_digest)
        pending = specimen.model_copy(deep=True)
        pending.run.dependencies[DEPENDENCY_KEY] = command.model_dump(mode="json")
        # Scheduling is operational metadata owned by the native queue callback.
        # Preserve all scientific stage/disposition/approval/field state here.
        pending.audit.append(AuditEvent(actor=principal.user_id, action="review_derive_rest",
            reason=request.reason, before={"revision":specimen.version, "run_id":specimen.run.id},
            after={"request_id":command.id, "input_digest":command.input_digest,
                "requested_fields":[str(key) for key in command.requested_fields]}))
        try:
            saved = await asyncio.to_thread(self.repository.save, principal, pending,
                specimen.version, "derive-rest:" + idempotency_key, body_digest)
        except Conflict:
            raise StaleWork("derivation_record_changed") from None
        retained = saved_derivation_command(saved)
        if retained != command or saved.version != command.queued_revision:
            raise StaleWork("derivation_enqueue_receipt_changed")
        await self._schedule(principal, saved, command)
        await self._wake()
        return self._accepted(command)

    async def _wake(self):
        if self.wake_worker is not None:
            try:
                await _call(self.wake_worker)
            except Exception:
                # A wake acknowledgement is not the durable admission. The
                # normal lane drain can still find this exact committed request.
                pass

    async def _schedule(self, principal, saved, command):
        if self.schedule_derivation is None:
            raise StaleWork("derivation_schedule_unavailable")
        receipt = DerivationScheduleReceipt.model_validate(
            await _call(self.schedule_derivation, principal, saved, command))
        if (receipt.request_id != command.id or receipt.queued_revision != saved.version
                or receipt.queued_revision != command.queued_revision
                or receipt.canonical_run_id != command.canonical_run_id):
            raise StaleWork("derivation_schedule_receipt_changed")

    @staticmethod
    def _accepted(command):
        return DerivationAccepted(request_id=command.id,
            source_revision=command.source_revision, queued_revision=command.queued_revision,
            canonical_run_id=command.canonical_run_id)

    async def result(self, principal, specimen_id, request_id):
        specimen = await self._load(principal, specimen_id)
        command = saved_derivation_command(specimen)
        if command is None or command.id != request_id:
            raise StaleWork("derivation_request_unavailable")
        stale = specimen.version != command.queued_revision or specimen.asset.sensitive is not False
        status, reason, proposals = command.status, command.blocked_reason, ()
        if not stale and command.status != "blocked":
            try:
                binding, _, scope, document, job = await self.discovery.bound_state(principal, specimen_id)
            except (BindingUnavailable, PublicationUnavailable):
                binding = None  # Queued work can await its first fresh registration.
            if binding is not None:
                if (binding.canonical.record_revision != command.queued_revision
                        or str(binding.canonical.canonical_run_id) != command.canonical_run_id
                        or job.get("dependencies", {}).get("derivation_request_id") != command.id):
                    raise StaleWork("derivation_binding_changed")
                result = job.get("dependencies", {}).get(RESULT_KEY)
                if result is not None:
                    if (not isinstance(result, dict) or result.get("request_id") != command.id
                            or result.get("status") not in {"running", "completed", "blocked"}):
                        raise StaleWork("derivation_result_unproved")
                    status, reason = result["status"], result.get("blocked_reason")
                    if status == "completed":
                        proposals = await asyncio.to_thread(self._proposals, command, document, scope, job, result,
                            capture_blobs=self.capture_blobs)
                if not binding.same_snapshot(await self.discovery.binding(principal, specimen_id)):
                    raise StaleWork("derivation_state_changed")
        return DerivationResultRead(request_id=command.id, status=status,
            source_revision=command.source_revision, queued_revision=command.queued_revision,
            canonical_revision=specimen.version, stale=stale, proposals=proposals,
            blocked_reason="derivation_input_revision_changed" if stale else reason)

    @staticmethod
    def _proposals(command, document, scope, job, result, *, capture_blobs=None):
        if command.status == "blocked":
            raise StaleWork("derivation_request_blocked")
        ids = result.get("checkpoint_ids")
        if not isinstance(ids, list) or len(ids) > len(command.requested_fields) or len(set(ids)) != len(ids):
            raise StaleWork("derivation_checkpoint_unproved")
        proposals = []
        for key in command.requested_fields:
            checkpoint = job["fields"][str(key)].get("checkpoint")
            if checkpoint is None or checkpoint.get("id") not in ids:
                continue
            for effect_id in checkpoint.get("receipt_ids", ()):
                effect = document.state["effects"].get(effect_id, {})
                payload = effect.get("receipt", {}).get("typed_payload", {})
                if payload.get("coverage", {}).get("source_id") != "georeference_spatial":
                    continue
                for raw in payload.get("candidate_json", ()):
                    item = json.loads(raw)
                    if item.get("settlement_allowed") is False or not item.get("value"):
                        continue
                    token = candidate_selection_id(scope.key, key, effect_id, item)
                    choice = retained_candidate(document, scope.key, key, token)
                    if choice["source_id"] != "georeference_spatial":
                        raise StaleWork("derivation_source_unproved")
                    data = {name:item[name] for name in ("field_key", "value", "input_fields", "input_revisions",
                        "evidence_ids", "authority_id", "dataset_ids", "tool_call_id", "value_layer", "rule_version")}
                    proposal = DerivationProposal(**data, checkpoint_id=checkpoint["id"],
                        checkpoint_revision=checkpoint["revision"], effect_id=effect_id, selection_id=token)
                    if proposal.rule_version != DERIVATION_RULE_VERSION:
                        raise StaleWork("derivation_rule_changed")
                    if (proposal.field_key != key
                            or dict(proposal.input_revisions) != {i.field_key:i.revision for i in command.inputs}
                            or set(proposal.input_fields) != {i.field_key for i in command.inputs}):
                        raise StaleWork("derivation_inputs_changed")
                    if capture_blobs is None:
                        raise StaleWork("derivation_capture_reader_unavailable")
                    from .source_capture_v2 import verify_spatial_derivation_capture

                    verify_spatial_derivation_capture(document, scope.key, key, command, choice, capture_blobs)
                    proposals.append(proposal)
        if not set(ids) <= {(job["fields"][str(k)].get("checkpoint") or {}).get("id")
                             for k in command.requested_fields}:
            raise StaleWork("derivation_checkpoint_unproved")
        return tuple(proposals)
