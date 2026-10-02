"""Pure canonical research output producer; source authored, execution UNRUN.

Only the reviewed server factory may construct this producer. The native writer
verifies captured source bodies before calling it and recomputes the projection
afterwards. Installing a protocol or a policy manifest is not live admission.
"""
from __future__ import annotations

import calendar
import copy
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from specimen_digitization.application.domain import (
    Disposition, FieldValue, MANDATORY, OPERATIONAL, Principal, Specimen, ValueState,
)
from specimen_digitization.application.policy import PLACEHOLDERS
from specimen_digitization.application.projection import derived_id
from specimen_digitization.application.storage import digest as canonical_digest

from .compatibility import PublicationUnavailable
from .contracts import (
    ALL_FIELDS, CollectionProfile, Digest, FieldKey, FrozenRecord, SourceResult,
    SpecialistRequest, WorkState, digest,
)
from .evidence import emu_irn_exception, validate_resolution
from .native_canonical import (
    CANONICAL_PROJECTOR_SHA256, CanonicalBindingV1, CanonicalPolicyMaterializationV1,
    CanonicalProjectionServicesV1, CapturedCanonicalEvidenceV1,
    SqlConnectCanonicalResearchWriter, canonical_value_v1,
)
from .publication import PreparedNativePublication
from .sources import result_envelope

KEYS = frozenset(MANDATORY)
IRN = str(FieldKey.IDENTIFIED_BY_IRN)


def unavailable(code: str) -> None:
    raise PublicationUnavailable(code)


class ResearchCanonicalPolicyV1(FrozenRecord):
    """Versioned scientific policy, pinned by trusted owner registration.

    This is distinct from the immutable financial policy. A caller-supplied
    manifest or an unchecked boolean cannot authorize publication.
    """
    contract_version: Literal["research-canonical-policy/v1"] = "research-canonical-policy/v1"
    owner_decisions: tuple[Literal["G1", "G6", "G42", "G43"], ...] = ("G1", "G6", "G42", "G43")
    canonical_profile_digest: Digest
    research_profile_digest: Digest
    source_registry_digest: Digest
    resolution_rule: Literal["verified_resolved_clears_without_blanket_human_approval"] = "verified_resolved_clears_without_blanket_human_approval"
    date_identified_rule: Literal["mandatory"] = "mandatory"
    pending_irn_rule: Literal["qualified_eparties_or_explicit_nonblocking_exception"] = "qualified_eparties_or_explicit_nonblocking_exception"
    evidence_id_rule: Literal["research-canonical-evidence/v1"] = "research-canonical-evidence/v1"
    lookup_dependency_rule: Literal["verified_current_field_dependencies/v1"] = "verified_current_field_dependencies/v1"

    @model_validator(mode="after")
    def exact_decisions(self):
        if self.owner_decisions != ("G1", "G6", "G42", "G43"):
            raise ValueError("research_canonical_owner_decisions_invalid")
        return self


@dataclass(frozen=True)
class MaterializationRequestV1:
    """Private original request/tools from the admitted capture resolver.

    The I4B factory must verify original request/input provenance. This type is
    not an HTTP input and does not claim that the resolver is implemented.
    """
    prepared_digest: str
    canonical_snapshot_sha256: str
    request: SpecialistRequest
    tool_results: tuple[SourceResult, ...]
    # None means that historical lookup attribution is not proved. The I4B
    # resolver may supply an exact immutable set only from verified dependencies.
    decision_lookup_ids: frozenset[str] | None = None


def _date_bounds(value: FieldValue) -> tuple[date, date]:
    text = value.normalized or value.parsed or value.literal or ""
    if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", text):
        raise ValueError("date_precision_unproved")
    parts = [int(part) for part in text.split("-")]
    precision = ("year", "month", "day")[len(parts) - 1]
    if value.precision is not None and value.precision != precision:
        raise ValueError("date_precision_mismatch")
    year, month = parts[0], parts[1] if len(parts) > 1 else 1
    lower = date(year, month, parts[2] if len(parts) > 2 else 1)
    upper = (date(year, 12, 31) if len(parts) == 1 else
             date(year, month, calendar.monthrange(year, month)[1]) if len(parts) == 2 else lower)
    return lower, upper


def _raw_grounded(value: FieldValue, run) -> bool:
    readings = {reading.id: reading for reading in run.observations}
    verbatim = value.verbatim_by_observation
    if not verbatim or not value.settled_observation_ids or not set(value.settled_observation_ids) <= set(verbatim):
        return False
    return all(identifier in readings and text and text in readings[identifier].literal_text
        and readings[identifier].raw_ref and readings[identifier].raw_sha256
        and (value.source_region_id is None or readings[identifier].region_id == value.source_region_id)
        and value.input_source_by_observation.get(identifier, value.input_source) == "raw_reading"
        for identifier, text in verbatim.items())


def _disposition(result: Specimen, profile: CollectionProfile, observed_at: float, *, latest_work=None, decision_lookup_ids=None) -> list[str]:
    """Evaluate all twenty fields, preserving genuine review requirements."""
    run = result.run
    if decision_lookup_ids is not None and not set(decision_lookup_ids) <= {item.id for item in run.lookups}:
        unavailable("canonical_lookup_dependency_mapping_unproved")
    unrecovered = any((decision_lookup_ids is None or item.id in decision_lookup_ids) and item.status in OPERATIONAL and not any(
        later.status.value == "success" and later.provider == item.provider and later.query == item.query
        for later in run.lookups[index + 1:]) for index, item in enumerate(run.lookups))
    if latest_work is not None and any(type(state) is not str or state not in {str(item) for item in WorkState}
            for state in latest_work.values()):
        unavailable("canonical_field_work_mapping_unproved")
    active_failure = any(state in {str(WorkState.PENDING), str(WorkState.RESEARCHING), str(WorkState.WAITING_SOURCE),
        str(WorkState.WAITING_POLICY), str(WorkState.OPERATIONAL_FAILED), str(WorkState.RETRY_SCHEDULED),
        str(WorkState.CANCELLED)} for state in (latest_work or {}).values())
    if run.blocker or unrecovered or active_failure:
        unavailable("canonical_operational_failure_not_human_review")
    reasons: list[str] = [f"research_human_question:{key}" for key, state in (latest_work or {}).items()
        if state == str(WorkState.WAITING_HUMAN)]
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
            if not drawn or any(value.state != ValueState.SUPPORTED or not _raw_grounded(value, run) for value in drawn):
                reasons.append(f"unresolved_transcription:{region.id}")
    evidence = {item.id: item for item in run.evidence}
    if len(evidence) != len(run.evidence):
        unavailable("canonical_evidence_identity_collision")
    fields = {str(item.field_key): item for item in profile.fields}
    for key in sorted(KEYS):
        value = run.fields[key]
        if (key == IRN and value.state != ValueState.SUPPORTED and fields[key].exception == emu_irn_exception()
                and not any((value.parsed, value.normalized, value.authority_id, value.authority_identity))):
            # The exception keeps the actual unresolved value visible; it does
            # not insert a fictional party or turn operational failure into data.
            continue
        settled = value.normalized or value.parsed or value.literal
        if (value.state != ValueState.SUPPORTED or not settled or
                settled.strip().casefold() in PLACEHOLDERS or (value.literal is None and not _raw_grounded(value, run))):
            reasons.append(f"mandatory_unresolved:{key}")
            continue
        if not value.evidence_ids or any(item not in evidence for item in value.evidence_ids):
            reasons.append(f"evidence_missing:{key}")
            continue
        citations = [evidence[item] for item in value.evidence_ids]
        if value.literal is not None and not any(value.literal in item.excerpt for item in citations):
            reasons.append(f"evidence_does_not_support_value:{key}")
        if value.verbatim_by_observation and not _raw_grounded(value, run):
            reasons.append(f"raw_reading_grounding_unproved:{key}")
        for layer in ("parsed", "normalized", "authority_id"):
            text = getattr(value, layer)
            if text and text != value.literal and not any(
                item.kind in {"authority", "authority_selection", "derived", "lookup"}
                and text in item.excerpt for item in citations
            ):
                reasons.append(f"unsupported_{layer}:{key}")
        if key == IRN and (not value.authority_identity or value.authority_identity.get("module") != "eparties"):
            reasons.append("identified_by_irn_identity_unproved")
    taxon = run.fields["taxon"]
    if not taxon.authority_id or not any(
        "taxon" in call.field_keys and call.evidence_id in taxon.evidence_ids
        and call.outcome.value == "success" and call.source in fields["taxon"].source_ids
        for call in run.tool_calls
    ):
        reasons.append("taxonomy_unresolved")
    for unit in ("m", "ft"):
        try:
            lower = run.fields[f"elevation_from_{unit}"]
            upper = run.fields[f"elevation_to_{unit}"]
            values = [Decimal(v.normalized or v.parsed or v.literal or "") for v in (lower, upper)]
            if any(not v.is_finite() for v in values) or values[0] > values[1]:
                reasons.append(f"elevation_range:{unit}")
        except InvalidOperation:
            reasons.append(f"elevation_invalid:{unit}")
    for end in ("from", "to"):
        try:
            metric, imperial = (run.fields[f"elevation_{end}_{unit}"] for unit in ("m", "ft"))
            metres, feet = (Decimal(v.normalized or v.parsed or v.literal or "") for v in (metric, imperial))
            if metres.is_finite() and feet.is_finite() and abs(metres * Decimal("3.28084") - feet) > Decimal("1"):
                reasons.append(f"elevation_units_conflict:{end}")
        except InvalidOperation:
            pass  # The mandatory/range checks above retain missing data.
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
    if not re.fullmatch(r"FMNH[- ]?INS[ #]*\d+", identifier.normalized or identifier.parsed or identifier.literal or "", re.I):
        reasons.append("identifier_format")
    return list(dict.fromkeys(reasons))


class CanonicalResearchMaterializer:
    """Produce a real next canonical version from one verified field checkpoint."""
    def __init__(self, policy: ResearchCanonicalPolicyV1, request_source):
        self.policy = ResearchCanonicalPolicyV1.model_validate(policy.model_dump(mode="json"))
        self.request_source = request_source

    async def materialize(self, principal: Principal, prepared: PreparedNativePublication,
                          binding: CanonicalBindingV1, prior: Specimen, *, prior_projection,
                          captured_evidence, projection_services: CanonicalProjectionServicesV1):
        prepared = PreparedNativePublication.model_validate(prepared.model_dump(mode="json"))
        binding = CanonicalBindingV1.model_validate(binding.model_dump(mode="json"))
        reg, scope, checkpoint = binding.registration, prepared.basis.scope, prepared.publication.checkpoints[0]
        if (principal.user_id != prepared.basis.actor_uid or principal.role not in {"operator", "reviewer", "manager", "admin"}
                or principal.scope != prior.scope or str(binding.organization_id) != principal.scope.organization_id
                or str(binding.collection_id) != principal.scope.collection_id or str(binding.specimen_id) != prior.id
                or prior.id != scope.specimen_id or binding.sensitive or scope.sensitive or prior.asset.sensitive):
            raise PermissionError("canonical_materialization_scope_denied")
        if (reg.base_canonical != binding.canonical or reg.current_canonical != binding.canonical
                or reg.publication_transition is not None or prior.version != binding.canonical.record_revision
                or prior.version != prepared.basis.expected_record_revision
                or prior.run.id != str(binding.canonical.canonical_run_id)
                or canonical_digest(prior.model_dump(mode="json")) != binding.canonical.snapshot_sha256
                or prior.asset.sha256 != reg.source_sha256
                or canonical_digest(prior.run.profile_snapshot) != reg.canonical_profile_digest
                or reg.job_id != scope.job_id or reg.generation != scope.generation
                or reg.input_digest != scope.input_digest or reg.profile_digest != scope.profile_digest
                or reg.runtime_binding_digest != prepared.basis.binding_digest
                or reg.job_key != prepared.basis.job_key or reg.program_key != prepared.basis.program_key
                or set(prior.run.fields) != KEYS):
            unavailable("canonical_materialization_basis_stale")
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
        if (digest(profile) != reg.profile_digest or {item.field_key for item in profile.fields} != set(ALL_FIELDS)
                or len(profile.fields) != 20 or profile.organization_id != scope.organization_id
                or profile.collection_id != scope.collection_id
                or not next(item for item in profile.fields if item.field_key == FieldKey.DATE_IDENTIFIED).mandatory):
            unavailable("canonical_research_profile_unproved")
        if (projection_services.projector_sha256 != CANONICAL_PROJECTOR_SHA256 or not callable(projection_services.projector)
                or not callable(projection_services.locate) or not callable(projection_services.size)):
            unavailable("canonical_projector_source_not_qualified")
        if self.request_source is None:
            unavailable("canonical_captured_request_source_unavailable")
        # The versioned capture interface names this shared pure lineage proof.
        # Old requests retain their actual generation; no scope rebinding.
        capture_scope, _ = SqlConnectCanonicalResearchWriter._capture_lineage(prepared, binding)
        context = await self.request_source.read(principal, prepared, binding)
        if (not isinstance(context, MaterializationRequestV1) or context.prepared_digest != digest(prepared)
                or context.canonical_snapshot_sha256 != binding.canonical.snapshot_sha256
                or context.request.scope != capture_scope or context.request.prompt.digest != checkpoint.prompt_digest
                or context.request.prompt.source_registry_digest != checkpoint.source_registry_digest):
            unavailable("canonical_captured_request_unproved")
        if context.decision_lookup_ids is not None and (not isinstance(context.decision_lookup_ids, frozenset)
                or any(type(identifier) is not str for identifier in context.decision_lookup_ids)):
            unavailable("canonical_lookup_dependency_mapping_unproved")
        if checkpoint.resolution.work_state not in {WorkState.RESOLVED, WorkState.WAITING_HUMAN, WorkState.NONBLOCKING_EXCEPTION}:
            unavailable("canonical_operational_or_policy_work_not_publishable")
        if checkpoint.resolution.value_layer == "derived":
            unavailable("canonical_derived_projection_v1_unavailable")
        validate_resolution(context.request, checkpoint.resolution, context.tool_results)
        for tool in context.tool_results:
            if (tool.receipt is None or tool.receipt.scope != capture_scope or tool.receipt.effect_status != "completed"
                    or tool.receipt.result_json != result_envelope(tool)
                    or tool.receipt.effect_id not in checkpoint.effect_receipt_ids):
                unavailable("canonical_source_result_unproved")
        key = reg.field_mapping[str(checkpoint.field_key)]
        if reg.human_locks[key]:
            unavailable("canonical_field_human_locked")
        cited = set(checkpoint.resolution.value.evidence_ids)
        relations = checkpoint.resolution.value.evidence_relations
        if checkpoint.resolution.value.state == ValueState.SUPPORTED and (
                set(relations) != cited or not any(role in {"supports", "decides"} for role in relations.values())):
            unavailable("canonical_candidate_evidence_relations_unproved")
        old_rows = copy.deepcopy(list(prior_projection))
        if (len(old_rows) != 20 or any(not isinstance(row, dict) for row in old_rows)
                or {row.get("fieldKey") for row in old_rows} != KEYS
                or any(str(row.get("recordVersionId")) != str(binding.canonical.record_version_id) for row in old_rows)):
            unavailable("canonical_prior_projection_unproved")
        contributions = tuple(CapturedCanonicalEvidenceV1.model_validate(item.model_dump(mode="json")) for item in captured_evidence)
        expected = set(checkpoint.resolution.evidence_ids) | set(checkpoint.resolution.value.evidence_ids)
        if len(contributions) != len(expected) or {item.evidence.id for item in contributions} != expected:
            unavailable("canonical_captured_evidence_scope_invalid")
        id_map = {item.evidence.id: UUID(item.canonical_evidence.id) for item in contributions}
        if len(set(id_map.values())) != len(id_map):
            unavailable("canonical_evidence_identity_collision")
        result = prior.model_copy(deep=True)
        result.version += 1
        for item in contributions:
            if (item.canonical_mapping_digest != reg.semantic_mapping_digest
                    or item.source_registry_digest != checkpoint.source_registry_digest
                    or item.canonical_run_id != binding.canonical.canonical_run_id
                    or item.canonical_region_id != item.canonical_evidence.region_id
                    or tuple(str(value) for value in item.canonical_observation_ids) != tuple(item.canonical_evidence.observation_ids)):
                unavailable("canonical_captured_evidence_mapping_invalid")
            if item.origin == "captured_source_result":
                matching_tools = [tool for tool in context.tool_results
                    if tool.model_copy(update={"receipt": None}) == item.source_result
                    and tool.receipt is not None and item.receipt is not None
                    and tool.receipt.effect_id == item.receipt.effect_id
                    and tool.receipt.request_digest == item.receipt.request_digest
                    and tool.receipt.binding_digest == item.receipt.binding_digest
                    and tool.receipt.capture_locator == item.receipt.capture.locator]
                if (item.receipt is None or item.receipt not in prepared.basis.receipts
                        or item.original_specialist_request != context.request
                        or len(matching_tools) != 1
                        or item.evidence not in item.source_result.evidence
                        or item.capture_envelope_digest != item.receipt.capture.sha256
                        or item.raw_capture != item.receipt.raw_capture):
                    unavailable("canonical_source_capture_context_unproved")
                expected_id = derived_id(self.policy.evidence_id_rule, scope.organization_id, scope.collection_id,
                    scope.specimen_id, prior.run.id, item.evidence.id, item.receipt.effect_id, item.evidence.response_digest)
                if item.canonical_evidence.id != expected_id:
                    unavailable("canonical_source_evidence_identity_unproved")
            existing = [row for row in result.run.evidence if row.id == item.canonical_evidence.id]
            if existing and existing != [item.canonical_evidence]:
                unavailable("canonical_evidence_identity_collision")
            if item.origin == "existing_canonical" and existing != [item.canonical_evidence]:
                unavailable("canonical_existing_evidence_unproved")
            if not existing:
                result.run.evidence.append(item.canonical_evidence.model_copy(deep=True))
            producer = item.canonical_producer
            if producer is not None:
                existing_calls = [row for row in result.run.tool_calls if row.call_key == producer.call_key]
                if existing_calls and existing_calls != [producer]:
                    unavailable("canonical_tool_identity_collision")
                if not existing_calls:
                    result.run.tool_calls.append(producer.model_copy(deep=True))
        result.run.fields[key] = canonical_value_v1(checkpoint.resolution, reg.field_mapping, id_map)
        field_work = reg.job.get("fields")
        if (not isinstance(field_work, dict) or set(field_work) != set(reg.field_mapping)
                or any(not isinstance(value, dict) or type(value.get("work_state")) is not str
                    or value["work_state"] not in {str(item) for item in WorkState} for value in field_work.values())
                or field_work[str(checkpoint.field_key)]["work_state"] != str(checkpoint.resolution.work_state)):
            unavailable("canonical_field_work_mapping_unproved")
        latest_work = {reg.field_mapping[key]: value.get("work_state") for key, value in field_work.items()}
        reasons = _disposition(result, profile, reg.read_bundle["server_time"], latest_work=latest_work,
            decision_lookup_ids=context.decision_lookup_ids)
        if checkpoint.resolution.work_state == WorkState.WAITING_HUMAN:
            reasons.append(f"research_human_question:{key}")
        result.run.reasons = list(dict.fromkeys(reasons))
        result.run.disposition = Disposition.REVIEW if result.run.reasons else Disposition.CLEARED
        result.run.stage = "finalized"
        projected = projection_services.projector(result, projection_services.locate, projection_services.size, principal.user_id)
        records = [row.variables for row in projected if row.operation == "AppendRecordVersionV2"]
        rows = sorted([row.variables for row in projected if row.operation == "AppendResolvedFieldV2"], key=lambda row: row["fieldKey"])
        if len(records) != 1 or len(rows) != 20 or {row["fieldKey"] for row in rows} != KEYS:
            unavailable("canonical_full_projection_unavailable")
        if result.run.fields[key].state == ValueState.SUPPORTED and next(row for row in rows if row["fieldKey"] == key).get("candidateId") is None:
            unavailable("canonical_supported_projection_unavailable")
        old_by_key = {row["fieldKey"]: row for row in old_rows}
        for row in rows:
            if row["fieldKey"] != key and any(row.get(part) != old_by_key[row["fieldKey"]].get(part) for part in ("candidateId", "state", "fieldGroup")):
                unavailable("canonical_retained_projection_changed")
        result_sha = canonical_digest(result.model_dump(mode="json"))
        receipt = {"status": "computed", "policy_contract_version": self.policy.contract_version,
                   "publication_digest": digest(prepared.publication), "prior_canonical": binding.canonical.model_dump(mode="json"),
                   "result_digest": result_sha, "policy_digest": reg.policy_digest,
                   "semantic_mapping_digest": reg.semantic_mapping_digest, "exact_field_keys": sorted(KEYS),
                   "disposition": str(result.run.disposition), "reasons": result.run.reasons,
                   "date_identified_mandatory": True, "blanket_human_approval_required": False,
                   "decision_lookup_ids": sorted(context.decision_lookup_ids) if context.decision_lookup_ids is not None else None}
        lineage = {"prior_fields": sorted(old_rows, key=lambda row: row["fieldKey"]), "fields": rows,
                   "evidence_id_mapping": {key: str(value) for key, value in id_map.items()},
                   "before_fields": {key: value.model_dump(mode="json") for key, value in prior.run.fields.items()},
                   "after_fields": {key: value.model_dump(mode="json") for key, value in result.run.fields.items()},
                   "human_locks": reg.human_locks}
        return CanonicalPolicyMaterializationV1(prepared_digest=digest(prepared), publication_digest=digest(prepared.publication),
            prior_canonical=binding.canonical, source_sha256=reg.source_sha256, canonical_profile_digest=reg.canonical_profile_digest,
            research_profile_digest=reg.profile_digest, runtime_binding_digest=reg.runtime_binding_digest,
            semantic_mapping_digest=reg.semantic_mapping_digest, policy_digest=reg.policy_digest,
            evidence_id_mapping=id_map, result=result, result_digest=result_sha, policy_receipt=receipt,
            policy_receipt_digest=digest(receipt), lineage_digest=digest(lineage))
