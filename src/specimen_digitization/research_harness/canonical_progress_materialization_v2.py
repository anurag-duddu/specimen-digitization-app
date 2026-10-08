"""Target-free recomputation of native whole-record research progress.

The sole native writer supplies current immutable checkpoint, snapshot and
published-field contexts. This producer changes policy metadata only; a terminal
work count never supplies scientific value or candidate authority.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from specimen_digitization.application.domain import Disposition, OPERATIONAL, Principal, Specimen
from specimen_digitization.application.human_field_carry import KEY as CARRY_KEY, VerifiedHumanCarries, job_outcomes
from specimen_digitization.application.storage import digest as canonical_digest
from .canonical_materialization import KEYS, unavailable
from .canonical_materialization_v2 import (
    BLOCKED, TERMINAL, UNFINISHED, ResearchCanonicalPolicyV2, TerminalFieldProofV2,
    _policy_held, _relations_unproved, _scientific_reasons,
)
from .canonical_projection_v2 import (
    CanonicalLineageContextV2, NativePriorSnapshotProofV2, _checkpoint,
    _literal_grounding, _prior_snapshot, _readings, _source_lineage, _value,
    validate_checkpoint_resolution_v2,
)
from .contracts import ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldCheckpoint, WorkState, digest
from .native_canonical_v2 import CanonicalBindingV2
from .native_materialization_context_v2 import canonical_prior_projection_v2
from .persistence import DurabilityScope, ResearchStore, StaleWork
from .publication import _native_checkpoint


@dataclass(frozen=True)
class _ProgressSnapshotBasis:
    """Common native snapshot basis, with no selected checkpoint or request."""
    native_prior_snapshot: NativePriorSnapshotProofV2
    prior_record_version_id: object
    prior_revision: int
    prior_snapshot_sha256: str


def _preserved(prior, reg, human_carries):
    try:
        outcomes = job_outcomes(reg.job)
    except (KeyError, TypeError, ValueError):
        unavailable("preserved_human_job_outcome_mismatch")
    locked = {key for key, value in reg.human_locks.items() if value}
    if prior.run.dependencies.get(CARRY_KEY) or outcomes or locked:
        if not isinstance(human_carries, VerifiedHumanCarries) or not human_carries.matches(prior):
            unavailable("preserved_human_current_base_unproved")
        if outcomes != human_carries.outcomes or locked != set(outcomes):
            unavailable("preserved_human_job_outcome_mismatch")
    elif human_carries is not None and (
            not isinstance(human_carries, VerifiedHumanCarries)
            or not human_carries.matches(prior) or human_carries.outcomes):
        unavailable("preserved_human_current_base_unproved")
    return outcomes


def _current_work(reg, scope, actor_uid, preserved):
    """Prove every real native state and immutable original/reuse pointer."""
    fields = reg.job.get("fields")
    if (type(fields) is not dict or set(fields) != {str(key) for key in ALL_FIELDS}
            or set(reg.field_mapping) != set(fields) or set(reg.field_mapping.values()) != KEYS
            or len(set(reg.field_mapping.values())) != 20
            or set(reg.human_locks) != KEYS
            or any(type(value) is not bool for value in reg.human_locks.values())):
        unavailable("canonical_field_work_mapping_unproved")
    durability = DurabilityScope(scope.organization_id, scope.collection_id,
        scope.specimen_id, scope.job_id, scope.generation, actor_uid, scope.sensitive)
    if reg.job.get("binding_digest") != digest(reg.job.get("pins")):
        unavailable("canonical_progress_checkpoint_binding_unproved")
    valid_states = {str(state) for state in WorkState}
    for research_key, row in fields.items():
        canonical_key = reg.field_mapping[research_key]
        if (type(row) is not dict or type(row.get("work_state")) is not str
                or row["work_state"] not in valid_states or type(row.get("locked")) is not bool
                or row["locked"] != reg.human_locks[canonical_key]
                or type(row.get("revision")) is not int or row["revision"] < 0):
            unavailable("canonical_field_work_mapping_unproved")
        if canonical_key in preserved:
            if row["checkpoint"] is not None or row["work_state"] != str(WorkState.WAITING_HUMAN):
                unavailable("preserved_human_job_outcome_mismatch")
            continue
        native = row.get("checkpoint")
        if native is None:
            if row["work_state"] not in {str(WorkState.PENDING), str(WorkState.RESEARCHING)}:
                unavailable("canonical_progress_checkpoint_state_unproved")
            continue
        try:
            original = FieldCheckpoint.model_validate(native["payload"])
            _, verified = _native_checkpoint(reg.job, original, original.scope)
            basis = ResearchStore._publication_basis(reg.job, durability, research_key)
        except (KeyError, TypeError, ValueError, StaleWork):
            unavailable("canonical_progress_checkpoint_state_unproved")
        if (str(original.field_key) != research_key or verified != original
                or original.scope.organization_id != scope.organization_id
                or original.scope.collection_id != scope.collection_id
                or original.scope.specimen_id != scope.specimen_id
                or original.scope.job_id != scope.job_id
                or original.resolution.work_state != row["work_state"]):
            unavailable("canonical_progress_checkpoint_state_unproved")
        if not basis["reused"]:
            if original.scope != scope:
                unavailable("canonical_progress_checkpoint_scope_unproved")
        else:
            history = next((row for row in reg.job["history"] if digest(row) == basis["history_digest"]), None)
            if (history is None or original.scope.input_digest != history["pins"]["input_digest"]
                    or original.scope.profile_digest != digest(history["pins"]["profile"])):
                unavailable("canonical_progress_checkpoint_scope_unproved")
        # Match the genuine journal loader's current runtime and dependency
        # checks without mutating its dependency high-water marks.
        pins = reg.job["pins"]
        role = next(role for role, keys in ROLE_FIELDS.items() if original.field_key in keys)
        prompt = pins.get("prompts", {}).get(str(role))
        if (type(prompt) is not dict or original.prompt_digest != prompt.get("digest")
                or original.source_registry_digest != pins.get("sources", {}).get("registry_digest")
                or original.model_settings_digest != digest(pins.get("settings"))):
            unavailable("canonical_progress_checkpoint_binding_unproved")
        revisions, digests = native["dependencies"], native.get("dependency_digests", {})
        if set(revisions) != set(digests):
            unavailable("canonical_progress_checkpoint_dependency_unproved")
        for key, revision in revisions.items():
            consumed = fields.get(key)
            checkpoint = None if consumed is None else consumed.get("checkpoint")
            if (type(revision) is not int or checkpoint is None
                    or consumed["revision"] != revision or checkpoint["revision"] != revision
                    or digest(checkpoint["payload"].get("resolution", checkpoint["payload"])) != digests[key]
                    or reg.job.get("dependencies", {}).get(key, revision) != revision):
                unavailable("canonical_progress_checkpoint_dependency_unproved")
    research = {key: row["work_state"] for key, row in fields.items()}
    return research, {reg.field_mapping[key]: state for key, state in research.items()}


def _qualified_fields(principal, prior, binding, scope, contexts, canonical, projection):
    """Qualify each published field against the common current native basis."""
    if type(contexts) is not tuple:
        unavailable("canonical_whole_record_grounding_unproved")
    reg, qualified = binding.registration, set()
    for proof in contexts:
        if not isinstance(proof, TerminalFieldProofV2) or not isinstance(proof.checkpoint, FieldCheckpoint):
            unavailable("canonical_whole_record_grounding_unproved")
        context, cp = proof.lineage_context, proof.checkpoint
        if (not isinstance(context, CanonicalLineageContextV2)
                or context.scope != scope or cp.scope != context.scope
                or context.actor_uid != principal.user_id or context.job != reg.job
                or context.field_mapping != reg.field_mapping or context.human_locks != reg.human_locks
                or context.prior_record_version_id != binding.canonical.record_version_id
                or context.native_prior_snapshot.canonical != binding.canonical
                or context.prior_projection != projection
                or cp.field_key not in context.original_request.field_keys):
            unavailable("canonical_whole_record_grounding_unproved")
        key = context.field_mapping.get(str(cp.field_key))
        if key not in canonical or key in qualified or reg.human_locks[key]:
            unavailable("canonical_whole_record_grounding_ambiguous")
        _prior_snapshot(prior, context)
        _, original = _checkpoint(context, cp)
        if (canonical[key] not in TERMINAL or str(original.resolution.work_state) != canonical[key]
                or context.original_request.scope != original.scope
                or context.original_request.prompt.digest != original.prompt_digest
                or context.original_request.prompt.source_registry_digest != original.source_registry_digest
                or _value(original.resolution, context) != prior.run.fields[key]):
            unavailable("canonical_whole_record_grounding_unproved")
        validate_checkpoint_resolution_v2(context, original)
        _source_lineage(context, prior, original, context.consumed_sources)
        rows, _ = _readings(prior.run.fields[key], prior.run, context)
        _literal_grounding(prior.run.fields[key], original.resolution, rows, context.original_request)
        qualified.add(key)
    return frozenset(qualified)


def _progress_reasons(run, profile, canonical, field_mapping, *, decision_lookup_ids=None):
    held = _policy_held(canonical, profile, field_mapping)
    operational = [f"research_work:{key}:{state}" for key, state in canonical.items()
        if state in BLOCKED and key not in held]
    human = [f"research_human_question:{key}" for key, state in canonical.items()
        if state == str(WorkState.WAITING_HUMAN)]
    human.extend(f"mandatory_unresolved:{key}" for key in sorted(held))
    if run.blocker:
        operational.append(run.blocker)
    if decision_lookup_ids is not None and (type(decision_lookup_ids) is not frozenset
            or any(type(key) is not str for key in decision_lookup_ids)
            or not decision_lookup_ids <= {row.id for row in run.lookups}):
        unavailable("canonical_lookup_dependency_mapping_unproved")
    for index, lookup in enumerate(run.lookups):
        if (decision_lookup_ids is None or lookup.id in decision_lookup_ids) and lookup.status in OPERATIONAL and not any(
                later.status.value == "success" and later.provider == lookup.provider and later.query == lookup.query
                for later in run.lookups[index + 1:]):
            operational.append(f"source_operational_failure:{lookup.id}:{lookup.status}")
    return held, tuple(dict.fromkeys(operational)), tuple(dict.fromkeys(human))


class CanonicalProgressMaterializerV2:
    def __init__(self, policy: ResearchCanonicalPolicyV2):
        self.policy = ResearchCanonicalPolicyV2.model_validate(policy.model_dump(mode="json"))

    async def materialize_progress_v2(self, principal: Principal, prepared, binding: CanonicalBindingV2,
            prior: Specimen, *, terminal_contexts: tuple[TerminalFieldProofV2, ...], prior_projection,
            human_carries=None, native_prior_snapshot: NativePriorSnapshotProofV2):
        from .progress_publication_v2 import PreparedNativeProgressV2, ProgressMaterializationV2, ProgressOnlyReceiptV2
        prepared = PreparedNativeProgressV2.model_validate(prepared.model_dump(mode="json"))
        if not isinstance(binding, CanonicalBindingV2):
            unavailable("canonical_v2_binding_required")
        binding = CanonicalBindingV2.model_validate(binding.model_dump(mode="json"))
        reg, scope = binding.registration, prepared.basis.scope
        if (principal.user_id != prepared.basis.actor_uid or principal.role not in {"operator", "reviewer", "manager", "admin"}
                or principal.scope != prior.scope or str(binding.organization_id) != scope.organization_id
                or str(binding.collection_id) != scope.collection_id or str(binding.specimen_id) != prior.id
                or prior.id != scope.specimen_id or binding.sensitive or scope.sensitive or prior.asset.sensitive):
            raise PermissionError("canonical_materialization_scope_denied")
        if prior.run.human_approved or prior.run.history_restore_human_locks:
            unavailable("canonical_progress_global_human_decision_locked")
        if (reg.current_canonical != binding.canonical or prior.version != binding.canonical.record_revision
                or prior.run.id != str(binding.canonical.canonical_run_id) or prior.asset.sha256 != reg.source_sha256
                or canonical_digest(prior.run.profile_snapshot) != reg.canonical_profile_digest
                or reg.job_id != scope.job_id or reg.generation != scope.generation or reg.input_digest != scope.input_digest
                or reg.profile_digest != scope.profile_digest or reg.runtime_binding_digest != prepared.basis.binding_digest
                or reg.job_key != prepared.basis.job_key or reg.program_key != prepared.basis.program_key
                or prepared.basis.pins_digest != digest(reg.job["pins"])
                or prepared.basis.field_mapping_digest != digest(reg.field_mapping)
                or prepared.basis.policy_digest != reg.policy_digest
                or prepared.publication.canonical_anchor != binding.canonical
                or prepared.basis.field_work_digest != digest(reg.job["fields"])
                or prepared.basis.human_locks != reg.human_locks
                or prepared.basis.expected_record_revision != prior.version or set(prior.run.fields) != KEYS):
            unavailable("canonical_materialization_basis_stale")
        if reg.read_bundle["hold_reasons"] or reg.read_bundle["halted"] or reg.read_bundle["paused"]:
            unavailable("canonical_materialization_operational_hold")
        observed_at = reg.read_bundle["server_time"]
        if type(observed_at) not in {int, float} or not math.isfinite(observed_at) or observed_at <= 0:
            unavailable("canonical_materialization_server_time_unproved")
        if ResearchCanonicalPolicyV2.from_registered_binding(binding) != self.policy:
            unavailable("canonical_research_policy_unproved")
        profile = CollectionProfile.model_validate(reg.job["pins"]["profile"])
        if (digest(profile) != reg.profile_digest or len(profile.fields) != 20
                or {row.field_key for row in profile.fields} != set(ALL_FIELDS)
                or profile.organization_id != scope.organization_id or profile.collection_id != scope.collection_id
                or not next(row for row in profile.fields if str(row.field_key) == "date_identified").mandatory):
            unavailable("canonical_research_profile_unproved")
        projection = canonical_prior_projection_v2(prior_projection, binding.canonical.record_version_id)
        if not isinstance(native_prior_snapshot, NativePriorSnapshotProofV2) or native_prior_snapshot.canonical != binding.canonical:
            unavailable("canonical_progress_native_snapshot_unproved")
        _prior_snapshot(prior, _ProgressSnapshotBasis(native_prior_snapshot, binding.canonical.record_version_id,
            prior.version, canonical_digest(prior.model_dump(mode="json"))))
        preserved = _preserved(prior, reg, human_carries)
        research, canonical = _current_work(reg, scope, principal.user_id, preserved)
        if set(research.values()) & {str(WorkState.PENDING), str(WorkState.RESEARCHING), str(WorkState.RETRY_SCHEDULED)}:
            unavailable("canonical_progress_runnable_work_remaining")
        qualified = _qualified_fields(principal, prior, binding, scope, terminal_contexts, canonical, projection)
        result = prior.model_copy(deep=True)
        result.version += 1
        held, operational, human = _progress_reasons(result.run, profile, canonical, reg.field_mapping)
        unpublished = _relations_unproved(reg.job, reg.field_mapping)
        human = tuple(dict.fromkeys((*human, *(f"mandatory_unresolved:{key}" for key in sorted(unpublished)),
            *_scientific_reasons(result, profile, observed_at, latest_work=canonical, field_mapping=reg.field_mapping,
                scientific_qualified=qualified, unpublished=unpublished))))
        states = {state for key, state in canonical.items() if key not in held}
        ungrounded = KEYS - held - unpublished - qualified - set(preserved)
        if preserved:
            human = tuple(reason for reason in human if reason not in {f"research_human_question:{key}" for key in preserved})
            human += tuple(f"preserved_human_decision:{key}" for key in sorted(preserved))
        if not states & UNFINISHED and ungrounded:
            operational += tuple(f"canonical_field_grounding_unproved:{key}" for key in sorted(ungrounded))
        unfinished, blocked = bool(states & UNFINISHED), bool(states & BLOCKED or operational)
        result.run.disposition = None if unfinished or operational else Disposition.REVIEW if human else Disposition.CLEARED
        result.run.stage = "processing_blocked" if blocked else "research_in_progress" if unfinished else "finalized"
        result.run.reasons = list(dict.fromkeys((*operational, *human)))
        result_sha = canonical_digest(result.model_dump(mode="json"))
        disposition = None if result.run.disposition is None else str(result.run.disposition)
        progress = ProgressOnlyReceiptV2(binding_id=reg.binding_id, job_key=reg.job_key, generation=reg.generation,
            prior_canonical=binding.canonical, result_digest=result_sha, policy_digest=reg.policy_digest,
            field_work_digest=digest(reg.job["fields"]), field_mapping_digest=digest(reg.field_mapping),
            research_field_work=research, canonical_field_work=canonical,
            wire_status="processing_blocked" if blocked else "running" if unfinished else "completed",
            run_stage=result.run.stage, disposition=disposition, operational_reason_codes=operational,
            human_reason_codes=human, exportable=result.run.disposition == Disposition.CLEARED)
        lineage = {"contract_version":"canonical-progress-only-lineage/v2",
            "prior_canonical":binding.canonical.model_dump(mode="json"), "prior_projection":list(projection),
            "field_work_digest":progress.field_work_digest, "field_mapping_digest":progress.field_mapping_digest,
            "scientific_qualified":sorted(qualified), "preserved_human":{key:digest(value) for key, value in sorted(preserved.items())},
            "unchanged_fields_digest":digest({key:value.model_dump(mode="json") for key,value in prior.run.fields.items()}),
            "unchanged_evidence_digest":digest([value.model_dump(mode="json") for value in prior.run.evidence])}
        lineage_sha = digest(lineage)
        receipt = {"status":"computed", "policy_contract_version":self.policy.contract_version,
            "publication_digest":digest(prepared.publication), "prior_canonical":binding.canonical.model_dump(mode="json"),
            "result_digest":result_sha, "policy_digest":reg.policy_digest, "semantic_mapping_digest":reg.semantic_mapping_digest,
            "field_work_digest":progress.field_work_digest, "field_mapping_digest":progress.field_mapping_digest,
            "exact_field_keys":sorted(KEYS), "progress_receipt_digest":digest(progress),
            "disposition":disposition, "reasons":result.run.reasons, "date_identified_mandatory":True,
            "blanket_human_approval_required":False, "lineage_digest":lineage_sha,
            "progress_only_lineage":lineage, "tool_input_execution_projection_digest":digest([]),
            "prepack_active_graph":copy.deepcopy(prior.active_graph),
            "prepack_native_snapshot_digest":binding.canonical.snapshot_sha256,
            "prepack_full_graph_digest":canonical_digest(prior.model_dump(mode="json"))}
        return ProgressMaterializationV2(prepared_digest=digest(prepared), publication_digest=digest(prepared.publication),
            prior_canonical=binding.canonical, source_sha256=reg.source_sha256, canonical_profile_digest=reg.canonical_profile_digest,
            research_profile_digest=reg.profile_digest, runtime_binding_digest=reg.runtime_binding_digest,
            semantic_mapping_digest=reg.semantic_mapping_digest, policy_digest=reg.policy_digest, evidence_id_mapping={},
            result=result, result_digest=result_sha, policy_receipt=receipt, policy_receipt_digest=digest(receipt),
            lineage_digest=lineage_sha, progress_receipt=progress, progress_receipt_digest=digest(progress))
