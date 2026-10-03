"""Causal sibling SOURCE only; V1 and immutable original job base stay unchanged.

Original intent is independent from append-only current admission/preparation.
No namespace imports, parsing, tests or native transaction have been qualified.
"""
from __future__ import annotations

import copy
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .contracts import Digest, FieldKey, FrozenRecord, FieldCheckpoint, digest
from .native_canonical import CANONICAL_KEYS, CanonicalIdentityV1, fail, strict_history_scope_v1
from .publication import PreparedNativePublication, _native_checkpoint

OPERATION_V2="research-publication/v2"
Positive=Annotated[int,Field(strict=True,ge=1)]


def json_model(value):
    return value.model_dump(mode="json")


class CanonicalSourceBasisV2(FrozenRecord):
    field_key: FieldKey
    canonical_field_key: str
    checkpoint_id: Digest
    checkpoint_digest: Digest
    checkpoint_revision: Positive
    resolution_digest: Digest
    scientific_source_digest: Digest | None = None
    candidate_id: UUID
    source_record_version_id: UUID
    projection_record_version_id: UUID
    canonical_run_id: UUID
    evidence_ids: tuple[UUID,...]
    lineage_digest: Digest


class ScientificIntentV2(FrozenRecord):
    contract_version: Literal["research-publication-intent/v2"]="research-publication-intent/v2"
    id: UUID
    actor_uid: str=Field(min_length=1)
    server_request_identity_digest: Digest
    idempotency_key: Digest
    operation_digest: Digest
    scientific_intent_digest: Digest
    original_base: CanonicalIdentityV1
    binding_id: UUID
    job_key: Digest
    program_key: str=Field(min_length=1)
    import_proof_id: UUID
    import_proof_digest: Digest
    authority_digest: Digest
    changed_field: str
    human_locks: dict[str,bool]
    dependency_sources: tuple[CanonicalSourceBasisV2,...]
    original_prepared: PreparedNativePublication

    @model_validator(mode="after")
    def exact_science(self):
        p=self.original_prepared
        if (self.actor_uid!=p.basis.actor_uid or self.job_key!=p.basis.job_key
            or self.program_key!=p.basis.program_key
            or self.original_base.record_revision!=p.basis.expected_record_revision
            or self.changed_field not in CANONICAL_KEYS or set(self.human_locks)!=CANONICAL_KEYS
            or any(type(value) is not bool for value in self.human_locks.values())
            or len({source.field_key for source in self.dependency_sources})!=len(self.dependency_sources)
            or {source.field_key for source in self.dependency_sources}!={d.field_key for d in p.basis.dependencies}
            or self.scientific_intent_digest!=scientific_basis_digest(p,self.dependency_sources)
            or self.operation_digest!=operation_digest(self.actor_uid,self.idempotency_key,
                self.server_request_identity_digest,self.scientific_intent_digest)):
            fail("native_v2_scientific_intent_invalid")
        return self


class CanonicalProgressReceiptV2(FrozenRecord):
    """Trusted I4A whole20 proof; no model/caller-supplied progress authority."""
    contract_version: Literal["canonical-research-progress/v2"]="canonical-research-progress/v2"
    binding_id: UUID
    job_key: Digest
    generation: Positive
    prior_canonical: CanonicalIdentityV1
    result_digest: Digest
    policy_digest: Digest
    field_work_digest: Digest
    field_mapping_digest: Digest
    research_field_work: dict[str,str]
    canonical_field_work: dict[str,str]
    target_research_field: FieldKey
    target_canonical_field: str
    wire_status: Literal["running","processing_blocked","completed"]
    run_stage: str
    # None while research is unfinished or blocked: neither is a disposition.
    disposition: Literal["cleared","needs_human_review"] | None
    operational_reason_codes: tuple[str,...]
    human_reason_codes: tuple[str,...]
    exportable: bool=Field(strict=True)

    @model_validator(mode="after")
    def honest_progress(self):
        from .contracts import ALL_FIELDS,WorkState
        if (set(self.research_field_work)!={str(k) for k in ALL_FIELDS}
            or set(self.canonical_field_work)!=CANONICAL_KEYS
            or any(type(state) is not str or state not in {str(s) for s in WorkState}
                for state in (*self.research_field_work.values(),*self.canonical_field_work.values()))
            or self.target_canonical_field not in CANONICAL_KEYS
            or len(set(self.operational_reason_codes))!=len(self.operational_reason_codes)
            or len(set(self.human_reason_codes))!=len(self.human_reason_codes)
            or any(not reason for reason in (*self.operational_reason_codes,*self.human_reason_codes))):
            fail("native_v2_progress_mapping_unproved")
        blocked={"waiting_source","waiting_policy","operational_failed","retry_scheduled","cancelled"}
        unfinished=blocked|{"pending","researching"}
        # A field held on a policy the profile declares missing carries its field
        # reason and goes to needs human review; it is never cleared.
        held={key for key,state in self.canonical_field_work.items()
            if state=="waiting_policy" and f"mandatory_unresolved:{key}" in self.human_reason_codes}
        values={state for key,state in self.canonical_field_work.items() if key not in held}
        if values&unfinished or self.operational_reason_codes:
            expected="processing_blocked" if values&blocked or self.operational_reason_codes else "running"
            stage="processing_blocked" if expected=="processing_blocked" else "research_in_progress"
            if self.disposition is not None or self.wire_status!=expected or self.run_stage!=stage or self.exportable:
                fail("native_v2_progress_false_completion")
        elif self.wire_status!="completed" or self.disposition not in {"cleared","needs_human_review"} or self.exportable!=(self.disposition=="cleared"):
            fail("native_v2_final_policy_unproved")
        elif ("waiting_human" in values or self.human_reason_codes) and self.disposition!="needs_human_review":
            fail("native_v2_final_human_review_required")
        return self


class NativeCausalReceiptV2(FrozenRecord):
    contract_version: Literal["native-canonical-publication/v2"]="native-canonical-publication/v2"
    receipt_id: UUID
    intent_id: UUID
    winning_preparation_id: UUID
    operation_digest: Digest
    scientific_intent_digest: Digest
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
    changed_field: str
    dependency_sources: tuple[CanonicalSourceBasisV2,...]
    human_locks: dict[str,bool]
    before_state_revision: Positive
    after_state_revision: Positive
    before_state_digest: Digest
    after_state_digest: Digest
    before_state: dict
    after_state: dict
    publication_outbox_key: str
    checkpoint_outbox_key: str
    native_commit: dict
    before_registration_revision: Positive
    after_registration_revision: Positive
    projection_digest: Digest
    prior_projection_digest: Digest
    projection_count: Literal[20]
    policy_receipt_digest: Digest
    lineage_digest: Digest
    progress_receipt: CanonicalProgressReceiptV2
    progress_receipt_digest: Digest
    audit_id: UUID
    outbox_id: UUID

    @model_validator(mode="after")
    def transition(self):
        strict_history_scope_v1(self.scope_identity)
        if (self.resulting.record_revision!=self.used.record_revision+1
            or self.resulting.canonical_run_id!=self.used.canonical_run_id
            or self.original_base.canonical_run_id!=self.used.canonical_run_id
            or self.after_state_revision!=self.before_state_revision+1
            or self.after_registration_revision!=self.before_registration_revision+1
            or self.changed_field not in CANONICAL_KEYS or set(self.human_locks)!=CANONICAL_KEYS
            or any(type(v) is not bool for v in self.human_locks.values())
            or digest(self.progress_receipt)!=self.progress_receipt_digest
            or self.progress_receipt.prior_canonical!=self.used or self.progress_receipt.binding_id!=self.binding_id
            or self.progress_receipt.job_key!=self.job_key or self.progress_receipt.generation!=self.scope_identity["generation"]
            or self.progress_receipt.target_canonical_field!=self.changed_field
            or self.progress_receipt.field_work_digest!=digest(self.before_state.get("jobs",{}).get(self.job_key,{}).get("fields"))
            or digest(self.before_state)!=self.before_state_digest or digest(self.after_state)!=self.after_state_digest):
            fail("native_v2_causal_receipt_invalid")
        expected=outbox_completion(self.before_state,self.publication_outbox_key,self.checkpoint_outbox_key,self.native_commit)
        if expected!=self.after_state or self.chain_digest!=chain_digest(self):
            fail("native_v2_causal_delta_invalid")
        return self


class PreparationV2(FrozenRecord):
    contract_version: Literal["research-publication-preparation/v2"]="research-publication-preparation/v2"
    id: UUID
    intent_id: UUID
    ordinal: Positive
    prior_preparation_id: UUID | None
    prior_preparation_digest: Digest | None
    mode: Literal["NEW_AFTER_PROGRESS","CAPTURED_BEFORE_SIBLING"]
    anchor: CanonicalIdentityV1
    anchor_receipt_id: UUID | None
    anchor_chain_digest: Digest
    anchor_registration_revision: Positive
    state_revision: Positive
    state_digest: Digest
    expected_state: dict
    source_basis: tuple[CanonicalSourceBasisV2,...]
    authority_digest: Digest
    human_locks: dict[str,bool]
    scientific_intent_digest: Digest
    prepared: PreparedNativePublication
    admission_digest: Digest

    @model_validator(mode="after")
    def captured(self):
        if (self.ordinal>20 or digest(self.expected_state)!=self.state_digest or self.state_revision!=self.prepared.basis.state_revision
            or self.state_digest!=self.prepared.basis.state_digest
            or self.scientific_intent_digest!=scientific_basis_digest(self.prepared,self.source_basis)
            or set(self.human_locks)!=CANONICAL_KEYS or any(type(v) is not bool for v in self.human_locks.values())
            or (self.ordinal==1)!=(self.prior_preparation_id is None and self.prior_preparation_digest is None)):
            fail("native_v2_preparation_invalid")
        if digest(self.model_dump(mode="json",exclude={"admission_digest"}))!=self.admission_digest:
            fail("native_v2_admission_invalid")
        return self


def scientific_basis_digest(prepared,sources):
    b=prepared.basis;checkpoint=prepared.publication.checkpoints[0]
    return digest({"scope":json_model(b.scope),"field":str(b.field_key),"checkpoint":json_model(checkpoint),
        "original_scope":json_model(b.original_scope),"original_typed_checkpoint_digest":b.original_typed_checkpoint_digest,
        "reused":b.reused,"history_digest":b.history_digest,"source_binding_digest":b.source_binding_digest,
        "dependencies":[json_model(item) for item in b.dependencies],"source_basis":[json_model(item) for item in sources],
        "receipts":[json_model(item) for item in b.receipts],"binding_digest":b.binding_digest,"pins_digest":b.pins_digest,
        "job_key":b.job_key,"program_key":b.program_key,"original_expected_cas":b.expected_record_revision,
        "lease":json_model(b.lease),"native_guard_digest":b.native_guard_digest,
        "checkpoint_id":b.checkpoint_id,"checkpoint_digest":b.checkpoint_digest,"typed_checkpoint_digest":b.typed_checkpoint_digest,
        "checkpoint_outbox_key":b.checkpoint_outbox_key,"publication_outbox_key":b.publication_outbox_key})


def operation_digest(actor,key,request_identity,science):
    return digest({"operation":OPERATION_V2,"actor_uid":actor,"idempotency_key":key,
        "server_request_identity_digest":request_identity,"scientific_intent_digest":science})


def genesis_digest(binding_id,base):
    return digest({"binding_id":str(binding_id),"base":json_model(base)})


def chain_digest(receipt):
    return digest({"parent":receipt.parent_chain_digest,"receipt":str(receipt.receipt_id),
        "operation":receipt.operation_digest,"used":json_model(receipt.used),"resulting":json_model(receipt.resulting),
        "field":receipt.changed_field,"preparation":receipt.preparation_digest,"lineage":receipt.lineage_digest})


def outbox_completion(state,publication_key,checkpoint_key,native_commit):
    result=copy.deepcopy(state)
    try:
        publication=result["outbox"][publication_key];checkpoint=result["outbox"][checkpoint_key]
        if publication["delivered"] is not False or checkpoint["delivered"] is not False:
            fail("native_v2_outbox_not_pending")
        publication["delivered"]=True;checkpoint["delivered"]=True
        publication["canonical_commit"]=copy.deepcopy(native_commit)
    except (KeyError,TypeError):
        fail("native_v2_outbox_unproved")
    return result


def verify_chain(intent,base,current,head_receipt_id,head_chain_digest,chain):
    if base!=intent.original_base or len(chain)>20:
        fail("native_v2_original_base_unproved")
    previous=base;parent=None;chain_sha=genesis_digest(intent.binding_id,base);seen=set()
    identity={key:getattr(intent.original_prepared.basis.scope,key) for key in
        ("organization_id","collection_id","specimen_id","job_id","generation")}
    for receipt in chain:
        if (receipt.used!=previous or receipt.parent_receipt_id!=parent or receipt.parent_chain_digest!=chain_sha
            or receipt.original_base!=base or receipt.binding_id!=intent.binding_id or receipt.scope_identity!=identity
            or receipt.actor_uid!=intent.actor_uid or receipt.job_key!=intent.job_key or receipt.program_key!=intent.program_key
            or receipt.import_proof_id!=intent.import_proof_id or receipt.import_proof_digest!=intent.import_proof_digest
            or receipt.authority_digest!=intent.authority_digest
            or receipt.input_digest!=intent.original_prepared.basis.scope.input_digest
            or receipt.profile_digest!=intent.original_prepared.basis.scope.profile_digest
            or receipt.runtime_binding_digest!=intent.original_prepared.basis.binding_digest
            or receipt.changed_field in seen):
            fail("native_v2_causal_chain_unproved")
        seen.add(receipt.changed_field);previous=receipt.resulting;parent=receipt.receipt_id;chain_sha=receipt.chain_digest
    if previous!=current or parent!=head_receipt_id or chain_sha!=head_chain_digest:
        fail("native_v2_current_pointer_unproved")
    return tuple(chain)


def verify_admission(intent,preparation,current,head_id,chain_sha,chain,state_revision,state,registration_revision,job):
    if (preparation.intent_id!=intent.id or preparation.scientific_intent_digest!=intent.scientific_intent_digest
        or scientific_basis_digest(preparation.prepared,preparation.source_basis)!=intent.scientific_intent_digest
        or preparation.source_basis!=intent.dependency_sources or preparation.authority_digest!=intent.authority_digest
        or preparation.human_locks!=intent.human_locks):
        fail("native_v2_same_science_unproved")
    verify_chain(intent,intent.original_base,current,head_id,chain_sha,chain)
    if any(receipt.changed_field==intent.changed_field for receipt in chain):
        fail("native_v2_target_already_native_published")
    anchors=[-1] if preparation.anchor==intent.original_base else [i for i,row in enumerate(chain) if row.resulting==preparation.anchor]
    if len(anchors)!=1:
        fail("native_v2_preparation_anchor_unproved")
    index=anchors[0];anchor_id=None if index==-1 else chain[index].receipt_id
    anchor_sha=genesis_digest(intent.binding_id,intent.original_base) if index==-1 else chain[index].chain_digest
    if anchor_id!=preparation.anchor_receipt_id or anchor_sha!=preparation.anchor_chain_digest:
        fail("native_v2_preparation_anchor_unproved")
    # Earlier source A is a valid freshly captured B dependency. Only transitions
    # AFTER B's explicit preparation anchor require consumed-field disjointness.
    blocked={intent.changed_field}|{source.canonical_field_key for source in intent.dependency_sources}
    expected=copy.deepcopy(preparation.expected_state);expected_revision=preparation.state_revision
    reg_revision=preparation.anchor_registration_revision
    for receipt in chain[index+1:]:
        if (receipt.changed_field in blocked or receipt.before_state!=expected
            or receipt.before_state_revision!=expected_revision or receipt.before_registration_revision!=reg_revision
            or receipt.human_locks!=preparation.human_locks):
            fail("native_v2_post_preparation_drift")
        expected=copy.deepcopy(receipt.after_state);expected_revision=receipt.after_state_revision
        reg_revision=receipt.after_registration_revision
    if expected!=state or expected_revision!=state_revision or reg_revision!=registration_revision:
        fail("native_v2_unrelated_state_drift")
    p=preparation.prepared
    if job.get("lease")!=p.basis.lease.model_dump(mode="json") or job.get("record_revision")!=intent.original_base.record_revision:
        fail("native_v2_lease_or_original_base_changed")
    _native_checkpoint(job,p.publication.checkpoints[0],p.basis.scope)
    for dependency in p.basis.dependencies:
        native=job.get("fields",{}).get(str(dependency.field_key),{}).get("checkpoint")
        if (not isinstance(native,dict) or native.get("id")!=dependency.checkpoint_id
            or digest(native)!=dependency.checkpoint_digest):
            fail("native_v2_dependency_checkpoint_unproved")
        source=FieldCheckpoint.model_validate(native["payload"])
        if source.revision!=dependency.revision or digest(source.resolution)!=dependency.resolution_digest:
            fail("native_v2_dependency_resolution_unproved")
        _native_checkpoint(job,source,source.scope)
    return expected
