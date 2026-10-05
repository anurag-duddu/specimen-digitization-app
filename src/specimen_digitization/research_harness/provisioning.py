"""Provision the research harness for one run at its plan step.

The bridge calls provision at every plan tick before the research worker runs.
Once the run's current revision has its canonical binding, provision returns at
once. Otherwise it writes, in order and each idempotently:
1. the run's base record_version (the ordinary projector, base_record=True),
2. the run's research state document (program key and budget from the run),
3. the job "{run.id}-r{revision}", generation 1, with the committed pins,
4. the canonical binding, registered by the worker actor.
A retry after a partial failure replays the steps already written.
The connector registers for an operator or above and replaces a binding row
left by an earlier run or revision; a refused registration raises
HeldUnknown, so the run holds.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from specimen_digitization.application import projection
from specimen_digitization.application.domain import MANDATORY, Principal
from specimen_digitization.application.production import ProjectionRejected
from specimen_digitization.application.storage import Conflict, digest as canonical_digest
from specimen_digitization.application.workflow import OperationalBlock, Workflow
from .canonical_materialization_v2 import ResearchCanonicalPolicyV2
from .committed_pins import committed_harness_route
from .compatibility import PublicationUnavailable
from .contracts import FieldKey, digest
from .native_canonical import CanonicalIdentityV1
from .native_canonical_v2 import OwnerRegistrationV2, SqlConnectCanonicalResearchWriterV2
from .persistence import (DurabilityScope, HeldUnknown, PinnedRuntime, ResearchStore,
    SqlConnectStateBackend, StaleWork)
from .production_runtime import (WORKER_ROLES, committed_job_pins, research_budget_policy,
    research_program_key)
from .publication_v2 import genesis_digest
from .workflow_bridge import membership_verifier, worker_actor

LOGGER = logging.getLogger(__name__)
POLICY_ORIGIN = "repo:src/specimen_digitization/research_harness/canonical_materialization_v2.py#ResearchCanonicalPolicyV2"
# The binding writer's codes for a registration the connector refused: GraphQL
# errors (native_canonical.SqlConnectNativeOperationClient.execute) and a
# registered count other than one (native_canonical_v2.register_current_binding).
REGISTRATION_REFUSED = frozenset({"native_canonical_transaction_rejected",
    "native_v2_registration_rejected"})


def research_job_id(specimen) -> str:
    """One job per run revision: an ordinary save after registration starts a new job.

    The research trace identity (telemetry.TraceIdentity) admits letters,
    digits, "-" and "_" only, so the revision follows a hyphen.
    """
    return f"{specimen.run.id}-r{specimen.version}"


def binding_id_for(scope: DurabilityScope):
    return uuid5(NAMESPACE_URL, "specimen-research-binding:" + scope.key)


def _review_proofs(repository, scope, specimen):
    if not specimen.audit_offset and not any(event.action.startswith("review_") for event in specimen.audit):
        if specimen.run.dependencies.get("human_review_field_locks"):
            raise HeldUnknown("research_human_lock_provenance_unavailable")
        return []
    try:
        proofs, _ = repository._review_proofs(scope, specimen)
        return proofs
    except (AttributeError, ValueError, PermissionError) as error:
        raise HeldUnknown("research_human_lock_provenance_unavailable") from error


def verified_human_locks(specimen, proofs):
    """Import saved human decisions only from repository-proven review events.

    Metadata by itself cannot lock a field. Every candidate selection must
    still name the exact ordinary evidence and canonical value saved by that
    event, which the ordinary repository proves against immutable snapshots.
    """
    locks = specimen.run.dependencies.get("human_review_field_locks", {})
    if not isinstance(locks, dict):
        raise HeldUnknown("research_human_lock_provenance_unavailable")
    evidence = {item.id: item for item in specimen.run.evidence}
    result = {}
    for key, lock in locks.items():
        if key not in {str(field) for field in FieldKey} or not isinstance(lock, dict):
            raise HeldUnknown("research_human_lock_provenance_unavailable")
        field = specimen.run.fields.get(key)
        item = evidence.get(lock.get("evidence_id"))
        matches = []
        for proof in proofs:
            event, after = proof.event, proof.event.after
            if (proof.specimen_id != specimen.id or proof.resulting_revision > specimen.version
                or event.action != "review_research_candidate" or after.get("field_key") != key
                or after.get("selection_id") != lock.get("selection_id")):
                continue
            if (field is None or item is None or not item.raw_ref or not item.digest
                or item.kind != "authority_selection" or item.source != after.get("source_id")
                or item.locator != "research-candidate:" + str(lock.get("selection_id"))
                or item.id not in after.get("evidence_ids", []) or item.id not in field.evidence_ids
                or field.evidence_relations.get(item.id) != "decides"
                or field.parsed != after.get("value") or field.normalized != after.get("value")
                or field.authority_id != after.get("authority_id")):
                continue
            matches.append(digest({"event": event.model_dump(mode="json"),
                "snapshot": proof.snapshot_sha256, "audit": proof.server_audit_id,
                "evidence": item.model_dump(mode="json")}))
        if len(matches) != 1:
            raise HeldUnknown("research_human_lock_provenance_unavailable")
        result[key] = matches[0]
    return result


def _derivation_human_locks(repository, specimen, proofs):
    """Narrow admission for reviewed records with a proved saved G38 command.

    The worker independently verifies the command's human enqueue audit before
    provisioning. Here the current queue/run and immutable input provenance
    are checked again; merely changing a lifecycle stage grants no work.
    """
    from .derivation_contracts import DerivationCommand
    from .derivation_inputs import genuine_human_locked_fields, verify_settled_inputs

    try:
        command = DerivationCommand.model_validate(
            specimen.run.dependencies.get("research_derivation_request"))
        if (command.status not in {"queued", "running"}
            or command.queued_revision != specimen.version
            or command.canonical_run_id != specimen.run.id):
            raise ValueError("Current queued command required")
        info = repository.version_info(specimen.scope, specimen.id, command.source_revision)
        if info.get("sha256") != command.source_snapshot_sha256:
            raise ValueError("Immutable source snapshot required")
        verify_settled_inputs(repository, specimen, repository.graph_blobs, command.inputs, proofs=proofs)
        keys = set(genuine_human_locked_fields(repository, specimen, proofs=proofs))
        keys.update(item.field_key for item in command.inputs)
        if keys != set(command.human_locked_fields):
            raise ValueError("Current human locks required")
        # The proof helper already establishes every input's original review,
        # unchanged field digest and immutable provenance bytes. Preserve that
        # custody in the new job even for ordinary/manual human corrections.
        return {str(key): digest({"kind": "verified_derivation_human_lock/v1",
            "request_id": command.id, "input_digest": command.input_digest,
            "field_key": str(key), "field_digest": digest(specimen.run.fields[str(key)])})
            for key in keys}
    except (ValueError, TypeError, KeyError, AttributeError):
        raise StaleWork("research_provision_derivation_unproved") from None


def _write_base_record(repository, scope, specimen, actor, *, review_proofs=None) -> str:
    """Write the rows the base record references, then the record; replays are no-ops."""
    if review_proofs is None:
        review_proofs = _review_proofs(repository, scope, specimen)
    base = repository.variables(scope)
    rows = [write for write in projection.writes(specimen, repository.locate, repository._sized,
        actor, base_record=True, review_proofs=review_proofs) if write.operation != "AppendReviewDecisionV2"]
    records = [write for write in rows if write.operation == "AppendRecordVersionV2"]
    if len(records) != 1:
        raise HeldUnknown("research_base_record_unavailable")
    for write in rows:
        repository._insert(write.operation, {**base, **write.variables})
    return records[0].variables["id"]


async def provision(repository, principal, specimen, *, actor_uid=None, verify_access=None,
                    state_backend=None, writer_factory=SqlConnectCanonicalResearchWriterV2) -> None:
    principal = Principal.model_validate(principal.model_dump(mode="json"))
    run = specimen.run
    if principal.role not in WORKER_ROLES or principal.user_id != worker_actor(actor_uid):
        raise PermissionError("research_worker_actor_required")
    await (verify_access or membership_verifier(repository))(principal, False)
    writer = writer_factory(repository, None, blobs=None)
    variables = writer._variables(principal, specimen.id)
    try:
        current = (await writer._execute("GetCanonicalResearchBindingV2", variables))["binding"]
    except PublicationUnavailable as error:
        raise HeldUnknown(str(error)) from None
    if current is not None and current.get("active_registration_count") == 1:
        return
    # No binding row yet (count 0), or a row for an earlier run or revision
    # (no current row): register this run's current revision.
    # An ordinary Retry queues the same parsed run without repeating its
    # completed steps. Its next ordinary step, rather than the queue stage,
    # proves that it has reached the plan boundary again.
    at_plan = run.stage == "plan" or (run.stage == "pending" and Workflow.next_step(run) == "plan")
    if (specimen.asset.sensitive is not False
        or (not at_plan and run.stage not in {"finalized", "waiting_for_review"})
        or set(run.fields) != set(MANDATORY)
        or committed_harness_route(run.profile_snapshot) is None
        or run.dependencies.get("profile_snapshot_sha256") != canonical_digest(run.profile_snapshot)):
        raise StaleWork("research_provision_run_unavailable")
    proofs, derivation_locks = None, {}
    if not at_plan:
        if specimen.scope != principal.scope:
            raise StaleWork("research_provision_derivation_unproved")
        proofs = await asyncio.to_thread(_review_proofs, repository, principal.scope, specimen)
        derivation_locks = await asyncio.to_thread(_derivation_human_locks, repository, specimen, proofs)
    data = await asyncio.to_thread(repository.execute, "GetSnapshot",
        dict(repository.variables(principal.scope), id=specimen.id, revision=specimen.version))
    row = data.get("specimenSnapshot")
    if (not isinstance(row, dict) or row.get("revision") != specimen.version
        or row.get("sha256") != canonical_digest(row.get("snapshot"))):
        raise StaleWork("research_provision_snapshot_unproved")
    scope = DurabilityScope(principal.scope.organization_id, principal.scope.collection_id,
        specimen.id, research_job_id(specimen), 1, principal.user_id, False)
    program_key = research_program_key(run.id)
    try:
        pins = committed_job_pins(run.profile_snapshot, organization_id=scope.organization_id,
            collection_id=scope.collection_id, input_digest=row["sha256"])
        # At the plan step every paid ordinary step is done, so the run's ordinary
        # spend is final when the research state is created: the allowance starts
        # with it counted.
        allowance_policy = research_budget_policy(run.profile_snapshot, run.usage.reserved_cost_micros)
    except (TypeError, ValueError):
        raise HeldUnknown("research_committed_pins_unavailable") from None
    if proofs is None:
        proofs = await asyncio.to_thread(_review_proofs, repository, principal.scope, specimen)
    human_locks = verified_human_locks(specimen, proofs)
    human_locks = {**derivation_locks, **human_locks}
    try:
        record_id = await asyncio.to_thread(_write_base_record, repository, principal.scope,
            specimen, principal.user_id, review_proofs=proofs)
    except (ProjectionRejected, OperationalBlock, Conflict, OSError):
        # The connector refused a row or the call failed; the next tick replays.
        raise HeldUnknown("research_base_record_unavailable") from None
    store = ResearchStore(state_backend if state_backend is not None
        else SqlConnectStateBackend(repository), program_key)
    try:
        existing = await asyncio.to_thread(store.backend.load, scope, program_key)
        if existing:
            # Keep the immutable policy; the monotonic ordinary-cost high-water
            # mark below also counts every paid correction after this seed.
            allowance_policy = replace(allowance_policy, external_settled_micro_usd=
                existing.state["budget_policy"].get("external_settled_micro_usd", 0))
        await asyncio.to_thread(store.initialize, scope, allowance_policy)
        await asyncio.to_thread(store.reconcile_ordinary_spend, scope, run.usage.reserved_cost_micros)
        await asyncio.to_thread(store.create_job, scope, PinnedRuntime(**pins),
            [str(key) for key in FieldKey], record_revision=specimen.version, human_locks=human_locks)
    except ValueError:
        # The run's state or job exists with a different allowance or pins.
        raise HeldUnknown("research_provision_state_conflict") from None
    state = (await asyncio.to_thread(store._read, scope)).state
    base = CanonicalIdentityV1(record_revision=specimen.version, record_version_id=record_id,
        canonical_run_id=run.id, host_record_version_id=f"{run.id}:{specimen.version}",
        snapshot_sha256=row["sha256"])
    scientific = ResearchCanonicalPolicyV2(
        canonical_profile_digest=run.dependencies["profile_snapshot_sha256"],
        research_profile_digest=digest(pins["profile"]),
        source_registry_digest=pins["sources"]["registry_digest"])
    # The sources a lookup may cite: every full_response capture policy in the
    # committed pins (no other kind runs a lookup). Canonical evidence names a
    # source by its registry id.
    evidence_sources = {source_id: {"policy_digest": row["source_policy_digest"],
        "canonical_source": source_id, "input_context_rule": "exact_original_request_fragments/v2",
        "evidence_id_rule": "research-canonical-evidence/v1"}
        for source_id, row in sorted(pins["sources"]["capture_policies"].items())
        if row["kind"] == "full_response"}
    mapping = {"field_mapping": {str(key): str(key) for key in FieldKey},
        "research_policy_contract_version": scientific.contract_version,
        "research_policy_origin": POLICY_ORIGIN,
        "journal_budget_policy_digest": digest(state["budget_policy"]),
        "evidence_sources": evidence_sources}
    binding_id = binding_id_for(scope)
    # The run's research allowance. The schema also requires the legacy
    # import_proof_id/import_proof_digest columns; no import proof exists, so
    # they repeat the binding id and this digest.
    allowance = digest({"program_key": program_key, "budget_policy": state["budget_policy"]})
    registration = OwnerRegistrationV2(binding_id=binding_id, base_canonical=base,
        current_canonical=base, job_id=scope.job_id, job_key=scope.key, generation=1,
        input_digest=pins["input_digest"], profile_digest=digest(pins["profile"]),
        runtime_binding_digest=digest(pins),
        canonical_profile_digest=run.dependencies["profile_snapshot_sha256"],
        source_sha256=specimen.asset.sha256, semantic_mapping=mapping,
        semantic_mapping_digest=digest(mapping), policy_digest=digest(scientific),
        program_key=program_key, authority_digest=allowance, import_proof_id=binding_id,
        import_proof_digest=allowance, current_chain_digest=genesis_digest(binding_id, base))
    try:
        await writer.register_current_binding(principal, specimen.id, registration,
            store=store, scope=scope)
    except PublicationUnavailable as error:
        # The connector refused this specimen's row: this record alone is held.
        # A refusal arrives as GraphQL errors (a row the checks do not admit,
        # or one that may not replace the current row, fails the count check),
        # or as a count other than one.
        if str(error) in REGISTRATION_REFUSED:
            # GraphQL errors also cover transient connector failures (unavailable,
            # deadline, permission, a connector not yet redeployed); the hold is
            # the same, so the underlying code is logged (no payload).
            LOGGER.warning("research binding registration refused: %s (record ...%s)",
                str(error), str(specimen.id)[-6:])
            raise HeldUnknown("research_provision_registration_refused") from None
        raise HeldUnknown(str(error)) from None
    except PermissionError as error:
        # The worker's role cannot register: an authorization failure.
        raise HeldUnknown(str(error)) from None
