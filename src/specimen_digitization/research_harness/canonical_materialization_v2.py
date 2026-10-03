"""Trusted canonical-policy-materialization/v2 SOURCE; execution UNRUN.

V1 stays immutable. Native V2 supplies real captured evidence and a private
transaction-read original/context provider, checks ancestry/preparation/CAS,
and recomputes/atomically persists value, record, progress and tool lineage.
Missing production context/whole20 proof remains operationally unavailable.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from specimen_digitization.application.domain import Disposition, OPERATIONAL, Principal, Specimen, ValueState
from specimen_digitization.application.policy import PLACEHOLDERS
from specimen_digitization.application.storage import digest as canonical_digest
from .canonical_materialization import KEYS, IRN, ResearchCanonicalPolicyV1, _date_bounds, _raw_grounded, unavailable
from .canonical_projection_v2 import (CanonicalLineageContextV2, _checkpoint, _literal_grounding, _prior_snapshot,
    _readings, _source_lineage, _value, project_canonical_value_v2, project_tool_input_lineage_v2,
    validate_checkpoint_resolution_v2)
from .canonical_evidence_provider_v2 import CapturedCanonicalEvidenceV2
from .contracts import ALL_FIELDS, CollectionProfile, FieldCheckpoint, FieldKey, SourceResult, SpecialistRequest, WorkState, digest
from .evidence import emu_irn_exception, validate_resolution
from .native_canonical import CANONICAL_PROJECTOR_SHA256, CanonicalProjectionServicesV1, CapturedCanonicalEvidenceV1, canonical_value_v1
from .native_canonical_v2 import CanonicalBindingV2, CanonicalPolicyMaterializationV2
from .publication import PreparedNativePublication
from .publication_v2 import CanonicalProgressReceiptV2
from .sources import result_envelope
from .native_materialization_context_v2 import (
    NativeMaterializationInputBundleV2, OriginalRequestProofV2, canonical_prior_projection_v2)

TERMINAL = {str(WorkState.RESOLVED), str(WorkState.WAITING_HUMAN), str(WorkState.NONBLOCKING_EXCEPTION)}
BLOCKED = {str(WorkState.WAITING_SOURCE), str(WorkState.WAITING_POLICY), str(WorkState.OPERATIONAL_FAILED), str(WorkState.RETRY_SCHEDULED), str(WorkState.CANCELLED)}
UNFINISHED = BLOCKED | {str(WorkState.PENDING), str(WorkState.RESEARCHING)}


def _policy_held(canonical, profile, field_mapping):
    """Fields waiting on a policy the research profile declares missing (verbatim_dts).

    Unknown semantics fail the field's policy gate (CONTRACTS.md:225-226): needs
    human review with the field reason, never an operational block, never cleared.
    Any other waiting_policy stays an operational block (CONTRACTS.md:243-246).
    """
    declared = {field_mapping[str(row.field_key)] for row in profile.fields if row.missing_policy}
    return frozenset(key for key, state in canonical.items()
        if key in declared and state == str(WorkState.WAITING_POLICY))


class ResearchCanonicalPolicyV2(ResearchCanonicalPolicyV1):
    contract_version: Literal["research-canonical-policy/v2"] = "research-canonical-policy/v2"
    lineage_rule: Literal["canonical-value-lineage/v2"] = "canonical-value-lineage/v2"
    progress_rule: Literal["actual_whole20_deferred_progress/v2"] = "actual_whole20_deferred_progress/v2"

    @classmethod
    def from_registered_binding(cls, binding):
        reg = binding.registration
        policy = cls(canonical_profile_digest=reg.canonical_profile_digest,
            research_profile_digest=reg.profile_digest,
            source_registry_digest=reg.job["pins"]["sources"]["registry_digest"])
        if (digest(policy) != reg.policy_digest or reg.policy_digest == reg.journal_budget_policy_digest
                or reg.semantic_mapping.get("research_policy_contract_version") != policy.contract_version
                or reg.semantic_mapping.get("research_policy_origin") != reg.research_policy_origin):
            unavailable("canonical_registered_scientific_policy_unproved")
        return policy


@dataclass(frozen=True)
class TerminalFieldProofV2:
    """Actual current typed checkpoint and its native-loaded original context.

    The shared checkpoint verifier proves immutable original/current reuse.
    An original payload is never rebound here to manufacture a current view.
    """
    checkpoint: FieldCheckpoint
    lineage_context: CanonicalLineageContextV2


@dataclass(frozen=True)
class MaterializationRequestV2:
    prepared_digest: str
    canonical_snapshot_sha256: str  # Actual packed native snapshot SHA.
    request: SpecialistRequest
    tool_results: tuple[SourceResult, ...]
    lineage_context: CanonicalLineageContextV2
    # Actual separately loaded native original contexts for terminal siblings.
    field_lineage_contexts: tuple[TerminalFieldProofV2, ...] = ()
    decision_lookup_ids: frozenset[str] | None = None


def _work_progress(reg, checkpoint, run, *, decision_lookup_ids=None, profile=None):
    fields = reg.job.get("fields")
    if (type(fields) is not dict or set(fields) != {str(key) for key in ALL_FIELDS}
            or set(reg.field_mapping) != set(fields) or set(reg.field_mapping.values()) != KEYS or len(set(reg.field_mapping.values())) != 20
            or any(type(row) is not dict or type(row.get("work_state")) is not str
                or row["work_state"] not in {str(state) for state in WorkState} for row in fields.values())
            or fields[str(checkpoint.field_key)]["work_state"] != str(checkpoint.resolution.work_state)):
        unavailable("canonical_field_work_mapping_unproved")
    research = {key: row["work_state"] for key, row in fields.items()}
    canonical = {reg.field_mapping[key]: state for key, state in research.items()}
    held = frozenset() if profile is None else _policy_held(canonical, profile, reg.field_mapping)
    operational = [f"research_work:{key}:{state}" for key, state in canonical.items() if state in BLOCKED and key not in held]
    human = [f"research_human_question:{key}" for key, state in canonical.items() if state == str(WorkState.WAITING_HUMAN)]
    human += [f"mandatory_unresolved:{key}" for key in sorted(held)]
    if run.blocker:
        operational.append(run.blocker)  # The actual blocker, no invented global cancellation.
    if decision_lookup_ids is not None and (type(decision_lookup_ids) is not frozenset
            or any(type(key) is not str for key in decision_lookup_ids) or not decision_lookup_ids <= {row.id for row in run.lookups}):
        unavailable("canonical_lookup_dependency_mapping_unproved")
    for index, lookup in enumerate(run.lookups):
        if (decision_lookup_ids is None or lookup.id in decision_lookup_ids) and lookup.status in OPERATIONAL and not any(
                later.status.value == "success" and later.provider == lookup.provider and later.query == lookup.query
                for later in run.lookups[index+1:]):
            operational.append(f"source_operational_failure:{lookup.id}:{lookup.status}")
    return research, canonical, tuple(dict.fromkeys(operational)), tuple(dict.fromkeys(human))


def _qualified_terminal_fields(prior, result, target_proof, contexts, canonical_work):
    qualified = set()
    actual = (target_proof, *contexts)
    target_context = target_proof.lineage_context
    targets = []
    for proof in actual:
        if not isinstance(proof, TerminalFieldProofV2) or not isinstance(proof.checkpoint, FieldCheckpoint):
            unavailable("canonical_whole_record_grounding_unproved")
        context, cp = proof.lineage_context, proof.checkpoint
        if (not isinstance(context, CanonicalLineageContextV2) or cp.scope != context.scope
                or cp.field_key not in context.original_request.field_keys):
            unavailable("canonical_whole_record_grounding_unproved")
        key = context.field_mapping.get(str(cp.field_key))
        if key not in canonical_work:
            unavailable("canonical_whole_record_grounding_unproved")
        if key in targets:
            unavailable("canonical_whole_record_grounding_ambiguous")
        targets.append(key)
        if (context.scope != target_context.scope or context.actor_uid != target_context.actor_uid
                or context.field_mapping != target_context.field_mapping or context.job != target_context.job
                or context.prior_record_version_id != target_context.prior_record_version_id
                or context.native_prior_snapshot.canonical != target_context.native_prior_snapshot.canonical
                or context.prior_projection != target_context.prior_projection):
            unavailable("canonical_whole_record_grounding_unproved")
        _prior_snapshot(prior, context)
        _, original = _checkpoint(context, cp)
        if (canonical_work[key] not in TERMINAL or str(original.resolution.work_state) != canonical_work[key]
                or context.original_request.scope != original.scope
                or context.original_request.prompt.digest != original.prompt_digest
                or context.original_request.prompt.source_registry_digest != original.source_registry_digest
                or _value(original.resolution, context) != result.run.fields[key]):
            unavailable("canonical_whole_record_grounding_unproved")
        validate_checkpoint_resolution_v2(context, original)
        _source_lineage(context, prior, original, context.consumed_sources)
        rows, _ = _readings(result.run.fields[key], result.run, context)
        _literal_grounding(result.run.fields[key], original.resolution, rows, context.original_request)
        qualified.add(key)
    return frozenset(qualified)


def _scientific_reasons(result, profile, observed_at, *, latest_work, field_mapping, scientific_qualified):
    """Versioned G1/G6/G42/G43 science rules evaluated on genuine settled fields.

    Unfinished work is handled separately; no work state is fabricated. Exact
    native original request/checkpoint/value lineage qualifies derived/settled
    layers before any source-evidence exemption below.
    """
    run = result.run
    reasons = [f"research_human_question:{key}" for key, state in latest_work.items() if state == str(WorkState.WAITING_HUMAN)]
    # This producer is admitted only through its distinct registered enhanced
    # scientific policy. PLAN G1 retires legacy31-34 and blanket138-139 here;
    # the original policy module and every ordinary run keep their own rules.
    if not run.coverage_confirmed or not run.regions:
        reasons.append("label_coverage_unconfirmed")
    for label in run.label_language_handling.get("labels", []):
        if label.get("review_required") and not run.human_approved:
            reasons.extend(f"{reason}:{label['region_id']}" for reason in label["reasons"])
    for region in run.regions:
        readings = [item for item in run.observations if item.region_id == region.id]
        if len({item.route_id for item in readings}) < 2 or len({item.model_id for item in readings}) < 2:
            reasons.append(f"independent_observations_missing:{region.id}")
        if any(not item.raw_ref or not item.raw_sha256 for item in readings):
            reasons.append(f"raw_provenance_missing:{region.id}")
        transcripts = [item for item in run.transcripts if item.region_id == region.id]
        if not transcripts or any(not item.resolved or not item.text for item in transcripts):
            drawn = [value for key, value in run.fields.items() if key != IRN and (
                value.source_region_id == region.id or any(identifier in {
                    reading.id for reading in readings} for identifier in value.verbatim_by_observation)
                or any(item.id in value.evidence_ids and item.region_id == region.id for item in run.evidence))]
            if not drawn or any(value.state != ValueState.SUPPORTED or not _raw_grounded(value, run)
                    and key not in scientific_qualified for key, value in run.fields.items() if value in drawn and latest_work[key] in TERMINAL):
                reasons.append(f"unresolved_transcription:{region.id}")
    evidence = {item.id: item for item in run.evidence}
    if len(evidence) != len(run.evidence):
        unavailable("canonical_evidence_identity_collision")
    profiles = {str(item.field_key): item for item in profile.fields}
    fields = {canonical: profiles[research] for research, canonical in field_mapping.items()}
    for key in sorted(KEYS):
        if latest_work[key] not in TERMINAL:
            continue
        value = run.fields[key]
        if (key == IRN and value.state != ValueState.SUPPORTED and fields[key].exception == emu_irn_exception()
                and not any((value.parsed, value.normalized, value.authority_id, value.authority_identity))):
            # The exception keeps the actual unresolved value visible; it does
            # not insert a fictional party or turn operational failure into data.
            continue
        settled = value.normalized or value.parsed or value.literal
        if (value.state != ValueState.SUPPORTED or not settled or
                settled.strip().casefold() in PLACEHOLDERS or (value.literal is None and key not in scientific_qualified and not _raw_grounded(value, run))):
            reasons.append(f"mandatory_unresolved:{key}")
            continue
        if not value.evidence_ids or any(item not in evidence for item in value.evidence_ids):
            reasons.append(f"evidence_missing:{key}")
            continue
        citations = [evidence[item] for item in value.evidence_ids]
        if value.literal is not None and not any(value.literal in item.excerpt for item in citations):
            reasons.append(f"evidence_does_not_support_value:{key}")
        if value.verbatim_by_observation and key not in scientific_qualified and not _raw_grounded(value, run):
            reasons.append(f"raw_reading_grounding_unproved:{key}")
        for layer in ("parsed", "normalized", "authority_id"):
            text = getattr(value, layer)
            if key not in scientific_qualified and text and text != value.literal and not any(
                item.kind in {"authority", "authority_selection", "derived", "lookup"}
                and text in item.excerpt for item in citations
            ):
                reasons.append(f"unsupported_{layer}:{key}")
        if key == IRN and (not value.authority_identity or value.authority_identity.get("module") != "eparties"):
            reasons.append("identified_by_irn_identity_unproved")
    taxon = run.fields["taxon"]
    if latest_work["taxon"] in TERMINAL and (not taxon.authority_id or not any(
        "taxon" in call.field_keys and call.evidence_id in taxon.evidence_ids
        and call.outcome.value == "success" and call.source in fields["taxon"].source_ids
        for call in run.tool_calls
    )):
        reasons.append("taxonomy_unresolved")
    for unit in ("m", "ft"):
        if any(latest_work[f"elevation_{end}_{unit}"] not in TERMINAL for end in ("from", "to")):
            continue
        try:
            lower = run.fields[f"elevation_from_{unit}"]
            upper = run.fields[f"elevation_to_{unit}"]
            values = [Decimal(v.normalized or v.parsed or v.literal or "") for v in (lower, upper)]
            if any(not v.is_finite() for v in values) or values[0] > values[1]:
                reasons.append(f"elevation_range:{unit}")
        except InvalidOperation:
            reasons.append(f"elevation_invalid:{unit}")
    for end in ("from", "to"):
        if any(latest_work[f"elevation_{end}_{unit}"] not in TERMINAL for unit in ("m", "ft")):
            continue
        try:
            metric, imperial = (run.fields[f"elevation_{end}_{unit}"] for unit in ("m", "ft"))
            metres, feet = (Decimal(v.normalized or v.parsed or v.literal or "") for v in (metric, imperial))
            if metres.is_finite() and feet.is_finite() and abs(metres * Decimal("3.28084") - feet) > Decimal("1"):
                reasons.append(f"elevation_units_conflict:{end}")
        except InvalidOperation:
            pass  # The mandatory/range checks above retain missing data.
    if all(latest_work[key] in TERMINAL for key in ("date_visited_from", "date_visited_to", "date_identified")):
        try:
            start, _ = _date_bounds(run.fields["date_visited_from"])
            _, end = _date_bounds(run.fields["date_visited_to"])
            identified, _ = _date_bounds(run.fields["date_identified"])
            today = datetime.fromtimestamp(observed_at, timezone.utc).date()
            if start > end or identified < start or identified > today:
                reasons.append("date_order")
        except (ValueError, OverflowError, OSError):
            reasons.append("date_precision_requires_review")
    identifier = run.fields["fmnh_ins_number"]
    if latest_work["fmnh_ins_number"] in TERMINAL and not re.fullmatch(r"FMNH[- ]?INS[ #]*\d+", identifier.normalized or identifier.parsed or identifier.literal or "", re.I):
        reasons.append("identifier_format")
    return list(dict.fromkeys(reasons))


class CanonicalResearchMaterializerV2:
    def __init__(self, policy: ResearchCanonicalPolicyV2, request_source=None):
        self.policy = ResearchCanonicalPolicyV2.model_validate(policy.model_dump(mode="json"))
        self.request_source = request_source

    async def materialize(self, principal: Principal, prepared: PreparedNativePublication,
            binding: CanonicalBindingV2, prior: Specimen, *, prior_projection, captured_evidence,
            projection_services: CanonicalProjectionServicesV1):
        return await self._materialize(principal, prepared, binding, prior,
            prior_projection=prior_projection, captured_evidence=captured_evidence,
            projection_services=projection_services, bundle=None)

    async def materialize_v2(self, principal: Principal, prepared: PreparedNativePublication,
            binding: CanonicalBindingV2, prior: Specimen, *, bundle: NativeMaterializationInputBundleV2,
            prior_projection, captured_evidence, projection_services: CanonicalProjectionServicesV1):
        if not isinstance(bundle, NativeMaterializationInputBundleV2):
            unavailable("canonical_v2_native_bundle_required")
        return await self._materialize(principal, prepared, binding, prior,
            prior_projection=prior_projection, captured_evidence=captured_evidence,
            projection_services=projection_services, bundle=bundle)

    async def _materialize(self, principal, prepared, binding, prior, *, prior_projection,
            captured_evidence, projection_services, bundle):
        prepared = PreparedNativePublication.model_validate(prepared.model_dump(mode="json"))
        if not isinstance(binding, CanonicalBindingV2):
            unavailable("canonical_v2_binding_required")
        binding = CanonicalBindingV2.model_validate(binding.model_dump(mode="json"))
        reg, scope, checkpoint = binding.registration, prepared.basis.scope, prepared.publication.checkpoints[0]
        if (principal.user_id != prepared.basis.actor_uid or principal.role not in {"operator", "reviewer", "manager", "admin"}
                or principal.scope != prior.scope or str(binding.organization_id) != principal.scope.organization_id
                or str(binding.collection_id) != principal.scope.collection_id or str(binding.specimen_id) != prior.id
                or prior.id != scope.specimen_id or binding.sensitive or scope.sensitive or prior.asset.sensitive):
            raise PermissionError("canonical_materialization_scope_denied")
        if (reg.current_canonical != binding.canonical or prior.version != binding.canonical.record_revision
                or prior.run.id != str(binding.canonical.canonical_run_id) or prior.asset.sha256 != reg.source_sha256
                or canonical_digest(prior.run.profile_snapshot) != reg.canonical_profile_digest
                or reg.job_id != scope.job_id or reg.generation != scope.generation
                or reg.input_digest != scope.input_digest or reg.profile_digest != scope.profile_digest
                or reg.runtime_binding_digest != prepared.basis.binding_digest or reg.job_key != prepared.basis.job_key
                or reg.program_key != prepared.basis.program_key or set(prior.run.fields) != KEYS):
            unavailable("canonical_materialization_basis_stale")
        # Original jobbase remains unchanged; only native V2 causal admission can
        # authorize the current preparation. Never infer CAS from field counts.
        if reg.read_bundle["hold_reasons"] or reg.read_bundle["halted"] or reg.read_bundle["paused"]:
            unavailable("canonical_materialization_operational_hold")
        observed_at = reg.read_bundle["server_time"]
        if type(observed_at) not in {int, float} or not math.isfinite(observed_at) or observed_at <= 0:
            unavailable("canonical_materialization_server_time_unproved")
        if (digest(self.policy) != reg.policy_digest or reg.policy_digest == reg.journal_budget_policy_digest
                or self.policy.canonical_profile_digest != reg.canonical_profile_digest
                or self.policy.research_profile_digest != reg.profile_digest
                or self.policy.source_registry_digest != checkpoint.source_registry_digest
                or reg.semantic_mapping.get("research_policy_contract_version") != self.policy.contract_version
                or reg.semantic_mapping.get("research_policy_origin") != reg.research_policy_origin):
            unavailable("canonical_research_policy_unproved")
        profile = CollectionProfile.model_validate(reg.job["pins"]["profile"])
        if (digest(profile) != reg.profile_digest or len(profile.fields) != 20
                or {row.field_key for row in profile.fields} != set(ALL_FIELDS)
                or profile.organization_id != scope.organization_id or profile.collection_id != scope.collection_id
                or not next(row for row in profile.fields if row.field_key == FieldKey.DATE_IDENTIFIED).mandatory):
            unavailable("canonical_research_profile_unproved")
        if projection_services.projector_sha256 != CANONICAL_PROJECTOR_SHA256:
            unavailable("canonical_projector_source_not_qualified")
        if bundle is None:
            if self.request_source is None or not callable(getattr(self.request_source, "read_v2", None)):
                unavailable("canonical_v2_private_native_context_unavailable")
            context = await self.request_source.read_v2(principal, prepared, binding, prior, prior_projection)
        else:
            context = bundle.target
            prior_projection = canonical_prior_projection_v2(prior_projection, binding.canonical.record_version_id)
        if (not isinstance(context, MaterializationRequestV2) or context.prepared_digest != digest(prepared)
                or context.canonical_snapshot_sha256 != binding.canonical.snapshot_sha256
                or not isinstance(context.lineage_context, CanonicalLineageContextV2)):
            unavailable("canonical_captured_request_unproved")
        lineage = context.lineage_context
        if (lineage.native_prior_snapshot.canonical != binding.canonical or lineage.scope != scope
                or lineage.job != reg.job or lineage.field_mapping != reg.field_mapping or lineage.human_locks != reg.human_locks
                or lineage.original_request != context.request or lineage.tool_results != context.tool_results
                or lineage.prior_projection != tuple(prior_projection)):
            unavailable("canonical_v2_private_native_context_unproved")
        _prior_snapshot(prior, lineage)
        _, original = _checkpoint(lineage, checkpoint)
        if context.request.scope != original.scope or original.resolution.work_state not in {WorkState.RESOLVED, WorkState.WAITING_HUMAN, WorkState.NONBLOCKING_EXCEPTION}:
            unavailable("canonical_operational_or_policy_work_not_publishable")
        validate_checkpoint_resolution_v2(lineage, original)
        from .local_utility_proof_v2 import local_utility_replays_v2
        local_replays = local_utility_replays_v2(context.request, context.tool_results,
            accepted_checkpoint_proof=lineage.accepted_checkpoint_proof)
        for tool in context.tool_results:
            if tool.receipt is None:
                continue  # Exact local parser replay above; no external effect is fabricated.
            if (tool.receipt.scope != original.scope or tool.receipt.effect_status != "completed"
                    or tool.receipt.result_json != result_envelope(tool) or tool.receipt.effect_id not in original.effect_receipt_ids):
                unavailable("canonical_source_result_unproved")
        key = reg.field_mapping[str(checkpoint.field_key)]
        if reg.human_locks[key]:
            unavailable("canonical_field_human_locked")
        contributions = tuple(captured_evidence)
        expected = set(original.resolution.evidence_ids) | set(original.resolution.value.evidence_ids)
        if ({row.evidence.id for row in contributions} != expected or len(contributions) != len(expected)
                or any(not isinstance(row, (CapturedCanonicalEvidenceV1, CapturedCanonicalEvidenceV2)) for row in contributions)):
            unavailable("canonical_captured_evidence_scope_invalid")
        ids = {row.evidence.id: UUID(row.canonical_evidence.id) for row in contributions}
        if len(set(ids.values())) != len(ids) or ids != lineage.evidence_id_mapping:
            unavailable("canonical_evidence_identity_collision")
        result = prior.model_copy(deep=True);result.version += 1
        for item in contributions:
            if (item.canonical_mapping_digest != reg.semantic_mapping_digest
                    or item.source_registry_digest != original.source_registry_digest
                    or item.canonical_run_id != binding.canonical.canonical_run_id):
                unavailable("canonical_captured_evidence_mapping_invalid")
            existing = [row for row in result.run.evidence if row.id == item.canonical_evidence.id]
            if existing and existing != [item.canonical_evidence]:
                unavailable("canonical_evidence_identity_collision")
            if isinstance(item, CapturedCanonicalEvidenceV1) and (item.origin != "existing_canonical" or existing != [item.canonical_evidence]):
                unavailable("canonical_source_capture_v2_requires_native_v2")
            if not existing:
                result.run.evidence.append(item.canonical_evidence.model_copy(deep=True))
            producer = item.canonical_producer
            if producer is not None:
                existing = [row for row in result.run.tool_calls if row.call_key == producer.call_key]
                if existing and existing != [producer]:
                    unavailable("canonical_tool_identity_collision")
                if not existing:
                    result.run.tool_calls.append(producer.model_copy(deep=True))
        result.run.fields[key] = canonical_value_v1(original.resolution, reg.field_mapping, ids)
        research, canonical, operational, human = _work_progress(reg, original, result.run,
            decision_lookup_ids=context.decision_lookup_ids, profile=profile)
        # A held field keeps its prior canonical value and carries its field
        # reason; it neither blocks the record nor needs whole-record grounding.
        held = _policy_held(canonical, profile, reg.field_mapping)
        states = {state for key, state in canonical.items() if key not in held}
        qualified = _qualified_terminal_fields(prior, result, TerminalFieldProofV2(checkpoint, lineage), context.field_lineage_contexts, canonical)
        human = tuple(dict.fromkeys((*human, *_scientific_reasons(result, profile, observed_at,
            latest_work=canonical, field_mapping=reg.field_mapping, scientific_qualified=qualified))))
        ungrounded = KEYS - held - qualified
        if not states & UNFINISHED and ungrounded:
            operational += tuple(f"canonical_field_grounding_unproved:{field}" for field in sorted(ungrounded))
        unfinished = bool(states & UNFINISHED)
        blocked = bool(states & BLOCKED or operational)
        # An unfinished run has no disposition, and an operational failure is a
        # block, never Deferred (docs/execution/CONTRACTS.md:217-246). The stage
        # carries both.
        result.run.disposition = None if unfinished or operational else Disposition.REVIEW if human else Disposition.CLEARED
        result.run.stage = "processing_blocked" if blocked else "research_in_progress" if unfinished else "finalized"
        result.run.reasons = list(dict.fromkeys((*operational, *human)))
        projection = project_canonical_value_v2(principal, prior=prior, result=result, checkpoint=checkpoint, context=lineage)
        tool_rows = tuple(write for item in contributions if isinstance(item, CapturedCanonicalEvidenceV2)
            for write in project_tool_input_lineage_v2(principal, prior=prior, checkpoint=checkpoint, context=lineage, contribution=item))
        result_sha = canonical_digest(result.model_dump(mode="json"))
        disposition = None if result.run.disposition is None else str(result.run.disposition)
        progress = CanonicalProgressReceiptV2(binding_id=reg.binding_id, job_key=reg.job_key, generation=reg.generation,
            prior_canonical=binding.canonical, result_digest=result_sha, policy_digest=reg.policy_digest,
            field_work_digest=digest(reg.job["fields"]), field_mapping_digest=digest(reg.field_mapping),
            research_field_work=research, canonical_field_work=canonical, target_research_field=original.field_key,
            target_canonical_field=key, wire_status="processing_blocked" if blocked else "running" if unfinished else "completed",
            run_stage=result.run.stage, disposition=disposition, operational_reason_codes=operational,
            human_reason_codes=human, exportable=result.run.disposition == Disposition.CLEARED)
        receipt = {"status": "computed", "policy_contract_version": self.policy.contract_version,
            "publication_digest": digest(prepared.publication), "prior_canonical": binding.canonical.model_dump(mode="json"),
            "result_digest": result_sha, "policy_digest": reg.policy_digest, "semantic_mapping_digest": reg.semantic_mapping_digest,
            "field_work_digest": progress.field_work_digest, "field_mapping_digest": progress.field_mapping_digest,
            "exact_field_keys": sorted(KEYS), "progress_receipt_digest": digest(progress),
            "disposition": disposition, "reasons": result.run.reasons, "date_identified_mandatory": True,
            "blanket_human_approval_required": False,
            "local_utility_replays": [proof.as_receipt() for proof in local_replays],
            "lineage_digest": projection.lineage_digest,
            "tool_input_execution_projection_digest": digest([{"operation": row.operation, "variables": row.variables} for row in tool_rows]),
            "prepack_active_graph": copy.deepcopy(prior.active_graph),
            "prepack_native_snapshot_digest": binding.canonical.snapshot_sha256,
            "prepack_full_graph_digest": lineage.prior_snapshot_sha256}
        return CanonicalPolicyMaterializationV2(prepared_digest=digest(prepared), publication_digest=digest(prepared.publication),
            prior_canonical=binding.canonical, source_sha256=reg.source_sha256, canonical_profile_digest=reg.canonical_profile_digest,
            research_profile_digest=reg.profile_digest, runtime_binding_digest=reg.runtime_binding_digest,
            semantic_mapping_digest=reg.semantic_mapping_digest, policy_digest=reg.policy_digest, evidence_id_mapping=ids,
            result=result, result_digest=result_sha, policy_receipt=receipt, policy_receipt_digest=digest(receipt),
            lineage_digest=projection.lineage_digest, progress_receipt=progress, progress_receipt_digest=digest(progress))
