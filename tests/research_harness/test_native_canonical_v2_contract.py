"""V2 meaningful SOURCE controls, ALL UNRUN. Fakes are not native SQL proof.

The reused V1 fixture is a deliberately synthetic unresolved field; no input,
import, financial authority, provider invocation or real pilot is represented.
Pure controls invoke the actual typed chain/admission/native-checkpoint code.
Receipt controls invoke the actual V2 adapter with named native responses and
actual canonical projector/snapshot decoding. Native rollback/races require a
separate compiled connector qualification, never inferred from these fakes.
"""
import asyncio
import copy
import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from test_native_canonical_contract import basis as basis_v1
from test_native_canonical_contract import genuine_derivation, ident
from specimen_digitization.application.domain import AuditEvent
from specimen_digitization.application.projection import writes
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.research_harness import native_canonical as v1
from specimen_digitization.research_harness import native_canonical_v2 as adapter
from specimen_digitization.research_harness import publication_v2 as v2
from specimen_digitization.research_harness.native_prepack_proof_v2 import make_prepack_proof_v2
from specimen_digitization.research_harness.contracts import (
    FieldCheckpoint, FieldKey, HumanQuestion, SourceCoverageReceipt, SourceCoverageState, digest,
)
from specimen_digitization.research_harness.publication import NativeDependencyBasis, PreparedNativePublication


def native_checkpoint(cp):
    scope={key:getattr(cp.scope,key) for key in ("organization_id","collection_id","specimen_id","job_id","generation")}
    row={"scope":scope,"field_key":str(cp.field_key),"revision":cp.revision,"payload":cp.model_dump(mode="json"),
        "retry_command_id":cp.retry_command_id,"receipt_ids":list(cp.effect_receipt_ids),
        "dependencies":{str(d.field_key):d.revision for d in cp.resolution.dependencies},
        "dependency_digests":{str(d.field_key):d.digest for d in cp.resolution.dependencies}}
    row["id"]=digest({"scope":scope,"field":str(cp.field_key),"revision":cp.revision,"payload":row["payload"]})
    return row


def prepared_for(b,field,state,state_revision,*,resolution=None,revision=1):
    cp=b.prepared.publication.checkpoints[0].model_copy(update={"field_key":FieldKey(field),"revision":revision})
    if resolution is not None:
        cp=cp.model_copy(update={"resolution":resolution})
    else:
        cp=cp.model_copy(update={"resolution":cp.resolution.model_copy(update={"field_key":FieldKey(field)})})
    native=native_checkpoint(cp);job=state["jobs"][b.prepared.basis.job_key]
    native["binding_digest"]=job["binding_digest"]
    job["fields"][field].update(locked=False,revision=revision,checkpoint=native,work_state=str(cp.resolution.work_state))
    job["checkpoints"]=[r for r in job["checkpoints"] if r["field_key"]!=field]+[native]
    key=digest("v2-test-field-"+field)
    values=b.prepared.model_dump(mode="json");values["publication"]["checkpoints"]=[cp.model_dump(mode="json")]
    values["publication"]["idempotency_key"]=key
    guard=values["publication"]["guard"];guard.update(checkpoint_revisions={field:revision},checkpoint_digests={field:digest(cp)},
        dependency_revisions={str(d.field_key):d.revision for d in cp.resolution.dependencies},
        dependency_digests={str(d.field_key):d.digest for d in cp.resolution.dependencies},receipt_ids=list(cp.effect_receipt_ids))
    dependencies=[]
    for pin in cp.resolution.dependencies:
        source=job["fields"][str(pin.field_key)]["checkpoint"]
        dependencies.append(NativeDependencyBasis(field_key=pin.field_key,revision=pin.revision,
            resolution_digest=pin.digest,checkpoint_id=source["id"],checkpoint_digest=digest(source)).model_dump(mode="json"))
    pub_key="publish/"+key;cp_key="checkpoint/"+native["id"]
    state["outbox"][pub_key]={"kind":"canonical_publication_required","delivered":False,"guard":{"fixture":"not native authority"}}
    state["outbox"][cp_key]={"kind":"field_checkpoint","scope":native["scope"],"checkpoint_id":native["id"],"delivered":False}
    values["basis"].update(field_key=field,field_revision=revision,checkpoint_id=native["id"],checkpoint_digest=digest(native),
        original_typed_checkpoint_digest=digest(cp),typed_checkpoint_digest=digest(cp),dependencies=dependencies,
        state_revision=state_revision,state_digest=digest(state),checkpoint_outbox_key=cp_key,
        checkpoint_outbox_digest=digest(state["outbox"][cp_key]),publication_outbox_key=pub_key,
        publication_outbox_digest=digest(state["outbox"][pub_key]),idempotency_key=key,receipts=[])
    # Synthetic fixture has no evidence receipts. Real producer controls below
    # test science/native source validation; they make no new-write claim.
    values["publication"]["checkpoints"][0]["effect_receipt_ids"]=[]
    values["publication"]["guard"]["receipt_ids"]=[]
    values["basis"]["typed_checkpoint_digest"]=digest(values["publication"]["checkpoints"][0])
    values["publication"]["guard"]["checkpoint_digests"]={field:values["basis"]["typed_checkpoint_digest"]}
    return PreparedNativePublication.model_validate(values)


@pytest.fixture
def causal(basis_v1):
    b=basis_v1
    state={"contract_version":"research-durability/v1","program_key":"existing-program",
        "budget_policy":{"fixture":"no authority"},"budget_totals":{"settled_micro_usd":0,"held_micro_usd":0},
        "jobs":{b.prepared.basis.job_key:copy.deepcopy(b.raw["registrations"][0]["job"])},
        "outbox":{},"effects":{},"halted":False}
    job=state["jobs"][b.prepared.basis.job_key]
    job["lease"]=b.prepared.basis.lease.model_dump(mode="json")
    for field in job["fields"].values():field["work_state"]="pending"
    coverage=SourceCoverageReceipt(source_id="synthetic-offline-country",field_key=FieldKey.COUNTRY,
        state=SourceCoverageState.EXHAUSTED,source_version="fixture-v1",
        exact_join_attempted=True,query_digest=digest("synthetic-offline-country-query"),
        qualification_digest=digest("synthetic-offline-country-policy"),
        receipt_ids=("synthetic-offline-country-receipt",),
        coverage_limit="Explicit inert country fixture; no native or provider coverage claim",reason="fixture_exhausted")
    question=HumanQuestion(field_key=FieldKey.COUNTRY,question="Which country does this ambiguous fixture label name?",
        reason="semantic_ambiguity",coverage=(coverage,))
    resolution=b.prepared.publication.checkpoints[0].resolution.model_copy(update={
        "work_state":"waiting_human","question":question})
    p=prepared_for(b,"country",state,7,resolution=resolution)
    # Immutable preparation is captured only after the entire fixture state is
    # assembled. A later test expressly introduces unrelated drift.
    p=p.model_copy(update={"basis":p.basis.model_copy(update={"state_digest":digest(state)})})
    intent=make_intent(b,p)
    prep=make_preparation(intent,p,state,7,intent.original_base,None,v2.genesis_digest(intent.binding_id,intent.original_base),1)
    return SimpleNamespace(b=b,state=state,job=job,p=p,intent=intent,prep=prep)


def make_intent(b,prepared,sources=()):
    science=v2.scientific_basis_digest(prepared,sources)
    return v2.ScientificIntentV2(id=ident("intent:"+str(prepared.basis.field_key)),actor_uid=b.principal.user_id,
        server_request_identity_digest=digest("verified-server-command:"+str(prepared.basis.field_key)),
        idempotency_key=prepared.basis.idempotency_key,
        operation_digest=v2.operation_digest(b.principal.user_id,prepared.basis.idempotency_key,
            digest("verified-server-command:"+str(prepared.basis.field_key)),science),scientific_intent_digest=science,
        original_base=b.binding.registration.base_canonical,binding_id=b.binding.registration.binding_id,
        job_key=prepared.basis.job_key,program_key=prepared.basis.program_key,import_proof_id=ident("import"),
        import_proof_digest=digest("retained-import-not-authority"),authority_digest=digest("retained-authority-not-authority"),
        changed_field=str(prepared.basis.field_key),human_locks={k:False for k in v1.CANONICAL_KEYS},dependency_sources=sources,original_prepared=prepared)


def make_preparation(intent,p,state,revision,anchor,head_id,head_sha,reg_revision,*,previous=None):
    values={"contract_version":"research-publication-preparation/v2","id":ident("prep:"+str(intent.id)+":"+str(1 if previous is None else previous.ordinal+1)),
        "intent_id":str(intent.id),"ordinal":1 if previous is None else previous.ordinal+1,
        "prior_preparation_id":None if previous is None else str(previous.id),
        "prior_preparation_digest":None if previous is None else digest(previous),"mode":"NEW_AFTER_PROGRESS",
        "anchor":anchor.model_dump(mode="json"),"anchor_receipt_id":None if head_id is None else str(head_id),
        "anchor_chain_digest":head_sha,"anchor_registration_revision":reg_revision,"state_revision":revision,
        "state_digest":digest(state),"expected_state":copy.deepcopy(state),"source_basis":[s.model_dump(mode="json") for s in intent.dependency_sources],
        "authority_digest":intent.authority_digest,"human_locks":{k:False for k in v1.CANONICAL_KEYS},
        "scientific_intent_digest":intent.scientific_intent_digest,"prepared":p.model_dump(mode="json")}
    return v2.PreparationV2(**values,admission_digest=digest(values))


def identity(b,version,name):
    return v1.CanonicalIdentityV1(record_revision=version,record_version_id=ident("record:"+name),
        canonical_run_id=b.binding.canonical.canonical_run_id,host_record_version_id="opaque:"+name,snapshot_sha256=digest("snapshot:"+name))


def progress_fixture(c,used,field,result_digest,state=None):
    state=c.state if state is None else state
    work={key:value["work_state"] for key,value in state["jobs"][c.intent.job_key]["fields"].items()}
    blocked=any(state in {"waiting_source","waiting_policy","operational_failed","retry_scheduled","cancelled"} for state in work.values())
    return v2.CanonicalProgressReceiptV2(binding_id=c.intent.binding_id,job_key=c.intent.job_key,generation=1,
        prior_canonical=used,result_digest=result_digest,policy_digest=digest("fixture-policy-identity"),
        field_work_digest=digest(state["jobs"][c.intent.job_key]["fields"]),field_mapping_digest=digest(c.b.binding.registration.field_mapping),
        research_field_work=work,canonical_field_work=work,target_research_field=FieldKey(field),target_canonical_field=field,
        wire_status="processing_blocked" if blocked else "running",run_stage="processing_blocked" if blocked else "research_in_progress",
        disposition=None,operational_reason_codes=(),human_reason_codes=(),exportable=False)


def receipt(c,*,field="county",used=None,parent=None,state=None,state_revision=7,reg_revision=1,resulting=None,native_commit=None,preparation=None):
    used=used or c.intent.original_base;state=copy.deepcopy(c.state if state is None else state)
    p=preparation or c.prep
    suffix="" if parent is None else "/"+str(used.record_version_id)
    pub_key="synthetic-sibling-publication/"+field+suffix
    cp_key="synthetic-sibling-checkpoint/"+field+suffix
    if native_commit is None:
        native_commit={"fixture":"flat native receipt, no authority","field":field}
    if preparation is not None:
        pub_key=p.prepared.basis.publication_outbox_key;cp_key=p.prepared.basis.checkpoint_outbox_key
    else:
        # Required pending sibling rows are deliberately in this scenario's
        # original snapshot, not magically inserted by allowed-delta validation.
        state["outbox"].setdefault(pub_key,{"delivered":False})
        state["outbox"].setdefault(cp_key,{"delivered":False})
    after=v2.outbox_completion(state,pub_key,cp_key,native_commit)
    progress=progress_fixture(c,used,field,digest("fixture-pure-policy-graph"),state)
    values=dict(receipt_id=ident("receipt:"+field+":"+str(used.record_revision)),intent_id=c.intent.id,
        winning_preparation_id=p.id,operation_digest=c.intent.operation_digest,scientific_intent_digest=c.intent.scientific_intent_digest,
        preparation_digest=digest(p),admission_digest=p.admission_digest,authority_digest=c.intent.authority_digest,
        input_digest=c.p.basis.scope.input_digest,profile_digest=c.p.basis.scope.profile_digest,runtime_binding_digest=c.p.basis.binding_digest,
        actor_uid=c.b.principal.user_id,scope_identity={k:getattr(c.p.basis.scope,k) for k in ("organization_id","collection_id","specimen_id","job_id","generation")},
        binding_id=c.intent.binding_id,job_key=c.intent.job_key,program_key=c.intent.program_key,
        import_proof_id=c.intent.import_proof_id,import_proof_digest=c.intent.import_proof_digest,original_base=c.intent.original_base,
        used=used,resulting=resulting or identity(c.b,used.record_revision+1,field),parent_receipt_id=None if parent is None else parent.receipt_id,
        parent_chain_digest=v2.genesis_digest(c.intent.binding_id,c.intent.original_base) if parent is None else parent.chain_digest,
        changed_field=field,dependency_sources=c.intent.dependency_sources,human_locks=p.human_locks,
        before_state_revision=state_revision,after_state_revision=state_revision+1,before_state_digest=digest(state),after_state_digest=digest(after),
        before_state=state,after_state=after,publication_outbox_key=pub_key,checkpoint_outbox_key=cp_key,native_commit=native_commit,
        before_registration_revision=reg_revision,after_registration_revision=reg_revision+1,projection_digest=digest("fixture-projection"),
        prior_projection_digest=digest("fixture-prior"),projection_count=20,policy_receipt_digest=digest("fixture-policy"),
        lineage_digest=digest("fixture-lineage"),progress_receipt=progress,progress_receipt_digest=digest(progress),
        audit_id=ident("audit:"+field),outbox_id=ident("outbox:"+field))
    sha=digest({"parent":values["parent_chain_digest"],"receipt":str(values["receipt_id"]),"operation":values["operation_digest"],
        "used":used.model_dump(mode="json"),"resulting":values["resulting"].model_dump(mode="json"),"field":field,
        "preparation":values["preparation_digest"],"lineage":values["lineage_digest"]})
    return v2.NativeCausalReceiptV2(**values,chain_digest=sha)


def admit(c,p,current,head,chain,state,revision,reg_revision):
    return v2.verify_admission(c.intent,p,current,None if head is None else head.receipt_id,
        v2.genesis_digest(c.intent.binding_id,c.intent.original_base) if head is None else head.chain_digest,
        chain,revision,state,reg_revision,state["jobs"][c.intent.job_key])


def test_R1_fresh_after_prior_same_job_progress_observes_current_without_all20_barrier(causal):
    c=causal;a=receipt(c)
    state=copy.deepcopy(a.after_state);state["budget_totals"]["settled_micro_usd"]=10
    # Legitimate newly admitted OTHER research progress occurred BEFORE fresh B.
    state["jobs"][c.intent.job_key]["fields"]["city"]["revision"]=2
    p=c.p.model_copy(update={"basis":c.p.basis.model_copy(update={"state_revision":9,"state_digest":digest(state)})})
    fresh=make_preparation(c.intent,p,state,9,a.resulting,a.receipt_id,a.chain_digest,2)
    assert admit(c,fresh,a.resulting,a,[a],state,9,2)==state
    assert c.intent.original_base.record_revision==1 and len([v for v in c.job["fields"].values() if v["checkpoint"]])==1
    assert a.resulting.record_revision==2  # next actual write would use2->3, never jobbase reset


def test_R2_preprepared_only_exact_disjoint_sibling_outbox_delta_is_admitted(causal):
    c=causal
    c.state["outbox"]["synthetic-sibling-publication/county"]={"delivered":False}
    c.state["outbox"]["synthetic-sibling-checkpoint/county"]={"delivered":False}
    p=c.p.model_copy(update={"basis":c.p.basis.model_copy(update={"state_digest":digest(c.state)})})
    old=make_preparation(c.intent,p,c.state,7,c.intent.original_base,None,c.prep.anchor_chain_digest,1)
    a=receipt(c,state=c.state)
    assert admit(c,old,a.resulting,a,[a],a.after_state,8,2)==a.after_state
    assert old.prepared.basis.expected_record_revision==1 and old.expected_state!=a.after_state


def test_R3_unrelated_after_capture_drift_holds_old_but_new_unexecuted_append_only_preparation_can_bind(causal):
    c=causal;state=copy.deepcopy(c.state);state["budget_totals"]["settled_micro_usd"]=17
    with pytest.raises(v1.PublicationUnavailable,match="unrelated_state_drift"):
        admit(c,c.prep,c.intent.original_base,None,[],state,8,1)
    p=c.p.model_copy(update={"basis":c.p.basis.model_copy(update={"state_revision":8,"state_digest":digest(state)})})
    fresh=make_preparation(c.intent,p,state,8,c.intent.original_base,None,c.prep.anchor_chain_digest,1,previous=c.prep)
    retained=adapter.RetainedIntentV2(original=c.intent,preparations=(c.prep,fresh),attempt=None)
    assert retained.preparations[0]==c.prep and fresh.scientific_intent_digest==c.intent.scientific_intent_digest
    assert admit(c,fresh,c.intent.original_base,None,[],state,8,1)==state


@pytest.mark.parametrize("mutation",["human_foreign_prefix","missing_parent","duplicate_changed_key","wrong_native_uuid","wrong_opaque","wrong_import","different_pins"])
def test_complete_native_chain_rejects_foreign_missing_duplicate_and_identity_substitution(causal,mutation):
    c=causal;a=receipt(c);chain=[a];current=a.resulting
    if mutation=="human_foreign_prefix":current=identity(c.b,3,"foreign-human")
    if mutation=="missing_parent":a=a.model_copy(update={"parent_receipt_id":UUID(ident("unproved-parent"))});chain=[a]
    if mutation=="duplicate_changed_key":
        second=receipt(c,used=a.resulting,parent=a,state=a.after_state,state_revision=8,reg_revision=2)
        chain=[a,second];current=second.resulting;a=second
    if mutation=="wrong_native_uuid":current=current.model_copy(update={"record_version_id":UUID(ident("unproved-native"))})
    if mutation=="wrong_opaque":current=current.model_copy(update={"host_record_version_id":"unproved-opaque"})
    if mutation=="wrong_import":a=a.model_copy(update={"import_proof_digest":digest("foreign-import")});chain=[a]
    if mutation=="different_pins":a=a.model_copy(update={"profile_digest":digest("foreign-profile")});chain=[a]
    with pytest.raises(v1.PublicationUnavailable):
        v2.verify_chain(c.intent,c.intent.original_base,current,a.receipt_id,a.chain_digest,chain)


@pytest.mark.parametrize("mutation",["wrong_target_checkpoint","changed_human_lock","different_lease","reset_jobbase"])
def test_R4_target_checkpoint_lease_human_lock_and_jobbase_mutation_hold(causal,mutation):
    c=causal;state=copy.deepcopy(c.state)
    if mutation=="wrong_target_checkpoint":state["jobs"][c.intent.job_key]["fields"]["country"]["checkpoint"]["id"]=digest("changed")
    if mutation=="changed_human_lock":state["jobs"][c.intent.job_key]["fields"]["country"]["locked"]=True
    if mutation=="different_lease":state["jobs"][c.intent.job_key]["lease"]["fence"]=2
    if mutation=="reset_jobbase":state["jobs"][c.intent.job_key]["record_revision"]=2
    # Even a new captured state is not permission to change the science/lease/base.
    p=c.p.model_copy(update={"basis":c.p.basis.model_copy(update={"state_digest":digest(state)})})
    fresh=make_preparation(c.intent,p,state,7,c.intent.original_base,None,c.prep.anchor_chain_digest,1)
    with pytest.raises(Exception):
        admit(c,fresh,c.intent.original_base,None,[],state,7,1)


@pytest.mark.parametrize("kind",["G44","G41-ft","G41-m"])
def test_fresh_derived_B_after_source_A_keeps_actual_scientific_resolution_and_native_source_bases(causal,kind):
    from specimen_digitization.research_harness.evidence import validate_resolution
    c=causal;request,source,derived=genuine_derivation(c.b,kind)
    assert validate_resolution(request,derived)==derived
    source_cp=c.p.publication.checkpoints[0].model_copy(update={"field_key":source.field_key,"revision":7,"resolution":source})
    state=copy.deepcopy(c.state);job=state["jobs"][c.intent.job_key];native=native_checkpoint(source_cp)
    job["fields"][str(source.field_key)].update(locked=False,revision=7,checkpoint=native);job["checkpoints"].append(native)
    a=receipt(c,field=str(source.field_key),state=state)
    state=copy.deepcopy(a.after_state)
    p=prepared_for(c.b,str(derived.field_key),state,9,resolution=derived)
    p=p.model_copy(update={"basis":p.basis.model_copy(update={"state_digest":digest(state)})})
    dep=p.basis.dependencies[0]
    source_basis=v2.CanonicalSourceBasisV2(field_key=source.field_key,canonical_field_key=str(source.field_key),
        checkpoint_id=native["id"],checkpoint_digest=digest(native),checkpoint_revision=7,resolution_digest=digest(source),
        scientific_source_digest=derived.derivation.source_digest,candidate_id=ident("actual-fixture-source-candidate"),
        source_record_version_id=a.resulting.record_version_id,projection_record_version_id=a.resulting.record_version_id,
        canonical_run_id=a.resulting.canonical_run_id,evidence_ids=tuple(UUID(ident(e)) for e in derived.evidence_ids),lineage_digest=digest("fixture-native-lineage"))
    intent=make_intent(c.b,p,(source_basis,));c2=SimpleNamespace(**{**vars(c),"intent":intent,"p":p})
    fresh=make_preparation(intent,p,state,9,a.resulting,a.receipt_id,a.chain_digest,2)
    assert admit(c2,fresh,a.resulting,a,[a],state,9,2)==state
    assert source_basis.resolution_digest==dep.resolution_digest!=source_basis.scientific_source_digest
    # A belongs to the complete original chain BEFORE B's captured anchor; no
    # backwards disjointness rule may incorrectly reject this legitimate basis.
    later=receipt(c2,field=str(source.field_key),used=a.resulting,parent=a,state=state,state_revision=9,reg_revision=2)
    with pytest.raises(v1.PublicationUnavailable):
        admit(c2,fresh,later.resulting,later,[a,later],later.after_state,10,3)
    assert p.publication.checkpoints[0].resolution.derivation==derived.derivation


class ReceiptConnector:
    graph_blobs=None
    def __init__(self,row,intent_row):
        self.row=copy.deepcopy(row);self.intent_row=copy.deepcopy(intent_row);self.calls=[];self.denied=False
    def execute(self,operation,variables,mutation=False):
        self.calls.append(operation)
        if self.denied:raise PermissionError(v1.ACCESS_DENIED)
        outer={"organizationMember":{"active":True},"collectionMember":{"active":True,"role":"reviewer","canViewSensitive":False},"specimen":{"sensitive":False}}
        if operation=="GetResearchPublicationIntentV2":return {**outer,"intent":copy.deepcopy(self.intent_row)}
        if operation=="GetResearchPublicationReceiptV2":return {**outer,"retained":copy.deepcopy(self.row)}
        raise AssertionError("Receipt-first replay must not discover, lease, prepare, mutate or spend: "+operation)
    def _snapshot(self,row):
        return self.b.connector._snapshot(row)


def retained_fixture(c):
    b=c.b;result=b.prior.model_copy(deep=True);result.version=2
    result.run.stage="research_in_progress";result.run.disposition=None
    policy_graph=result.model_copy(deep=True)
    policy_digest=canonical_digest(result.model_dump(mode="json"))
    result.audit.append(AuditEvent(id=ident("audit:country"),actor=b.principal.user_id,action="research_publication",
        reason=c.intent.operation_digest,before={"revision":1},after={"revision":2}))
    # An unfinished publication has no disposition; its record still comes from the projector.
    projection=writes(result,b.connector.locate,b.connector._sized,b.principal.user_id,base_record=True)
    record=next(w.variables for w in projection if w.operation=="AppendRecordVersionV2")
    fields=sorted([w.variables for w in projection if w.operation=="AppendResolvedFieldV2"],key=lambda r:r["fieldKey"])
    result.audit[-1].after["record_version_id"]=record["id"]
    current=v1.CanonicalIdentityV1(record_revision=2,record_version_id=record["id"],canonical_run_id=result.run.id,
        host_record_version_id="opaque-native-result-2",snapshot_sha256=canonical_digest(result.model_dump(mode="json")))
    pub={"id":ident("receipt:country:1"),"actorUid":b.principal.user_id,"idempotencyKey":c.intent.idempotency_key,
        "operationDigest":c.intent.operation_digest,"preparedDigest":digest(c.prep),"publicationDigest":digest(c.p.publication),
        "specimenId":result.id,"bindingId":str(c.intent.binding_id),"jobId":c.p.basis.scope.job_id,"jobKey":c.intent.job_key,
        "generation":1,"inputDigest":c.p.basis.scope.input_digest,"profileDigest":c.p.basis.scope.profile_digest,
        "runtimeBindingDigest":c.p.basis.binding_digest,"usedCanonicalRevision":1,"usedRecordVersionId":str(c.intent.original_base.record_version_id),
        "usedHostRecordVersionId":c.intent.original_base.host_record_version_id,"usedSnapshotSha256":c.intent.original_base.snapshot_sha256,
        "resultingCanonicalRevision":2,"nativeRecordVersionId":record["id"],"canonicalRunId":result.run.id,
        "hostRecordVersionId":current.host_record_version_id,"snapshotSha256":current.snapshot_sha256,"projectionDigest":digest(fields),
        "projectionCount":20,"auditId":ident("audit:country"),"outboxId":ident("outbox:country"),
        "policyReceiptDigest":digest("fixture-policy"),"lineageDigest":digest("fixture-lineage"),"sensitive":False}
    progress=progress_fixture(c,c.intent.original_base,"country",policy_digest)
    prepack=make_prepack_proof_v2(policy_graph,result,result.model_dump(mode="json"),progress=progress,
        audit_id=pub["auditId"],actor_uid=b.principal.user_id,operation_digest=c.intent.operation_digest,native_record_version_id=record["id"])
    pub["prepackProofDigest"]=digest(prepack)
    proof=receipt(c,field="country",resulting=current,native_commit=pub,preparation=c.prep)
    proof=proof.model_copy(update={"projection_digest":digest(fields),"progress_receipt":progress,"progress_receipt_digest":digest(progress)})
    marker=adapter.RetainedAttemptV2(id=ident("attempt"),preparation_id=c.prep.id,operation_digest=c.intent.operation_digest,
        preparation_digest=digest(c.prep),admission_digest=c.prep.admission_digest)
    row={"publication":pub,"request":{"operation":v2.OPERATION_V2,"actorUid":b.principal.user_id,
        "idempotencyKey":c.intent.idempotency_key,"requestSha256":c.intent.operation_digest,"specimenId":result.id,"revision":2},
        "snapshot":{"snapshot":result.model_dump(mode="json"),"sha256":current.snapshot_sha256,"revision":2,"contractVersion":"0.1"},
        "record":{"id":record["id"],"runId":result.run.id,"predecessorId":str(c.intent.original_base.record_version_id)},
        "fields":fields,"audit":{"actorUid":b.principal.user_id,"revision":2,"requestSha256":c.intent.operation_digest},
        "outbox":{"aggregateRevision":2,"deduplicationKey":c.intent.operation_digest},
        "intent":c.intent.model_dump(mode="json"),"preparation":c.prep.model_dump(mode="json"),"causal":proof.model_dump(mode="json"),"attempt":marker.model_dump(mode="json"),"prepack":prepack}
    intent_row={"original":c.intent.model_dump(mode="json"),"preparation_count":1,"preparations":[c.prep.model_dump(mode="json")],"attempt":marker.model_dump(mode="json")}
    connector=ReceiptConnector(row,intent_row);connector.b=b
    writer=adapter.SqlConnectCanonicalResearchWriterV2(connector,None,blobs=None,materializer=None,operation_client=connector)
    return writer,connector


def call(c,callback):
    token=actor_uid.set(c.b.principal.user_id)
    try:return asyncio.run(callback())
    finally:actor_uid.reset(token)


def test_D3_restart_actual_adapter_replays_retained_winning_preparation_before_mutable_discovery(causal):
    c=causal;writer,connector=retained_fixture(c)
    result=call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert result.replayed and result.causal.used.record_revision==1 and result.published.record_revision==2
    assert result.causal.winning_preparation_id==c.prep.id
    assert connector.calls==["GetResearchPublicationIntentV2","GetResearchPublicationReceiptV2"]
    # journal/materializer are None: replay succeeds despite unavailable expired
    # lease/delivered-outbox/new binding, and reads no mutable current pointer.


def test_R5_accepted_lost_ack_control_retained_winner_never_refreshes_or_reissues_write(causal):
    c=causal;writer,connector=retained_fixture(c)
    first=call(c,lambda:writer._read_receipt_v2(c.b.principal,c.intent,replayed=True))
    second=call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert first.causal==second.causal and first.snapshot_sha256==second.snapshot_sha256
    assert all(name.startswith("GetResearchPublication") for name in connector.calls)


def test_R5_attempt_without_receipt_blocks_new_write_and_append_preparation(causal):
    c=causal;writer,connector=retained_fixture(c);connector.row=None
    with pytest.raises(v1.PublicationUnavailable,match="attempt_outcome_unknown"):
        call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,c.intent.idempotency_key,c.intent.server_request_identity_digest))
    with pytest.raises(v1.PublicationUnavailable,match="attempt_outcome_unknown"):
        call(c,lambda:writer.append_preparation(c.b.principal,c.intent,c.p))
    assert all(name.startswith("GetResearchPublication") for name in connector.calls)


@pytest.mark.parametrize("part",["request","snapshot","record","intent","preparation","causal","attempt","audit","outbox"])
def test_partial_native_receipt_pair_is_hold_never_absence_or_fallback(causal,part):
    c=causal;writer,connector=retained_fixture(c);connector.row[part]=None
    with pytest.raises(v1.PublicationUnavailable,match="receipt_partial"):
        call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert all(name.startswith("GetResearchPublication") for name in connector.calls)


def test_revoked_access_denies_even_complete_old_winning_receipt(causal):
    c=causal;writer,connector=retained_fixture(c);connector.denied=True
    with pytest.raises(PermissionError):
        call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert connector.calls==["GetResearchPublicationIntentV2"]


@pytest.mark.parametrize("tamper",["extra_field","missing_field","wrong_candidate","wrong_native_version","changed_receipt_op","wrong_snapshot"])
def test_exact20_projection_and_native_uuid_snapshot_receipt_controls(causal,tamper):
    c=causal;writer,connector=retained_fixture(c)
    if tamper=="extra_field":connector.row["fields"].append(copy.deepcopy(connector.row["fields"][0]))
    if tamper=="missing_field":connector.row["fields"].pop()
    if tamper=="wrong_candidate":connector.row["fields"][0]["candidateId"]=ident("unproved")
    if tamper=="wrong_native_version":connector.row["record"]["id"]=ident("unproved")
    if tamper=="changed_receipt_op":connector.row["publication"]["operationDigest"]=digest("different intent")
    if tamper=="wrong_snapshot":connector.row["snapshot"]["sha256"]=digest("unproved")
    with pytest.raises(v1.PublicationUnavailable):
        call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert all(name.startswith("GetResearchPublication") for name in connector.calls)


@pytest.mark.parametrize("kind",["G44","G41-ft","G41-m"])
def test_pending_genuine_derived_extension_is_explicit_hold_not_fake_literal_or_candidate(causal,kind):
    c=causal;request,source,resolution=genuine_derivation(c.b,kind)
    mapping={key:UUID(ident(key)) for key in resolution.evidence_ids}
    value=v1.canonical_value_v1(resolution,c.b.binding.registration.field_mapping,mapping)
    assert value.layer=="derived" and value.literal is None and resolution.derivation.source_digest!=resolution.dependencies[0].digest
    result=c.b.prior.model_copy(deep=True);result.version+=1;result.run.fields[str(resolution.field_key)]=value
    projection=writes(result,c.b.connector.locate,c.b.connector._sized,c.b.principal.user_id)
    row=next(w.variables for w in projection if w.operation=="AppendResolvedFieldV2" and w.variables["fieldKey"]==str(resolution.field_key))
    assert row["candidateId"] is None  # source proof of missing current dependency, NOT a waiver


def test_target_previously_published_before_new_anchor_cannot_repeat_same_generation(causal):
    c=causal;a=receipt(c,field="country")
    p=c.p.model_copy(update={"basis":c.p.basis.model_copy(update={"state_revision":8,"state_digest":digest(a.after_state)})})
    fresh=make_preparation(c.intent,p,a.after_state,8,a.resulting,a.receipt_id,a.chain_digest,2)
    with pytest.raises(v1.PublicationUnavailable,match="target_already_native_published"):
        admit(c,fresh,a.resulting,a,[a],a.after_state,8,2)


def test_winning_receipt_replay_ignores_later_current_pointer_and_retains_bytes(causal):
    c=causal;writer,connector=retained_fixture(c)
    original=copy.deepcopy(connector.row)
    # A later sibling pointer belongs to the fake authoritative store, but no
    # same-operation replay query is allowed to read or rewind that pointer.
    connector.current_pointer=identity(c.b,3,"later-sibling")
    result=call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert result.published.record_revision==2 and connector.current_pointer.record_revision==3
    assert connector.row==original and connector.calls==["GetResearchPublicationIntentV2","GetResearchPublicationReceiptV2"]


def test_v1_mutable_wrapper_entrypoints_cannot_silently_invoke_v2_writer(causal):
    c=causal;writer,connector=retained_fixture(c)
    with pytest.raises(v1.PublicationUnavailable,match="explicit_intent_preparation"):
        call(c,lambda:writer.publish_native_research(c.b.principal,c.p))
    with pytest.raises(v1.PublicationUnavailable,match="explicit_intent_preparation"):
        call(c,lambda:writer.publish_receipt_first(c.b.principal,c.p))
    assert connector.calls==[]


def test_concurrent_same_operation_receipt_contenders_return_one_immutable_winner_without_new_mutation(causal):
    c=causal;writer,connector=retained_fixture(c)
    async def contenders():
        return await asyncio.gather(*(writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,
            c.intent.idempotency_key,c.intent.server_request_identity_digest) for _ in range(2)))
    left,right=call(c,contenders)
    assert left.causal.receipt_id==right.causal.receipt_id and left.causal.winning_preparation_id==right.causal.winning_preparation_id
    assert left.snapshot_sha256==right.snapshot_sha256 and len(connector.calls)==4
    assert all(name.startswith("GetResearchPublication") for name in connector.calls)
    # This proves actual replay caller behavior only; the first-commit native
    # disjoint/same-field race and every SQL rollback boundary remain UNRUN.


def test_retained_attempt_cannot_be_switched_to_an_unproved_preparation(causal):
    c=causal;writer,connector=retained_fixture(c)
    connector.intent_row["attempt"]["preparation_id"]=ident("unretained-preparation")
    with pytest.raises(v1.PublicationUnavailable,match="attempt_partial"):
        call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert connector.calls==["GetResearchPublicationIntentV2"]


@pytest.mark.parametrize("state",["pending","researching","waiting_source","waiting_policy","operational_failed","retry_scheduled","cancelled"])
def test_V2_whole20_progress_has_no_disposition_while_running_or_operationally_blocked(causal,state):
    from pydantic import ValidationError
    c=causal;work={key:"resolved" for key in v1.RESEARCH_KEYS};work["county"]=state
    blocked=state in {"waiting_source","waiting_policy","operational_failed","retry_scheduled","cancelled"}
    values=progress_fixture(c,c.intent.original_base,"country",digest("whole20-actual-fixture")).model_dump(mode="json")
    values.update(research_field_work=work,canonical_field_work=work,
        wire_status="processing_blocked" if blocked else "running",run_stage="processing_blocked" if blocked else "research_in_progress")
    progress=v2.CanonicalProgressReceiptV2.model_validate(values)
    assert progress.disposition is None and not progress.exportable
    # Deferred is not the state of unfinished or blocked research.
    with pytest.raises(ValidationError):
        v2.CanonicalProgressReceiptV2.model_validate({**values,"disposition":"deferred"})
    for final in ("cleared","needs_human_review"):
        with pytest.raises(v1.PublicationUnavailable,match="false_completion"):
            v2.CanonicalProgressReceiptV2.model_validate({**values,"disposition":final})
    values["wire_status"]="completed"
    with pytest.raises(v1.PublicationUnavailable,match="false_completion"):
        v2.CanonicalProgressReceiptV2.model_validate(values)


def test_V2_progress_retains_genuine_human_reasons_while_sibling_work_remains(causal):
    c=causal;progress=progress_fixture(c,c.intent.original_base,"country",digest("fixture"))
    raw=progress.model_dump(mode="json");raw["human_reason_codes"]=["fixture-genuine-human-need"]
    actual=v2.CanonicalProgressReceiptV2.model_validate(raw)
    assert actual.human_reason_codes==("fixture-genuine-human-need",) and actual.disposition is None and not actual.exportable


@pytest.mark.parametrize("mutation",["missing","unknown","wrong_type","duplicate_mapping"])
def test_V2_progress_missing_or_unproved_whole20_work_state_holds(causal,mutation):
    c=causal;raw=progress_fixture(c,c.intent.original_base,"country",digest("fixture")).model_dump(mode="json")
    if mutation=="missing":del raw["canonical_field_work"]["county"]
    if mutation=="unknown":raw["canonical_field_work"]["county"]="unproved_unknown"
    if mutation=="wrong_type":raw["canonical_field_work"]["county"]=True
    if mutation=="duplicate_mapping":raw["research_field_work"]={"country":"resolved"}
    with pytest.raises(Exception):v2.CanonicalProgressReceiptV2.model_validate(raw)


# SOURCE UNRUN: synthetic retained work/reason metadata exercises actual typed
# guards and actual receipt replay; it grants no scientific/native authority.
# Compiled PublishCanonicalResearchV2 must separately qualify both terminal
# human cases, proper CLEAR, unfinished human cases and exportable type/mismatch
# controls with actual native rollback/readback. No source-string assertion or
# fake connector response is used as proof of that SQL transaction.
def terminal_progress_raw(c):
    raw=progress_fixture(c,c.intent.original_base,"country",digest("terminal-fixture-policy-graph")).model_dump(mode="json")
    work={key:"resolved" for key in v1.RESEARCH_KEYS}
    raw.update(research_field_work=work,canonical_field_work=dict(work),wire_status="completed",
        run_stage="quality_checked",disposition="cleared",operational_reason_codes=[],human_reason_codes=[],exportable=True)
    return raw


@pytest.mark.parametrize("human_basis",["waiting_human","retained_human_reason"])
def test_terminal_human_work_or_retained_reason_refuses_false_clear_and_accepts_review(causal,human_basis):
    raw=terminal_progress_raw(causal)
    if human_basis=="waiting_human":
        raw["research_field_work"]["country"]=raw["canonical_field_work"]["country"]="waiting_human"
    else:
        raw["human_reason_codes"]=["fixture-genuine-human-need"]
    before=copy.deepcopy(raw)
    with pytest.raises(v1.PublicationUnavailable,match="final_human_review_required"):
        v2.CanonicalProgressReceiptV2.model_validate(raw)
    assert raw==before
    raw.update(disposition="needs_human_review",exportable=False)
    actual=v2.CanonicalProgressReceiptV2.model_validate(raw)
    assert actual.wire_status=="completed" and actual.disposition=="needs_human_review" and not actual.exportable
    assert actual.human_reason_codes==tuple(raw["human_reason_codes"])
    assert actual.canonical_field_work==before["canonical_field_work"]


@pytest.mark.parametrize("state",["pending","researching","waiting_source","waiting_policy","operational_failed","retry_scheduled","cancelled"])
def test_unfinished_or_blocked_sibling_preserves_human_need_without_terminal_completion(causal,state):
    raw=terminal_progress_raw(causal)
    raw["research_field_work"]["country"]=raw["canonical_field_work"]["country"]="waiting_human"
    raw["research_field_work"]["county"]=raw["canonical_field_work"]["county"]=state
    raw["human_reason_codes"]=["fixture-genuine-human-need"]
    blocked=state not in {"pending","researching"}
    raw.update(wire_status="processing_blocked" if blocked else "running",
        run_stage="processing_blocked" if blocked else "research_in_progress",disposition=None,exportable=False)
    before=copy.deepcopy(raw)
    actual=v2.CanonicalProgressReceiptV2.model_validate(raw)
    assert actual.disposition is None and not actual.exportable
    assert actual.wire_status==raw["wire_status"] and actual.human_reason_codes==("fixture-genuine-human-need",)
    assert actual.research_field_work==before["research_field_work"] and actual.canonical_field_work==before["canonical_field_work"]
    assert raw==before


def held_policy_raw(c,*,reason=True,other=None):
    # verbatim_dts waits on the policy its profile declares missing; every other field is resolved.
    raw=terminal_progress_raw(c)
    raw["research_field_work"]["verbatim_dts"]=raw["canonical_field_work"]["verbatim_dts"]="waiting_policy"
    if other is not None:
        raw["research_field_work"]["county"]=raw["canonical_field_work"]["county"]=other
    raw["human_reason_codes"]=["mandatory_unresolved:verbatim_dts"] if reason else []
    return raw


def test_a_held_policy_field_refuses_clear_and_accepts_needs_human_review(causal):
    raw=held_policy_raw(causal)
    with pytest.raises(v1.PublicationUnavailable,match="final_human_review_required"):
        v2.CanonicalProgressReceiptV2.model_validate(raw)
    raw.update(disposition="needs_human_review",exportable=False)
    actual=v2.CanonicalProgressReceiptV2.model_validate(raw)
    assert actual.wire_status=="completed" and actual.disposition=="needs_human_review" and not actual.exportable
    assert actual.human_reason_codes==("mandatory_unresolved:verbatim_dts",)
    # Nor is it an operational block.
    with pytest.raises(v1.PublicationUnavailable,match="final_policy_unproved"):
        v2.CanonicalProgressReceiptV2.model_validate({**raw,"wire_status":"processing_blocked",
            "run_stage":"processing_blocked","disposition":None})


def test_waiting_policy_without_its_field_reason_stays_operationally_blocked(causal):
    raw=held_policy_raw(causal,reason=False)
    for final in ("cleared","needs_human_review"):
        with pytest.raises(v1.PublicationUnavailable,match="false_completion"):
            v2.CanonicalProgressReceiptV2.model_validate({**raw,"disposition":final,"exportable":final=="cleared"})
    raw.update(wire_status="processing_blocked",run_stage="processing_blocked",disposition=None,exportable=False)
    assert v2.CanonicalProgressReceiptV2.model_validate(raw).disposition is None


@pytest.mark.parametrize("state",["waiting_source","operational_failed","pending"])
def test_a_held_policy_field_does_not_hide_other_unfinished_or_blocked_work(causal,state):
    raw=held_policy_raw(causal,other=state)
    with pytest.raises(v1.PublicationUnavailable,match="false_completion"):
        v2.CanonicalProgressReceiptV2.model_validate({**raw,"disposition":"needs_human_review","exportable":False})
    blocked=state!="pending"
    raw.update(wire_status="processing_blocked" if blocked else "running",
        run_stage="processing_blocked" if blocked else "research_in_progress",disposition=None,exportable=False)
    actual=v2.CanonicalProgressReceiptV2.model_validate(raw)
    assert actual.disposition is None and actual.human_reason_codes==("mandatory_unresolved:verbatim_dts",)


def test_all_resolved_no_human_proper_clear_remains_possible_at_progress_guard(causal):
    raw=terminal_progress_raw(causal)
    actual=v2.CanonicalProgressReceiptV2.model_validate(raw)
    assert actual.wire_status=="completed" and actual.disposition=="cleared" and actual.exportable
    assert actual.human_reason_codes==() and set(actual.canonical_field_work.values())=={"resolved"}
    # This typed positive does not supply actual scientific/native policy.


def test_terminal_progress_refuses_a_missing_or_deferred_disposition(causal):
    from pydantic import ValidationError
    raw=terminal_progress_raw(causal);raw.update(disposition=None,exportable=False)
    with pytest.raises(v1.PublicationUnavailable,match="final_policy_unproved"):
        v2.CanonicalProgressReceiptV2.model_validate(raw)
    raw["disposition"]="deferred"
    with pytest.raises(ValidationError):
        v2.CanonicalProgressReceiptV2.model_validate(raw)


@pytest.mark.parametrize("disposition,exportable",[("cleared",False),("needs_human_review",True)])
def test_terminal_progress_refuses_exportable_disposition_mismatch(causal,disposition,exportable):
    raw=terminal_progress_raw(causal);raw.update(disposition=disposition,exportable=exportable)
    with pytest.raises(v1.PublicationUnavailable,match="final_policy_unproved"):
        v2.CanonicalProgressReceiptV2.model_validate(raw)


@pytest.mark.parametrize("exportable",["true","false",1,0,None])
def test_progress_exportable_is_a_strict_boolean_not_coerced_authority(causal,exportable):
    from pydantic import ValidationError
    raw=terminal_progress_raw(causal);raw["exportable"]=exportable
    with pytest.raises(ValidationError):
        v2.CanonicalProgressReceiptV2.model_validate(raw)


@pytest.mark.parametrize("human_basis",["waiting_human","retained_human_reason"])
def test_actual_retained_receipt_replay_refuses_terminal_human_false_clear_without_mutation(causal,human_basis):
    c=causal;writer,connector=retained_fixture(c)
    raw=terminal_progress_raw(c)
    if human_basis=="waiting_human":
        raw["research_field_work"]["country"]=raw["canonical_field_work"]["country"]="waiting_human"
    else:
        raw["human_reason_codes"]=["fixture-genuine-human-need"]
    connector.row["causal"]["progress_receipt"]=raw
    before=copy.deepcopy(connector.row)
    with pytest.raises(v1.PublicationUnavailable,match="final_human_review_required"):
        call(c,lambda:writer.resume_same_operation(c.b.principal,c.p.basis.scope.specimen_id,
            c.intent.idempotency_key,c.intent.server_request_identity_digest))
    assert connector.row==before
    assert connector.calls==["GetResearchPublicationIntentV2","GetResearchPublicationReceiptV2"]


# The binding registration writer. A fake operation client captures the native
# call; the SQL itself is not exercised here.
REGISTRATION_POLICY={"fixture":"synthetic committed budget policy, no authority"}


class RegistrationStore:
    def __init__(self,budget_policy):
        self.budget_policy=budget_policy;self.reads=[]
    def _read(self,scope):
        self.reads.append(scope)
        return SimpleNamespace(state={"budget_policy":copy.deepcopy(self.budget_policy)},revision=3)


class RegistrationConnector:
    graph_blobs=None
    def __init__(self):
        self.calls=[]
    def execute(self,operation,variables,mutation=False):
        self.calls.append((operation,copy.deepcopy(variables),mutation))
        if operation=="RegisterCanonicalResearchBindingV2":return {"registered":1}
        raise AssertionError("registration reads its binding back through read_current_binding: "+operation)


def registration_case(c,*,journal=False,policy_digest=None):
    reg=c.b.binding.registration
    semantic={**copy.deepcopy(reg.semantic_mapping),
        "journal_budget_policy_digest":policy_digest or digest(REGISTRATION_POLICY)}
    values={k:v for k,v in reg.model_dump(mode="json").items() if k in adapter.OwnerRegistrationV2.model_fields}
    authority=digest("synthetic registration authority")
    values.update(semantic_mapping=semantic,semantic_mapping_digest=digest(semantic),authority_digest=authority,
        import_proof_id=str(reg.binding_id),import_proof_digest=authority,
        current_chain_digest=v2.genesis_digest(reg.binding_id,reg.base_canonical))
    registration=adapter.OwnerRegistrationV2.model_validate(values)
    store=RegistrationStore(REGISTRATION_POLICY)
    scope=SimpleNamespace(actor_uid=c.b.principal.user_id,specimen_id=c.p.basis.scope.specimen_id)
    connector=RegistrationConnector()
    writer=adapter.SqlConnectCanonicalResearchWriterV2(connector,
        SimpleNamespace(store=store,scope=scope) if journal else None,blobs=None,operation_client=connector)
    async def read_back(principal,specimen_id):
        connector.calls.append(("read_current_binding",specimen_id,False))
        return "registered-binding"
    writer.read_current_binding=read_back
    return SimpleNamespace(registration=registration,store=store,scope=scope,connector=connector,writer=writer,
        specimen_id=c.p.basis.scope.specimen_id)


def test_an_operator_registers_the_binding_with_the_provisioners_store_and_scope(causal):
    c=causal;r=registration_case(c)
    operator=c.b.principal.model_copy(update={"role":"operator"})
    result=call(c,lambda:r.writer.register_current_binding(operator,r.specimen_id,r.registration,store=r.store,scope=r.scope))
    assert result=="registered-binding" and r.store.reads==[r.scope]
    assert [row[0] for row in r.connector.calls]==["RegisterCanonicalResearchBindingV2","read_current_binding"]
    operation,variables,mutation=r.connector.calls[0]
    payload=json.loads(variables["registrationJson"])
    assert mutation is True and variables["actorUid"]==operator.user_id and variables["specimenId"]==r.specimen_id
    assert payload["binding_id"]==str(r.registration.binding_id)
    assert payload["journal_budget_policy"]==REGISTRATION_POLICY and payload["state_revision"]==3


def test_a_viewer_cannot_register_a_binding(causal):
    c=causal;r=registration_case(c)
    viewer=c.b.principal.model_copy(update={"role":"viewer"})
    with pytest.raises(PermissionError,match="native_canonical_operator_required"):
        call(c,lambda:r.writer.register_current_binding(viewer,r.specimen_id,r.registration,store=r.store,scope=r.scope))
    assert r.connector.calls==[] and r.store.reads==[]


def test_registration_uses_the_journal_only_when_no_store_and_scope_are_passed(causal):
    c=causal;r=registration_case(c,journal=True)
    assert call(c,lambda:r.writer.register_current_binding(c.b.principal,r.specimen_id,r.registration))=="registered-binding"
    assert r.store.reads==[r.scope]
    bare=registration_case(c)
    with pytest.raises(ValueError,match="store_and_scope_required"):
        call(c,lambda:bare.writer.register_current_binding(c.b.principal,bare.specimen_id,bare.registration))
    assert bare.connector.calls==[]


@pytest.mark.parametrize("mismatch",["budget_policy","actor","specimen"])
def test_registration_refuses_an_unpinned_budget_policy_or_foreign_scope(causal,mismatch):
    c=causal
    r=registration_case(c,policy_digest=digest("another budget policy") if mismatch=="budget_policy" else None)
    if mismatch=="actor":r.scope.actor_uid="another-worker"
    if mismatch=="specimen":r.scope.specimen_id=ident("another-specimen")
    with pytest.raises(v1.PublicationUnavailable,match="native_v2_owner_policy_pin_unproved"):
        call(c,lambda:r.writer.register_current_binding(c.b.principal,r.specimen_id,r.registration,store=r.store,scope=r.scope))
    assert r.connector.calls==[]
