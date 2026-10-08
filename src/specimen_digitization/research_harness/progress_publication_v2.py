"""Disjoint, target-free native progress contracts; scientific receipts stay intact."""
from __future__ import annotations

import copy
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .contracts import ALL_FIELDS, Digest, FrozenRecord, ResearchScope, WorkState, digest
from .native_canonical import CANONICAL_KEYS, CanonicalIdentityV1, CanonicalPolicyMaterializationV1, fail
from .persistence import Lease
from .compatibility import PublishedResearch

PROGRESS_OPERATION_V2 = "research-progress-publication/v2"
MAX_CAUSAL_RECEIPTS = 64
MAX_SCIENTIFIC_RECEIPTS = 20
MAX_PROGRESS_RECEIPTS = 44


class ProgressPublicationV2(FrozenRecord):
    contract_version: Literal["research-progress-only/v2"] = "research-progress-only/v2"
    scope: ResearchScope
    field_work_digest: Digest
    field_mapping_digest: Digest
    canonical_anchor: CanonicalIdentityV1


class ProgressBasisV2(FrozenRecord):
    scope: ResearchScope
    actor_uid: str = Field(min_length=1)
    job_key: Digest
    program_key: str = Field(min_length=1)
    binding_digest: Digest
    pins_digest: Digest
    field_work_digest: Digest
    field_mapping_digest: Digest
    policy_digest: Digest
    human_locks: dict[str, bool]
    expected_record_revision: int = Field(strict=True, ge=1)
    lease: Lease
    state_revision: int = Field(strict=True, ge=1)
    state_digest: Digest
    publication_outbox_key: str
    native_guard_digest: Digest

    @model_validator(mode="after")
    def current_basis(self):
        if (set(self.human_locks) != CANONICAL_KEYS or any(type(v) is not bool for v in self.human_locks.values())
            or self.lease.job_key != self.job_key or self.lease.generation != self.scope.generation):
            fail("native_progress_basis_unproved")
        return self


class PreparedNativeProgressV2(FrozenRecord):
    contract_version: Literal["prepared-native-progress/v2"] = "prepared-native-progress/v2"
    basis: ProgressBasisV2
    publication: ProgressPublicationV2
    guard: dict

    @model_validator(mode="after")
    def matched(self):
        if (self.basis.scope != self.publication.scope
            or self.basis.field_work_digest != self.publication.field_work_digest
            or self.basis.field_mapping_digest != self.publication.field_mapping_digest
            or self.basis.expected_record_revision != self.publication.canonical_anchor.record_revision
            or self.guard.get("operation_kind") != "progress_only"
            or digest(self.guard) != self.basis.native_guard_digest):
            fail("native_progress_prepared_unproved")
        return self


class ProgressOnlyReceiptV2(FrozenRecord):
    contract_version: Literal["canonical-progress-only/v2"] = "canonical-progress-only/v2"
    binding_id: UUID
    job_key: Digest
    generation: int = Field(strict=True, ge=1)
    prior_canonical: CanonicalIdentityV1
    result_digest: Digest
    policy_digest: Digest
    field_work_digest: Digest
    field_mapping_digest: Digest
    research_field_work: dict[str, str]
    canonical_field_work: dict[str, str]
    wire_status: Literal["processing_blocked", "completed"]
    run_stage: Literal["processing_blocked", "finalized"]
    disposition: Literal["cleared", "needs_human_review"] | None
    operational_reason_codes: tuple[str, ...]
    human_reason_codes: tuple[str, ...]
    exportable: bool = Field(strict=True)

    @model_validator(mode="after")
    def honest(self):
        if (set(self.research_field_work) != {str(k) for k in ALL_FIELDS}
            or set(self.canonical_field_work) != CANONICAL_KEYS
            or any(type(s) is not str or s not in {str(w) for w in WorkState}
                for s in (*self.research_field_work.values(), *self.canonical_field_work.values()))
            or any(s in {"pending", "researching", "retry_scheduled"} for s in (*self.research_field_work.values(), *self.canonical_field_work.values()))
            or len(set(self.operational_reason_codes)) != len(self.operational_reason_codes)
            or len(set(self.human_reason_codes)) != len(self.human_reason_codes)
            or any(not s for s in (*self.operational_reason_codes, *self.human_reason_codes))):
            fail("native_progress_mapping_unproved")
        held = {k for k, s in self.canonical_field_work.items()
            if s == "waiting_policy" and f"mandatory_unresolved:{k}" in self.human_reason_codes}
        blocked = {s for k, s in self.canonical_field_work.items() if k not in held}
        if blocked & {"waiting_source", "waiting_policy", "operational_failed", "cancelled"} or self.operational_reason_codes:
            if self.wire_status != "processing_blocked" or self.run_stage != "processing_blocked" or self.disposition is not None or self.exportable:
                fail("native_progress_false_completion")
        elif (self.wire_status != "completed" or self.run_stage != "finalized"
            or self.disposition not in {"cleared", "needs_human_review"}
            or self.exportable != (self.disposition == "cleared")
            or ("waiting_human" in blocked or self.human_reason_codes) and self.disposition != "needs_human_review"):
            fail("native_progress_policy_unproved")
        return self


class ProgressMaterializationV2(CanonicalPolicyMaterializationV1):
    contract_version: Literal["canonical-progress-materialization/v2"] = "canonical-progress-materialization/v2"
    progress_receipt: ProgressOnlyReceiptV2
    progress_receipt_digest: Digest

    @model_validator(mode="after")
    def current_result(self):
        p = self.progress_receipt
        if (digest(p) != self.progress_receipt_digest or p.prior_canonical != self.prior_canonical
            or p.result_digest != self.result_digest or p.policy_digest != self.policy_digest
            or self.result.run.stage != p.run_stage
            or (None if self.result.run.disposition is None else str(self.result.run.disposition)) != p.disposition):
            fail("native_progress_materialization_unproved")
        return self


def progress_basis_digest(prepared):
    b = prepared.basis
    return digest({"operation": PROGRESS_OPERATION_V2, "scope": b.scope.model_dump(mode="json"),
        "job_key": b.job_key, "program_key": b.program_key, "binding_digest": b.binding_digest,
        "pins_digest": b.pins_digest, "field_work_digest": b.field_work_digest,
        "field_mapping_digest": b.field_mapping_digest, "policy_digest": b.policy_digest,
        "human_locks": b.human_locks, "canonical_anchor": prepared.publication.canonical_anchor.model_dump(mode="json")})


def progress_operation_digest(actor, key, request_identity, basis_digest):
    return digest({"operation": PROGRESS_OPERATION_V2, "actor_uid": actor, "idempotency_key": key,
        "server_request_identity_digest": request_identity, "progress_basis_digest": basis_digest})


class ProgressIntentV2(FrozenRecord):
    contract_version: Literal["research-progress-intent/v2"] = "research-progress-intent/v2"
    id: UUID
    actor_uid: str
    server_request_identity_digest: Digest
    idempotency_key: Digest
    operation_digest: Digest
    progress_basis_digest: Digest
    original_base: CanonicalIdentityV1
    binding_id: UUID
    job_key: Digest
    program_key: str
    import_proof_id: UUID
    import_proof_digest: Digest
    authority_digest: Digest
    human_locks: dict[str, bool]
    original_prepared: PreparedNativeProgressV2

    @model_validator(mode="after")
    def immutable(self):
        b = self.original_prepared.basis
        if (b.actor_uid != self.actor_uid or b.job_key != self.job_key or b.program_key != self.program_key
            or self.human_locks != b.human_locks or progress_basis_digest(self.original_prepared) != self.progress_basis_digest
            or self.original_base.canonical_run_id != self.original_prepared.publication.canonical_anchor.canonical_run_id
            or progress_operation_digest(self.actor_uid, self.idempotency_key, self.server_request_identity_digest,
                self.progress_basis_digest) != self.operation_digest):
            fail("native_progress_intent_unproved")
        return self


class ProgressPreparationV2(FrozenRecord):
    contract_version: Literal["research-progress-preparation/v2"] = "research-progress-preparation/v2"
    id: UUID
    intent_id: UUID
    ordinal: int = Field(strict=True, ge=1, le=20)
    prior_preparation_id: UUID | None
    prior_preparation_digest: Digest | None
    anchor: CanonicalIdentityV1
    anchor_receipt_id: UUID | None
    anchor_chain_digest: Digest
    anchor_registration_revision: int = Field(strict=True, ge=1)
    state_revision: int = Field(strict=True, ge=1)
    state_digest: Digest
    expected_state: dict
    authority_digest: Digest
    human_locks: dict[str, bool]
    progress_basis_digest: Digest
    prepared: PreparedNativeProgressV2
    admission_digest: Digest

    @model_validator(mode="after")
    def captured(self):
        if (digest(self.expected_state) != self.state_digest
            or self.state_digest != self.prepared.basis.state_digest
            or self.state_revision != self.prepared.basis.state_revision
            or self.anchor != self.prepared.publication.canonical_anchor
            or self.human_locks != self.prepared.basis.human_locks
            or self.progress_basis_digest != progress_basis_digest(self.prepared)
            or (self.ordinal == 1) != (self.prior_preparation_id is None and self.prior_preparation_digest is None)
            or digest(self.model_dump(mode="json", exclude={"admission_digest"})) != self.admission_digest):
            fail("native_progress_preparation_unproved")
        return self


def progress_outbox_completion(state, key, native_commit):
    result = copy.deepcopy(state)
    event = result.get("outbox", {}).get(key)
    if (not isinstance(event, dict) or event.get("kind") != "canonical_publication_required"
        or event.get("delivered") is not False or event.get("guard", {}).get("operation_kind") != "progress_only"):
        fail("native_progress_outbox_unproved")
    event["delivered"] = True
    event["canonical_commit"] = copy.deepcopy(native_commit)
    return result


class NativeProgressCausalReceiptV2(FrozenRecord):
    contract_version: Literal["native-canonical-progress/v2"] = "native-canonical-progress/v2"
    receipt_id: UUID
    intent_id: UUID
    winning_preparation_id: UUID
    operation_digest: Digest
    progress_basis_digest: Digest
    preparation_digest: Digest
    admission_digest: Digest
    authority_digest: Digest
    input_digest: Digest
    profile_digest: Digest
    runtime_binding_digest: Digest
    actor_uid: str
    scope_identity: dict
    binding_id: UUID
    job_key: Digest
    program_key: str
    import_proof_id: UUID
    import_proof_digest: Digest
    original_base: CanonicalIdentityV1
    used: CanonicalIdentityV1
    resulting: CanonicalIdentityV1
    parent_receipt_id: UUID | None
    parent_chain_digest: Digest
    chain_digest: Digest
    human_locks: dict[str, bool]
    before_state_revision: int = Field(strict=True, ge=1)
    after_state_revision: int = Field(strict=True, ge=1)
    before_state_digest: Digest
    after_state_digest: Digest
    before_state: dict
    after_state: dict
    publication_outbox_key: str
    native_commit: dict
    before_registration_revision: int = Field(strict=True, ge=1)
    after_registration_revision: int = Field(strict=True, ge=1)
    projection_digest: Digest
    prior_projection_digest: Digest
    preserved_projection_digest: Digest
    projection_count: Literal[20]
    policy_receipt_digest: Digest
    lineage_digest: Digest
    progress_receipt: ProgressOnlyReceiptV2
    progress_receipt_digest: Digest
    audit_id: UUID
    outbox_id: UUID

    @model_validator(mode="after")
    def transition(self):
        from .native_canonical import strict_history_scope_v1
        strict_history_scope_v1(self.scope_identity)
        p = self.progress_receipt
        if (self.resulting.record_revision != self.used.record_revision + 1
            or self.resulting.canonical_run_id != self.used.canonical_run_id
            or self.original_base.canonical_run_id != self.used.canonical_run_id
            or self.after_state_revision != self.before_state_revision + 1
            or self.after_registration_revision != self.before_registration_revision + 1
            or set(self.human_locks) != CANONICAL_KEYS or any(type(v) is not bool for v in self.human_locks.values())
            or digest(p) != self.progress_receipt_digest or p.prior_canonical != self.used
            or p.binding_id != self.binding_id or p.job_key != self.job_key or p.generation != self.scope_identity["generation"]
            or p.field_work_digest != digest(self.before_state.get("jobs", {}).get(self.job_key, {}).get("fields"))
            or digest(self.before_state) != self.before_state_digest or digest(self.after_state) != self.after_state_digest
            or progress_outbox_completion(self.before_state, self.publication_outbox_key, self.native_commit) != self.after_state
            or self.chain_digest != progress_chain_digest(self)):
            fail("native_progress_causal_receipt_unproved")
        return self


def progress_chain_digest(receipt):
    return digest({"operation_kind": "progress_only", "parent": receipt.parent_chain_digest,
        "receipt": str(receipt.receipt_id), "operation": receipt.operation_digest,
        "used": receipt.used.model_dump(mode="json"), "resulting": receipt.resulting.model_dump(mode="json"),
        "preparation": receipt.preparation_digest, "lineage": receipt.lineage_digest,
        "progress": receipt.progress_receipt_digest, "preserved_projection": receipt.preserved_projection_digest})


class ProgressAttemptV2(FrozenRecord):
    id: UUID
    preparation_id: UUID
    operation_digest: Digest
    preparation_digest: Digest
    admission_digest: Digest


class RetainedProgressIntentV2(FrozenRecord):
    original: ProgressIntentV2
    preparations: tuple[ProgressPreparationV2, ...]
    attempt: ProgressAttemptV2 | None

    @model_validator(mode="after")
    def immutable_history(self):
        prior = None
        seen = set()
        if len(self.preparations) > 20:
            fail("native_progress_preparation_inventory_unproved")
        for ordinal, prepared in enumerate(self.preparations, 1):
            if (prepared.intent_id != self.original.id or prepared.ordinal != ordinal or prepared.id in seen
                or prepared.progress_basis_digest != self.original.progress_basis_digest
                or prepared.authority_digest != self.original.authority_digest
                or prepared.human_locks != self.original.human_locks
                or prepared.prior_preparation_id != (None if prior is None else prior.id)
                or prepared.prior_preparation_digest != (None if prior is None else digest(prior))):
                fail("native_progress_preparation_inventory_unproved")
            seen.add(prepared.id)
            prior = prepared
        if self.attempt is not None:
            found = [p for p in self.preparations if p.id == self.attempt.preparation_id]
            if (len(found) != 1 or self.attempt.operation_digest != self.original.operation_digest
                or self.attempt.preparation_digest != digest(found[0])
                or self.attempt.admission_digest != found[0].admission_digest):
                fail("native_progress_attempt_unproved")
        return self


class NativeProgressResultV2(FrozenRecord):
    receipt_version: Literal["native-canonical-progress/v2"] = "native-canonical-progress/v2"
    published: PublishedResearch
    causal: NativeProgressCausalReceiptV2
    snapshot_sha256: Digest
    opaque_record_version: str
    replayed: bool = Field(strict=True)

    @model_validator(mode="after")
    def matched(self):
        if (self.published.record_revision != self.causal.resulting.record_revision
            or self.snapshot_sha256 != self.causal.resulting.snapshot_sha256
            or self.opaque_record_version != self.causal.resulting.host_record_version_id):
            fail("native_progress_result_unproved")
        return self
