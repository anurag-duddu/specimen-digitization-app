"""Provision the research harness for one run at its plan step.

The bridge calls provision at every plan tick before the research worker runs.
Once the run's current revision has its canonical binding, provision returns at
once. Otherwise it writes, in order and each idempotently:
1. the run's base record_version (the ordinary projector, base_record=True),
2. the run's research state document (program key and budget from the run),
3. the job "{run.id}-r{revision}", generation 1, with the committed pins,
4. the canonical binding, registered by the worker actor.
A retry after a partial failure replays the steps already written.
"""
from __future__ import annotations

import asyncio
from uuid import NAMESPACE_URL, uuid5

from specimen_digitization.application import projection
from specimen_digitization.application.domain import MANDATORY, Principal
from specimen_digitization.application.production import ProjectionRejected
from specimen_digitization.application.storage import Conflict, digest as canonical_digest
from specimen_digitization.application.workflow import OperationalBlock
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

POLICY_ORIGIN = "repo:src/specimen_digitization/research_harness/canonical_materialization_v2.py#ResearchCanonicalPolicyV2"


def research_job_id(specimen) -> str:
    """One job per run revision: an ordinary save after registration starts a new job.

    The research trace identity (telemetry.TraceIdentity) admits letters,
    digits, "-" and "_" only, so the revision follows a hyphen.
    """
    return f"{specimen.run.id}-r{specimen.version}"


def binding_id_for(scope: DurabilityScope):
    return uuid5(NAMESPACE_URL, "specimen-research-binding:" + scope.key)


def _write_base_record(repository, scope, specimen, actor) -> str:
    """Write the rows the base record references, then the record; replays are no-ops."""
    base = repository.variables(scope)
    rows = [write for write in projection.writes(specimen, repository.locate, repository._sized,
        actor, base_record=True) if write.operation != "AppendReviewDecisionV2"]
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
    if (specimen.asset.sensitive is not False or run.stage != "plan"
        or set(run.fields) != set(MANDATORY)
        or committed_harness_route(run.profile_snapshot) is None
        or run.dependencies.get("profile_snapshot_sha256") != canonical_digest(run.profile_snapshot)):
        raise StaleWork("research_provision_run_unavailable")
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
        allowance_policy = research_budget_policy(run.profile_snapshot)
    except (TypeError, ValueError):
        raise HeldUnknown("research_committed_pins_unavailable") from None
    try:
        record_id = await asyncio.to_thread(_write_base_record, repository, principal.scope,
            specimen, principal.user_id)
    except (ProjectionRejected, OperationalBlock, Conflict, OSError):
        # The connector refused a row or the call failed; the next tick replays.
        raise HeldUnknown("research_base_record_unavailable") from None
    store = ResearchStore(state_backend if state_backend is not None
        else SqlConnectStateBackend(repository), program_key)
    try:
        await asyncio.to_thread(store.initialize, scope, allowance_policy)
        await asyncio.to_thread(store.create_job, scope, PinnedRuntime(**pins),
            [str(key) for key in FieldKey], record_revision=specimen.version)
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
        raise HeldUnknown(str(error)) from None
